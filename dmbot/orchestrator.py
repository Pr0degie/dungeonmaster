"""DMbot orchestrator — the DM brain that turns player input into a DM answer.

Wires the LLM layer: buffer the players' transcribed lines per channel, and on a trigger build
the prompt (system persona + running history + the buffered lines), ask the LLM, and return the
German DM answer — while keeping a per-channel conversation history.

Player lines are buffered from the STT worker thread and read on the event loop, so the buffer
is lock-guarded.

The per-channel and per-turn records (``ChannelSession``, ``TurnAnswer``, …) live in
``dmbot/brain/channel.py`` and are re-exported here. Method groups of ``DMBrain`` live next to
them as mixins (ADR 065): ``pending`` (what the cogs take out of the brain and put into it),
``opening`` (``!start`` / ``!intro``), ``side_calls`` (classifiers, recap, rules answer) and
``generation`` (one answer through the guards).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Awaitable, Callable

from .llm.client import LLMClient
from .llm.failover import LLMPausedError
from .llm.persona import load_system_prompt
from .llm.prompt_assembly import assemble_system_prompt
from .rules.marker import MARKER_SPECS
from .rules.profile import SystemProfile
from .tts.textsplit import has_speakable_content

# Re-exported for back-compat after the pure helpers moved to dmbot/llm/* (ADR 034): tests
# and DMBrain/StreamAssembler still reference these names from `orchestrator`.
from .llm.sanitize import (  # noqa: F401
    _ROLE_LABEL,
    _ROLE_LABELS,
    _cut_at_labels,
    _sanitize,
    _sanitize_leading,
    _strip_leading_label,
    _trim_to_last_sentence,
)
from .llm.echo_guard import (  # noqa: F401
    _ECHO_NUDGE,
    _REPEAT_NUDGE,
    _ROLL_DIRECTIVE,
    is_echo,
    is_self_repetition,
)
from .llm.director_msgs import (  # noqa: F401
    build_intro_director_msg,
    build_opening_director_msg,
    scene_rejected_note_de,
)
from .llm.consistency import Violation
from .llm.turn_actions import group_by_speaker
from .llm.stream_assembler import (  # noqa: F401
    StreamAssembler, finalize_answer, finalize_answer_markers, finalize_answer_trimmed,
)

# The records moved to dmbot/brain/channel.py; re-exported for the same reason (ADR 034): the
# cogs and the tests reach ``TurnAnswer``, ``turn_user_msg`` and the others through this module.
from .brain.channel import (  # noqa: F401
    ChannelSession,
    TurnAnswer,
    _Attempt,
    _markers_dict,
    _Sink,
    _Turn,
    turn_user_msg,
)
from .brain.generation import GenerationMixin
from .brain.opening import OpeningMixin
from .brain.pending import PendingMixin
from .brain.side_calls import SideCallsMixin

log = logging.getLogger(__name__)


class DMBrain(GenerationMixin, SideCallsMixin, OpeningMixin, PendingMixin):
    """Per-channel history + a pending-player-lines buffer, driving one LLM client."""

    def __init__(
        self,
        client: LLMClient,
        *,
        profile: SystemProfile | None = None,
        max_history_turns: int = 20,
        num_predict: int = 220,
        max_buffer_lines: int = 8,
        retriever=None,
        recap_num_predict: Callable[[], int | None] | None = None,
    ) -> None:
        self._client = client
        # Output cap of the recap call (:meth:`summarize`), asked per call: the room a recap needs
        # depends on the tokens of the backend that answers, and that can change mid-session (a
        # failover). ``None`` — no hook, or the hook's answer — means ``RECAP_NUM_PREDICT``. The
        # wiring supplies the hook (dmbot.llm.recap_cap).
        self._recap_num_predict = recap_num_predict
        # Rulebook retriever (stage 3, ADR 019): an object with
        # ``async fetch_block(query, *, channel_id) -> str`` (rag/retrieve.RulebookRetriever).
        # Per turn the latest user_msg is embedded and matching rule chunks join the prompt —
        # threshold-gated, so narration turns carry no block; the channel id scopes the
        # campaign-memory half (ADR 054) to this channel's played sessions. None →
        # no retrieval (pre-10a behaviour, and what most unit tests use).
        self._retriever = retriever
        # Active system profile (Phase 8). When set, DM answers are scanned for <<TEST …>> markers
        # (rules/marker), which are stripped from the spoken text and surfaced as pending tests.
        # None → no dice flow (pre-Phase-8 behaviour, kept for the existing unit tests).
        self._profile = profile
        self._num_predict = num_predict  # hard cap on a turn's length (spoken aloud — keep it tight)
        self._max_messages = max_history_turns * 2  # a turn = one user + one assistant message
        # Continuous transcription (no wake word) buffers table talk + jokes between !dm presses;
        # sending the whole pile drowns the real action. Keep only the most recent lines so the
        # latest intent dominates. 0 = unbounded. Tunable via DM_MAX_LINES.
        self._max_buffer_lines = max_buffer_lines
        # Per-channel state: one :class:`ChannelSession` each, reached through :meth:`_session`.
        self._sessions: dict[int, ChannelSession] = {}
        # Guards session creation and every ``ChannelSession.buffer`` access: the buffer is written
        # from the STT thread and read on the event loop.
        self._lock = threading.Lock()
        # Token stats (prompt_eval_count / eval_count / num_ctx) from the most recent *narration*
        # call — set only by _chat_once / _stream_once, so the router's classify_test and summarize
        # calls don't overwrite it. The cog reads it right after respond()/redo() for the [latency]
        # line. None until the first turn.
        self.last_llm_stats: dict | None = None
        # The roll router's last classify_test verdict: {"raw": <constrained-JSON text>,
        # "decision": <TestRequest as dict> | None}. Stateless like the call itself — the dice
        # cog copies it into the turn's replay notes right after classifying. None until then
        # (and back to None when a classification fails).
        self.last_router: dict | None = None
        # The two post-turn classifiers of D107, captured the same way for the replay journal:
        # {"raw": <constrained-JSON text>, "verdict": <target id / commitment dict>,
        #  "failure": <enum value or None>}. Stateless like the calls themselves — the runtime
        # copies them into the turn's notes right after classifying (ADR 046).
        self.last_scene_router: dict | None = None
        self.last_facts: dict | None = None
        self.last_npcs: dict | None = None  # the presence classifier's (ADR 062), same shape

    @property
    def max_history_turns(self) -> int:
        """How many turns the in-memory history keeps — used to bound the autosave restore (D41)."""
        return self._max_messages // 2

    def _session(self, channel_id: int) -> ChannelSession:
        """The channel's :class:`ChannelSession`, created on first touch. Creation takes the lock
        because the STT thread reaches this through :meth:`add_player_line` — so never call it
        while holding the lock."""
        session = self._sessions.get(channel_id)
        if session is None:
            with self._lock:
                session = self._sessions.setdefault(channel_id, ChannelSession())
        return session

    def add_player_line(self, channel_id: int, name: str, text: str) -> None:
        """Buffer a transcribed player line for the next DM turn (STT thread-safe)."""
        session = self._session(channel_id)
        with self._lock:
            session.buffer.append((name, text))

    def pending_count(self, channel_id: int) -> int:
        """Player lines waiting for a DM turn — buffered ones and those a paused turn left."""
        session = self._session(channel_id)
        with self._lock:
            return len(session.buffer) + sum(len(lines) for _seq, lines in session.held_parts)

    def waiting_turn(self, channel_id: int) -> bool:
        """Whether a turn the paused backend left unanswered still waits: kept player lines, or
        dice results nobody narrated. A turn in flight has taken both along, so this is False
        while the call that ended the pause is that very turn. Lines merely buffered (spoken,
        mic not released yet) do not count."""
        session = self._session(channel_id)
        return bool(session.held_parts or session.test_results)

    def turn_held(self, channel_id: int) -> bool:
        """Whether the channel's latest turn attempt was put aside because the LLM backend is
        paused — its ``None`` then means "not answered yet", not "nothing to respond to"."""
        return self._session(channel_id).turn_held

    def _drain(self, channel_id: int) -> list[tuple[str, str]]:
        session = self._session(channel_id)
        with self._lock:
            lines = session.buffer
            session.buffer = []
            return lines

    def _prepare_turn(
        self, channel_id: int, extra_text: str | None
    ) -> tuple[str, list[str], list[dict[str, str]]] | None:
        """Drain + cap the buffered player lines (plus any typed ``extra_text``), fold in any
        pending dice results, and assemble ``(user_msg, labels, history)`` — the shared front half
        of :meth:`respond` and :meth:`respond_streaming`. Records the turn's last action (roll
        router) and last turn (redo). Returns ``None`` if there's nothing to respond to."""
        lines = self._drain(channel_id)
        # A line without a letter or digit ("...", "…" — STT on background noise) is no player
        # line. Dropped before the cap, so noise cannot push a real line out of the turn.
        if noise := sum(1 for _n, t in lines if t and not has_speakable_content(t)):
            log.debug("buffer: dropped %d player line(s) without a letter or digit", noise)
            lines = [(n, t) for n, t in lines if not t or has_speakable_content(t)]
        total = len(lines)
        if self._max_buffer_lines and total > self._max_buffer_lines:
            lines = lines[-self._max_buffer_lines:]  # keep the most recent — the latest intent
            log.info(
                "buffer: kept the last %d of %d player lines (older dropped as table-talk noise)",
                self._max_buffer_lines, total,
            )
        if extra_text:
            lines.append(("Spieler", extra_text.strip()))
        fresh = [(n, t) for n, t in lines if has_speakable_content(t)]  # also an empty/noise extra_text
        # A turn the paused backend left unanswered leads, outside the cap above: the cap drops
        # table-talk noise, and these lines were already chosen as a turn.
        session = self._session(channel_id)
        parts, session.held_parts = sorted(session.held_parts, key=lambda part: part[0]), []
        held = [line for _seq, part in parts for line in part]
        held_seq = parts[0][0] if parts else None
        lines = held + fresh
        # Dice results from clicked tests feed the consequence narration even with no player line.
        results = self._drain_test_results(channel_id)
        if not lines and not results:
            return None

        # GM notes (ADR 047, e.g. "clock full — consequence now") ride whatever turn comes next.
        # Drained AFTER the nothing-to-respond-to guard, so an empty auto-turn can't swallow them.
        notes, session.gm_notes = session.gm_notes, []

        # Remember the latest player action for the roll-detection router (ADR 014); None on a
        # results-only turn so the router doesn't re-fire on a stale action after a dice roll.
        session.last_action = lines[-1] if lines else None
        session.last_actions = group_by_speaker(lines)
        # Replay capture (ADR 046): the structured turn input, post-cap — what dm-eval re-feeds.
        session.replay_turn = {
            "lines": [[n, t] for n, t in lines], "results": list(results), "notes": list(notes),
        }

        # Result lines (engine rolls) lead, then GM notes, then the player lines — all context.
        parts = [f"[Würfel] {r}" for r in results]
        parts += [f"[Regie] {n}" for n in notes]
        parts += [f"{name}: {text}" for name, text in lines]
        if results and not lines:
            # Results-only turn: tell the model explicitly what to do with the bare roll line —
            # without this it tends to predict the next player line instead (echo, D43/ADR 018).
            parts.append(_ROLL_DIRECTIVE)
        user_msg = "\n".join(parts)
        # Labels become Ollama stop sequences and the post-hoc truncation guard against the model
        # fabricating replies / scripting several turns: this turn's own speakers + every known
        # character/player at the table (so an appended "Seskin: …"/"Pr0degie: …" puppet script is
        # cut even when those names didn't speak this turn) + the generic role labels. Deduped.
        labels = list(dict.fromkeys([name for name, _ in lines] + session.known_speakers + _ROLE_LABELS))
        session.turn_seq += 1
        session.last_turn = _Turn(
            user_msg, labels, seq=session.turn_seq, held_seq=held_seq,
            held=held, fresh=fresh, results=results, notes=notes,
        )
        return user_msg, labels, session.history

    def _hold_turn(self, channel_id: int, turn: _Turn, before: tuple) -> None:
        """The LLM backend is paused and nothing of ``turn`` was said (ADR 061, amendment
        2026-11-13 fourth): put its input back so the next turn answers it, and leave the session
        as if the turn had not been tried (``before``: the last-turn/last-action/replay fields
        from before :meth:`_prepare_turn`), so ``!redo`` and the roll router still see the turn
        that was really played.

        Only the turn the backend failed on is kept outside the player-line cap. A later attempt
        that had taken the kept lines along gives them back as they were, and its own new lines go
        to the head of the buffer, where the cap applies again. Several turns that were in flight
        when the backend failed are each kept, and ``_prepare_turn`` reads them in the order they
        were said, whichever failed first. Dice results and GM notes return to their own queues,
        which have no cap."""
        session = self._session(channel_id)
        if turn.held:
            session.held_parts.append((turn.held_seq, turn.held))
            with self._lock:
                session.buffer[:0] = turn.fresh
        elif turn.fresh:
            session.held_parts.append((turn.seq, turn.fresh))
        session.test_results[:0] = turn.results
        session.gm_notes[:0] = turn.notes
        turn.aside = True
        if session.last_turn is turn:
            # Only while this is still the channel's newest turn: a later one in flight owns
            # these fields, and if it gets its answer they must describe it (roll router, !redo).
            (session.last_turn, session.last_action, session.last_actions,
             session.replay_turn, session.replay_gen) = before
            if session.last_turn is not None and session.last_turn.aside:
                # ``before`` was taken while another turn was in flight that has been put aside
                # too: its input waits in the queues, so ``!redo`` must not run it a second time.
                session.last_turn, session.last_action, session.last_actions = None, None, []
        session.turn_held = True
        log.warning(
            "⏸ LLM backend paused — the turn is kept for later: %d player line(s), %d dice "
            "result(s), %d GM note(s)", len(turn.held) + len(turn.fresh), len(turn.results), len(turn.notes),
        )

    async def _refresh_rag(self, channel_id: int, user_msg: str) -> None:
        """Fetch the turn's ``## Regelwerk`` block for ``user_msg`` (stage 3, ADR 019). Empty for
        most turns (threshold) and on any failure — retrieval must never break a turn."""
        if self._retriever is None:
            return
        try:
            block = await self._retriever.fetch_block(user_msg, channel_id=channel_id)
        except Exception:
            log.exception("rag refresh failed — turn continues without it")
            block = ""
        self._session(channel_id).rag_block = block or ""

    async def _respond(
        self,
        channel_id: int,
        extra_text: str | None,
        *,
        sink: _Sink | None = None,
        check: Callable[[str], list[Violation]] | None = None,
    ) -> str | None:
        """The body of :meth:`respond` (``sink=None``) and :meth:`respond_streaming`: prepare
        the turn from the buffer, refresh the rulebook block, run it through :meth:`_run_turn`.
        ``None`` if there is nothing to respond to — and when the paused backend did not answer:
        the turn's input is then kept for the next turn (:meth:`_hold_turn`, :meth:`turn_held`)."""
        session = self._session(channel_id)
        before = (session.last_turn, session.last_action, session.last_actions,
                  session.replay_turn, session.replay_gen)
        prep = self._prepare_turn(channel_id, extra_text)
        if prep is None:
            session.turn_held = False
            return None
        user_msg, labels, history = prep
        turn = session.last_turn  # this turn's record — taken before any await
        await self._refresh_rag(channel_id, user_msg)
        try:
            answer = await self._run_turn(session, turn, history, sink=sink, check=check)
        except LLMPausedError:
            self._hold_turn(channel_id, turn, before)
            return None
        # Written when the turn ends, never when one starts: a turn starting in between must not
        # wipe what the cog is about to read for the turn that was just put aside.
        session.turn_held = False
        return answer

    async def respond(
        self, channel_id: int, *, extra_text: str | None = None,
        check: Callable[[str], list[Violation]] | None = None,
    ) -> str | None:
        """Run one DM turn for ``channel_id``: consume the buffered player lines (plus any
        directly typed ``extra_text``), ask the LLM, append to history and return the answer.
        Returns ``None`` if there is nothing to respond to. ``check`` is the consistency guard
        (ADR 045): violations regenerate the answer once before it reaches the table.
        """
        return await self._respond(channel_id, extra_text, check=check)

    async def _redo(
        self,
        channel_id: int,
        *,
        sink: _Sink | None = None,
        check: Callable[[str], list[Violation]] | None = None,
    ) -> str | None:
        """The body of :meth:`redo` (``sink=None``) and :meth:`redo_streaming`: take the last
        turn's input, drop its pair from history and its queued markers, run it again through
        :meth:`_run_turn`. ``None`` if there is no turn to redo yet."""
        session = self._session(channel_id)
        last = session.last_turn
        if last is None:
            session.turn_held = False
            return None
        history = session.history
        # Drop the pair this very turn stored, so the redo isn't duplicated — found by identity:
        # after a suppressed or failed turn there is none, and the last pair is the turn BEFORE it.
        idx = next((i for i, m in enumerate(history) if m is last.stored), None)
        removed = history[idx:idx + 2] if idx is not None else []
        if idx is not None:
            del history[idx:idx + 2]
        last.stored = None
        pending = session.pending
        self._drop_pending(channel_id)  # the redo supersedes the old turn's marker requests
        await self._refresh_rag(channel_id, last.user_msg)
        try:
            answer = await self._run_turn(session, last, history, sink=sink, check=check)
            session.turn_held = False
            return answer
        except LLMPausedError:
            # The paused backend gave no new answer: the old one stands, with its requests.
            if removed:
                history[idx:idx] = removed
                last.stored = removed[0]
            session.pending = pending
            session.turn_held = True
            log.warning("⏸ LLM backend paused — the redo is dropped, the previous answer stays")
            return None

    async def redo(self, channel_id: int, *,
                   check: Callable[[str], list[Violation]] | None = None) -> str | None:
        """Re-generate the **last** DM turn (same player input, a fresh answer) — for when the DM
        misunderstood. Drops the previous answer + its user turn from history first, so the new one
        replaces it rather than stacking. ``None`` if there is no turn to redo yet."""
        return await self._redo(channel_id, check=check)

    def _build_request(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, list[dict[str, str]], dict]:
        """Assemble ``(system, messages, options)`` for one DM turn — the shared head both the
        batch (:meth:`_chat_once`) and streaming (:meth:`_stream_once`) calls use, so they
        can't drift. The system-prompt slice order lives in :func:`assemble_system_prompt`; the
        session's blocks are read here, per call, so a block set mid-turn reaches a retry. Labels
        become Ollama stop sequences (the anti-puppeting guard). ``temperature`` is only set by the
        opening turns (D83), which pin a lower value for steadier instruction-following; a normal
        turn passes ``None`` → the model default (unchanged)."""
        system = assemble_system_prompt(
            load_system_prompt(),
            recap=session.recap,
            adventure=session.adventure_block,
            state_summary=session.state_summary,
            npc_memory=session.npc_memory_block,
            rag=session.rag_block,
            alias_hint=session.alias_hint,
        )
        messages = [*history_prefix, {"role": "user", "content": user_msg}]
        options = {"stop": [f"\n{label}:" for label in labels], "num_predict": num_predict or self._num_predict}
        if temperature is not None:
            options["temperature"] = temperature
        return system, messages, options

    def _queue_markers(self, session: ChannelSession, markers: dict[str, list]) -> None:
        """Queue the turn's parsed marker requests (ADR 051) under the results-only suppression
        rule and record what was actually queued for the replay journal (ADR 046) — called once
        per kept answer by :meth:`_guarded_answer`, batch or streamed.

        Suppression: inline ``<<TEST>>``/``<<MANIFEST>>``/``<<ORT>>``/``<<ERLEDIGT>>`` markers on
        a results-only (post-roll consequence) turn are dropped — a consequence narration must not
        request a NEW roll or scene move or the loop never ends (seen live); they queue only when
        the turn answered a player action. ``<<UHR>>``/``<<ZEIT>>`` are exempt (ADR 047/048): the
        post-roll consequence turn is the canonical tick/advance moment, and neither triggers a
        new roll/turn — no loop to guard."""
        queued = session.last_action is not None
        for spec in MARKER_SPECS:
            reqs = markers[spec.kind]
            if reqs and (queued or not spec.suppressible):
                session.pending[spec.kind].extend(reqs)
                if spec.kind == "tests":
                    session.tests_narrator = (self.last_llm_stats or {}).get("backend")
        # Replay capture (ADR 046): what this turn actually queued (empty when suppressed) —
        # the marker Soll dm-eval compares against.
        if session.replay_gen is None:
            session.replay_gen = {}
        session.replay_gen["markers"] = _markers_dict(markers, queued=queued)

    async def respond_streaming(
        self,
        channel_id: int,
        *,
        extra_text: str | None = None,
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None = None,
    ) -> str | None:
        """Streaming variant of :meth:`respond` (ADR 017): same buffering / history / pending-test
        bookkeeping, but drive the LLM with the client's ``chat_stream`` and ``await
        on_sentence(s)`` for each complete sentence as it's ready, so the cog can synthesise + speak
        it before the rest is done. ``should_abort()`` (e.g. ``lambda: paused``) stops emission
        cleanly. Returns the stored answer, or ``None`` if there's nothing to respond to."""
        return await self._respond(channel_id, extra_text, sink=_Sink(on_sentence, should_abort))

    async def redo_streaming(
        self,
        channel_id: int,
        *,
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None = None,
    ) -> str | None:
        """Streaming variant of :meth:`redo`: re-stream the last turn's input, replacing (not
        stacking) the previous answer in history."""
        return await self._redo(channel_id, sink=_Sink(on_sentence, should_abort))

    def _append_turn(self, history: list[dict[str, str]], user_msg: str, answer: str) -> dict[str, str]:
        """Append the pair and return its user message — the object ``!redo`` recognises it by."""
        user = {"role": "user", "content": user_msg}
        history.append(user)
        history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:  # keep the tail; recaps will cover the rest later
            del history[: len(history) - self._max_messages]
        return user

    @staticmethod
    def _log_classifier(kind: str, started: float, outcome: str) -> None:
        """One ``[classifier]`` line per side call: how long the verdict took, in ms, and what it
        was. Logging only. The number is the whole call as the turn experiences it — on the
        Claude backend that includes the CLI spawn (ADR 061), which is the point: it is the wait
        before the dice button, the scene change or the fact."""
        log.info("[classifier] %s %dms → %s", kind, round((time.monotonic() - started) * 1000), outcome)

    def add_test_result(self, channel_id: int, line: str) -> None:
        """Buffer a rolled test result (a German summary line) to feed the next turn so the DM
        narrates its consequence (architecture §9: 'back into the next prompt')."""
        self._session(channel_id).test_results.append(line)

    def _drain_test_results(self, channel_id: int) -> list[str]:
        session = self._session(channel_id)
        results, session.test_results = session.test_results, []
        return results

    def set_alias_hint(self, channel_id: int, hint: str) -> None:
        """Set (or clear, with '') the 'who plays whom' hint appended to this channel's prompt."""
        self._session(channel_id).alias_hint = hint or ""

    def set_known_speakers(self, channel_id: int, names: list[str]) -> None:
        """Register every character + player name at the table (CharacterStore.speaker_labels). They
        join the turn's own speakers as cut-labels + stop sequences, so a puppeted "Seskin: …" /
        "Pr0degie: …" script the model appends is truncated — the deterministic backstop to the
        persona's no-puppeting rule. An empty list clears it."""
        self._session(channel_id).known_speakers = list(names or ())

    def set_context(
        self, channel_id: int, *, recap: str = "", state_summary: str = "",
        adventure_block: str = "", npc_memory_block: str = "",
    ) -> None:
        """Set the memory context injected into this channel's prompt: the stored recap (narrative
        thread), the compact world-state block (hard facts, Phase 9), the adventure block
        (summary + current scene card, Phase 10a) and the NPC-memory block (what the scene's NPCs
        remember, ADR 044). Empty strings clear them. The cog calls this on join (from the loaded
        state) and after every state change."""
        session = self._session(channel_id)
        session.recap = recap or ""
        session.state_summary = state_summary or ""
        session.adventure_block = adventure_block or ""
        session.npc_memory_block = npc_memory_block or ""

    def current_recap(self, channel_id: int) -> str:
        """The recap currently injected into this channel's prompt (set via :meth:`set_context`), or
        "" if none. The auto-compaction (D57) reads it to make the next recap cumulative."""
        return self._session(channel_id).recap

    def history_len(self, channel_id: int) -> int:
        """Number of stored messages (user + assistant) in this channel's history — lets the cog see
        whether a compaction actually shrank the running history."""
        return len(self._session(channel_id).history)

    def history_messages(self, channel_id: int, start: int = 0) -> list[dict[str, str]]:
        """A copy of this channel's history messages from index ``start`` on — the NPC-memory
        extractor's input window (ADR 044): the turns of the scene just left."""
        return [dict(m) for m in self._session(channel_id).history[start:]]

    @property
    def client(self) -> "LLMClient":
        """The shared LLM client — injected into side-band callers that own their own prompt
        (the NPC-memory extractor, ADR 044), so they stay testable pure-function modules."""
        return self._client

    def clear_history(self, channel_id: int) -> None:
        """Drop the channel's rolling conversation history *only* (the auto-compaction reset, D57).

        Unlike :meth:`reset` (a fresh session), this keeps the recap, world-state/adventure blocks,
        pending tests/results and the buffer untouched — only the turn-by-turn history is cleared,
        because the just-generated cumulative recap now carries that thread forward. The next prompt
        is then persona + adventure + (longer) recap + state + empty history, safely under budget, so
        the persona/adventure are never the truncated head again.

        Removes exactly the message objects the matching :meth:`summarize` folded into the recap
        (``compact_consumed``): a turn appended, redone or still in flight during the summarize
        await, or one the history cap shifted, stays — the recap never saw it (ADR 030 #4).
        The live list is filtered in place, because a turn still in
        flight holds it and appends its pair there. ``last_turn`` survives exactly when its
        stored pair does: once that pair went into the recap, ``!redo`` has nothing to redo; a
        turn with no stored pair yet (in flight, suppressed) keeps it.

        With no record (a direct call, not via the auto-compaction) it falls back to a full wipe
        into a new list and clears ``last_turn``."""
        session = self._session(channel_id)
        consumed, session.compact_consumed = session.compact_consumed, None
        if consumed is None:
            session.history = []  # no record → original full-clear behaviour
            session.last_turn = None
            return
        gone = {id(m) for m in consumed}  # ``consumed`` keeps the objects alive, so ids are stable
        session.history[:] = [m for m in session.history if id(m) not in gone]
        last = session.last_turn
        if last is not None and last.stored is not None and id(last.stored) in gone:
            session.last_turn = None

    def reset(self, channel_id: int) -> None:
        """Forget a channel's history and pending lines (e.g. new session)."""
        # Reset in place, field by field: the session object stays, so a line the STT thread
        # buffers during the reset lands in the new buffer. ``known_speakers`` and the replay
        # capture are deliberately not touched — they never were.
        session = self._session(channel_id)
        with self._lock:
            session.buffer = []
        session.held_parts = []
        session.turn_held = False
        session.history = []
        session.last_turn = None
        session.compact_consumed = None
        self._drop_pending(channel_id)
        session.gm_notes = []
        session.test_results = []
        session.last_action = None
        session.last_actions = []
        session.alias_hint = ""
        session.recap = ""
        session.state_summary = ""
        session.adventure_block = ""
        session.npc_memory_block = ""
        session.rag_block = ""

    async def aclose(self) -> None:
        await self._client.aclose()
