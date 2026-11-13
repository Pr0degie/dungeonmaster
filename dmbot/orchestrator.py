"""DMbot orchestrator — the DM brain that turns player input into a DM answer (Phase 5).

Wires the LLM layer: buffer the players' transcribed lines per channel, and on a trigger build
the prompt (system persona + running history + the buffered lines), ask Ollama, and return the
German DM answer — while keeping a per-channel conversation history.

Later phases extend the prompt (recap → JSON state → RAG) and add the dice-marker flow; for now
it is persona + history + the latest player turn. Player lines are buffered from the STT worker
thread and read on the event loop, so the buffer is lock-guarded.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

from .llm.client import LLMClient
from .llm.persona import load_system_prompt
from .llm.prompt_assembly import assemble_system_prompt
from .llm.roll_router import classifier_schema, classifier_system, to_test_request
from .memory.recap import RECAP_MAX_CHARS, RECAP_NUM_PREDICT, RECAP_SYSTEM_DE, build_recap_user
from .rules.marker import (
    MARKER_SPECS,
    ClockTickRequest,
    ErledigtRequest,
    ManifestRequest,
    SceneRequest,
    TestRequest,
    ZeitRequest,
    empty_markers,
)
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
from .llm.fact_router import FactVerdict, classify_commitment
from .llm.npc_router import NpcVerdict, classify_present_npcs
from .llm.scene_router import SceneVerdict, classify_scene_move
from .llm.consistency import Violation, retry_nudge_de
from .llm.intro_guard import INTRO_RETRY_NUDGE
from .llm.turn_actions import group_by_speaker
from .llm.stream_assembler import StreamAssembler, finalize_answer, finalize_answer_markers  # noqa: F401

log = logging.getLogger(__name__)


def _markers_dict(markers: dict[str, list], *, queued: bool) -> dict:
    """The turn's parsed marker requests as plain dicts for the replay journal (ADR 046).
    ``queued=False`` (a results-only turn suppressed them) records empty lists for the
    suppressible kinds — the suppression itself is behaviour the replay must reproduce.
    Non-suppressible kinds (``uhr``/``zeit``, ADR 047/048: the post-roll consequence turn is
    the canonical tick/advance moment) record what was parsed regardless. Key order is the
    registry order (ADR 051) — the journal bytes must not move."""
    return {
        spec.kind: (
            [asdict(r) for r in markers[spec.kind]] if queued or not spec.suppressible else []
        )
        for spec in MARKER_SPECS
    }


@dataclass
class ChannelSession:
    """Everything :class:`DMBrain` keeps for one voice channel. One object per channel, created
    on first touch (:meth:`DMBrain._session`) and reset in place by :meth:`DMBrain.reset`."""

    # The running conversation, user/assistant pairs, capped at ``max_history_turns``.
    history: list[dict[str, str]] = field(default_factory=list)
    # Transcribed player lines waiting for the next turn. Written from the STT thread, read on
    # the event loop — touch it only under ``DMBrain._lock``.
    buffer: list[tuple[str, str]] = field(default_factory=list)
    # How many history messages the last :meth:`DMBrain.summarize` folded into the recap. The
    # auto-compaction clears history right after the (awaited) summarize, but a dice-button turn
    # can append to the live list *during* that await — :meth:`DMBrain.clear_history` removes
    # only these first N messages so that concurrent turn survives both the recap and the
    # history (Finding #4). Cleared once consumed; None → clear_history does a full wipe.
    compact_consumed: int | None = None
    # The pending-marker store (ADR 051): the requests parsed from the last DM turn, one list
    # per registry kind (``tests``, ``manifests``, ``scenes``, ``erledigt``, ``uhr``, ``zeit``).
    # Drained through :meth:`DMBrain.take_pending` — by dicecog (tests/manifests) and the
    # delivery pipeline (the rest); what each consumer does is on the ``take_pending_<kind>``
    # wrappers.
    pending: dict[str, list] = field(default_factory=empty_markers)
    # One-shot GM directives injected into the NEXT turn's user message as "[Regie] …" lines
    # (ADR 047: "clock X is full — the consequence hits now"). Code-queued only, drained by
    # _prepare_turn like dice results, exempt from the player-line cap.
    gm_notes: list[str] = field(default_factory=list)
    # Test results fed back in (engine roll → narrate consequence): prepended to the next turn,
    # exempt from the player-line cap.
    test_results: list[str] = field(default_factory=list)
    # A light "who plays whom" hint (display name → character) appended to the system prompt,
    # so the model stops confusing player and character names (open item F).
    alias_hint: str = ""
    # Every character + player name at the table (CharacterStore.speaker_labels). They join the
    # turn's own speakers as cut-labels + stop sequences, so a puppeted "Seskin: …"/"Pr0degie: …"
    # script the model tacks on is truncated — the deterministic guard behind the persona's
    # no-puppeting rule (the live fix; nemo ignores the soft rule). Survives :meth:`DMBrain.reset`.
    known_speakers: list[str] = field(default_factory=list)
    # Memory (Phase 9): the stored session recap + a compact world-state block, injected into the
    # system prompt after the persona (docs/conventions.md order: core → tone → recap → JSON state →
    # history). Set by the cog from the world state, refreshed when state changes.
    recap: str = ""
    state_summary: str = ""
    # The adventure block (stage 1+2 of the hybrid, ADR 019): always-on adventure summary +
    # the current scene card, selected by code from WorldState.scene_id. Set by the cog.
    adventure_block: str = ""
    # The NPC-memory block (ADR 044): what the current scene's NPCs remember, rendered by the
    # runtime from the world state (top-K per NPC). Set alongside the state summary.
    npc_memory_block: str = ""
    # The turn's ``## Regelwerk`` block (stage 3, ADR 019) — refreshed per turn, mostly empty.
    rag_block: str = ""
    # The last turn's (user_msg, labels), so !redo can re-generate it when the DM misunderstood —
    # same input, a fresh answer that replaces the last one in history.
    last_turn: tuple[str, list[str]] | None = None
    # The last player action (name, text) consumed — the roll-detection router (ADR 014)
    # classifies it after the narration turn. None when a turn had no player line (e.g. a
    # test-result feedback turn), so the router skips it.
    last_action: tuple[str, str] | None = None
    # Every speaker's action of that same turn, one entry each (D111). ``last_action`` is its
    # last element and stays for callers that only ask "was there an action?"; the router walks
    # this list so a turn with several declarations produces a test button per declaring
    # character instead of only for whoever spoke last.
    last_actions: list[tuple[str, str]] = field(default_factory=list)
    # Replay capture (ADR 046): the structured input of the turn in flight (player lines +
    # drained dice-result lines, set by _prepare_turn/_prepare_opening) and the generation side
    # (the kept answer's raw LLM text + the markers it queued). Drained into the history autosave
    # by take_replay_turn; the eval harness (dm-eval) replays them. Survive :meth:`DMBrain.reset`.
    replay_turn: dict | None = None
    replay_gen: dict | None = None


@dataclass
class _Sink:
    """Where a streamed turn speaks: ``on_sentence`` gets each complete sentence as it is
    ready, ``should_abort()`` (e.g. ``lambda: paused``) stops emission cleanly. A turn with a
    sink streams, a turn without one is a batch turn — the only difference between the paths."""

    on_sentence: Callable[[str], Awaitable[None]]
    should_abort: Callable[[], bool] | None = None


@dataclass
class _Attempt:
    """One LLM call's outcome, batch or streamed: the sanitised answer and its parsed markers.
    A streamed attempt also says what it still holds back (``remaining``, not spoken yet),
    whether it spoke anything and whether the stream broke mid-generation."""

    answer: str
    markers: dict[str, list]
    remaining: list[str] = field(default_factory=list)
    spoke_any: bool = False
    errored: bool = False


class DMBrain:
    """Per-channel history + a pending-player-lines buffer, driving one Ollama client."""

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
        session = self._session(channel_id)
        with self._lock:
            return len(session.buffer)

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
        total = len(lines)
        if self._max_buffer_lines and total > self._max_buffer_lines:
            lines = lines[-self._max_buffer_lines:]  # keep the most recent — the latest intent
            log.info(
                "buffer: kept the last %d of %d player lines (older dropped as table-talk noise)",
                self._max_buffer_lines, total,
            )
        if extra_text:
            lines.append(("Spieler", extra_text.strip()))
        lines = [(n, t) for n, t in lines if t]
        # Dice results from clicked tests feed the consequence narration even with no player line.
        results = self._drain_test_results(channel_id)
        if not lines and not results:
            return None

        # GM notes (ADR 047, e.g. "clock full — consequence now") ride whatever turn comes next.
        # Drained AFTER the nothing-to-respond-to guard, so an empty auto-turn can't swallow them.
        session = self._session(channel_id)
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
        session.last_turn = (user_msg, labels)
        return user_msg, labels, session.history

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
        ``None`` if there is nothing to respond to."""
        prep = self._prepare_turn(channel_id, extra_text)
        if prep is None:
            return None
        user_msg, labels, history = prep
        await self._refresh_rag(channel_id, user_msg)
        return await self._run_turn(
            self._session(channel_id), user_msg, labels, history, sink=sink, check=check
        )

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
            return None
        user_msg, labels = last
        history = session.history
        if (
            len(history) >= 2
            and history[-1]["role"] == "assistant"
            and history[-2]["role"] == "user"
        ):
            del history[-2:]  # drop the turn we're redoing so it isn't duplicated
        self._drop_pending(channel_id)  # the redo supersedes the old turn's marker requests
        await self._refresh_rag(channel_id, user_msg)
        return await self._run_turn(session, user_msg, labels, history, sink=sink, check=check)

    async def redo(self, channel_id: int, *,
                   check: Callable[[str], list[Violation]] | None = None) -> str | None:
        """Re-generate the **last** DM turn (same player input, a fresh answer) — for when the DM
        misunderstood. Drops the previous answer + its user turn from history first, so the new one
        replaces it rather than stacking. ``None`` if there is no turn to redo yet."""
        return await self._redo(channel_id, check=check)

    async def _apply_consistency(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history: list[dict[str, str]],
        answer: str,
        check: Callable[[str], list[Violation]] | None,
    ) -> str:
        """The consistency guard (ADR 045): check the answer against the world state and, on a
        violation, regenerate **once** with a concrete German correction appended (the echo/intro
        nudge mechanism). Strictly fail-open — a guard error, an empty retry or a still-violating
        retry all deliver an answer anyway; the guard never blocks the session. Max one retry.

        Marker hygiene: markers the discarded first answer queued must not survive it — snapshot
        + clear the pending queues before the retry (whose own :meth:`_guarded_answer` re-queues
        its markers) and restore the snapshot only if the retry is discarded (mirrors ``redo``)."""
        if check is None or not answer:
            return answer
        try:
            violations = check(answer)
        except Exception:
            log.exception("consistency guard raised — delivering unchecked (fail-open)")
            return answer
        if not violations:
            return answer
        found = ",".join(f"{v.kind}:{v.npc}" for v in violations)
        log.warning("[consistency] violated (%s) — regenerating once", found)
        snapshot, session.pending = session.pending, empty_markers()
        nudged = f"{user_msg}\n{retry_nudge_de(violations)}"
        retry, _errored = await self._guarded_answer(session, nudged, labels, history)
        if not retry:
            # Kind by kind, and only where the first answer had queued something: a kind it left
            # empty keeps whatever the discarded retry queued (unchanged behaviour).
            for kind, reqs in snapshot.items():
                if reqs:
                    session.pending[kind] = reqs
            log.warning("[consistency] retry came back empty — keeping the first answer (fail-open)")
            return answer
        try:
            still = check(retry)
        except Exception:
            still = []
        retry_ok = not still
        if not retry_ok:
            log.warning("[consistency] retry still violates (%s) — delivering anyway (fail-open)",
                        ",".join(f"{v.kind}:{v.npc}" for v in still))
        log.info("[consistency] regenerated=1 violations=%s retry_ok=%s", found, retry_ok)
        return retry

    def _prepare_opening(self, channel_id: int, director_msg: str) -> tuple[str, list[str], list[dict[str, str]]]:
        """Assemble the one-off ``(user_msg, labels, history)`` for the ``!start`` opening turn.

        Unlike :meth:`_prepare_turn` this consumes no buffered player lines and adds no
        ``Spieler:`` line — the opening is a GM-side *director* instruction, not a player action.
        Crucially it leaves the session's ``last_action`` untouched (so it stays None), which makes
        :meth:`_queue_markers` skip queuing any ``<<TEST>>``/``<<ORT>>``
        marker the model might emit — i.e. **no dice on a briefing** (the task's dice-suppression
        requirement) falls out of the existing results-only guard for free. Records ``last_turn``
        so the opening can be ``!redo``-ne like any turn, and reuses the same labels (known table
        speakers + role labels) so the anti-puppeting stop sequences still apply."""
        session = self._session(channel_id)
        labels = list(dict.fromkeys(session.known_speakers + _ROLE_LABELS))
        session.last_turn = (director_msg, labels)
        # Replay capture (ADR 046): an opening turn re-feeds its director_msg, not player lines.
        session.replay_turn = {"lines": [], "results": [], "opening": True}
        return director_msg, labels, session.history

    async def _opening(
        self,
        channel_id: int,
        director_msg: str,
        *,
        sink: _Sink | None = None,
        is_weak: Callable[[str], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """The body of :meth:`respond_opening` (``sink=None``) and
        :meth:`respond_opening_streaming`: the one-off director turn through :meth:`_run_turn`."""
        user_msg, labels, history = self._prepare_opening(channel_id, director_msg)
        return await self._run_turn(
            self._session(channel_id), user_msg, labels, history,
            sink=sink, is_weak=is_weak, num_predict=num_predict, temperature=temperature,
        )

    async def respond_opening(self, channel_id: int, director_msg: str, num_predict: int | None = None,
                              temperature: float | None = None,
                              is_weak: Callable[[str], bool] | None = None) -> str | None:
        """Run the opening-briefing turn (``!start`` / ``!intro test``, batch path): generate one GM
        turn from the ``director_msg`` instruction, append it to history, return the answer. Dice are
        suppressed (see :meth:`_prepare_opening`). ``""`` only on the rare echo-guard suppression.
        ``!intro`` passes a lower ``temperature`` (D83) so the monologue reliably follows the director
        brief instead of wandering into a short generic turn.

        ``is_weak`` (the batch-only intro guard, ADR 041 follow-up): when given and the generated
        opening reads weak (too short / a player figure skipped — the 12B model's high-variance
        failure), regenerate **once** with a firmer nudge before the turn reaches the table. Only the
        kept answer is appended to history. Streaming ``!intro`` can't use this (audio already plays),
        which is why the validated batch path is the one to prefer once synthesis is fast enough."""
        return await self._opening(
            channel_id, director_msg, is_weak=is_weak, num_predict=num_predict, temperature=temperature
        )

    async def respond_opening_streaming(
        self,
        channel_id: int,
        director_msg: str,
        *,
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str | None:
        """Streaming variant of :meth:`respond_opening` (the live path, ADR 017): same one-off
        director turn, spoken sentence-by-sentence via ``on_sentence``. Dice stay suppressed.
        ``!intro`` passes a lower ``temperature`` (D83) for steadier instruction-following."""
        return await self._opening(
            channel_id, director_msg, sink=_Sink(on_sentence, should_abort),
            num_predict=num_predict, temperature=temperature,
        )

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

    async def _chat_once(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, dict[str, list]]:
        """One non-streaming LLM call for ``user_msg`` on top of ``history_prefix`` → (sanitised
        answer, ``{kind: parsed requests}`` keyed by the marker registry, ADR 051). The raw
        building block of :meth:`_guarded_answer`: a batch turn's first attempt, and the
        echo-guard retry of every turn, streamed ones included."""
        system, messages, options = self._build_request(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature)
        raw = await self._client.chat(system, messages, options=options)
        # narration call's token counts (for [latency]).
        self.last_llm_stats = self._client.last_stats
        # Debug aid (lands in debug.log only — 🪵 is filtered off the console + terminal mirror):
        # the raw LLM output BEFORE marker-stripping, so we can see whether the model emitted a
        # <<TEST …>> marker at all (the prime suspect when the dice-marker flow doesn't fire).
        log.info("🪵 LLM roh: %s", raw.replace("\n", " ⏎ "))
        # Replay capture (ADR 046): the raw text with markers intact. Each call overwrites, so
        # after an echo-guard/consistency retry the KEPT answer's raw is what the autosave gets.
        session.replay_gen = {"raw": raw}
        return finalize_answer_markers(raw, labels, self._profile)

    @staticmethod
    def _answer_problem(answer: str, user_msg: str, prev_answer: str) -> tuple[str, str] | None:
        """``(log label, retry nudge)`` when the answer parrots a player line (D43/ADR 018) or
        re-narrates the DM's own previous answer (W4/ADR 019); ``None`` when the answer is fine."""
        if not answer:
            return None
        if is_echo(answer, user_msg):
            return "parrots a player line", _ECHO_NUDGE
        if is_self_repetition(answer, prev_answer):
            return "re-narrates the previous answer", _REPEAT_NUDGE
        return None

    @staticmethod
    def _prev_answer(history_prefix: list[dict[str, str]]) -> str:
        """The DM's most recent stored answer (for the self-repetition check), or ''."""
        if history_prefix and history_prefix[-1].get("role") == "assistant":
            return history_prefix[-1].get("content", "")
        return ""

    async def _stream_once(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        sink: _Sink,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> _Attempt:
        """One streamed LLM call — the streaming counterpart of :meth:`_chat_once`. Drives
        ``chat_stream`` through a :class:`StreamAssembler` and speaks sentences via the sink as
        they're ready. Degrades on a mid-stream error — keeps what was spoken, flags the attempt
        ``errored``, never raises out of a half-spoken turn."""
        system, messages, options = self._build_request(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature)
        assembler = StreamAssembler(labels, self._profile)
        errored = False
        spoke_any = False
        agen = self._client.chat_stream(system, messages, options=options)
        try:
            async for delta in agen:
                for sentence in assembler.feed(delta):
                    if has_speakable_content(sentence):  # skip a lone "."/quote/backtick (don't synth it)
                        await sink.on_sentence(sentence)
                        spoke_any = True
                if assembler.stopped:
                    break  # a mid-text speaker label — abort the stream, keep the narration
                if sink.should_abort is not None and sink.should_abort():
                    break  # paused (ADR 013): stop emitting; resume won't replay
        except Exception:
            log.exception("streaming turn failed mid-generation — keeping the partial answer")
            errored = True
        finally:
            await agen.aclose()  # closes the httpx stream (the client-side stop)
        self.last_llm_stats = self._client.last_stats
        log.info("🪵 LLM roh (stream): %s", assembler.raw.replace("\n", " ⏎ "))
        # Replay capture (ADR 046) — an echo-guard retry overwrites this via _chat_once, so the
        # kept answer's raw wins (batch-path parity).
        session.replay_gen = {"raw": assembler.raw}
        result = assembler.finish()
        return _Attempt(result.answer, result.markers, list(result.remaining), spoke_any, errored)

    async def _guarded_answer(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        *,
        sink: _Sink | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str | None, bool]:
        """One DM answer for ``user_msg`` behind the echo guard (D43/ADR 018 + W4) — the single
        generation path of every turn. ``sink=None`` asks the LLM in one batch call
        (:meth:`_chat_once`); with a sink the first attempt streams (:meth:`_stream_once`).

        If the answer merely parrots a player line or re-narrates the DM's own previous answer,
        retry once with a corrective nudge — always a plain batch call, the corrective rare path.
        If the retry misfires again the turn is suppressed: nothing spoken, nothing stored
        (degenerate turns in history self-reinforce, seen live 2026-06-12). A streamed attempt is
        only retried while nothing was spoken — an echo/repetition is held back by the assembler's
        last-sentence rule for short answers; a half-spoken or errored turn is never retried.

        Speaks what a streamed turn still holds back and queues the kept answer's markers.
        Returns ``(answer, errored)``: ``answer`` is ``None`` for a suppressed turn, ``errored``
        says the stream broke mid-generation."""
        streaming = sink is not None
        prev = self._prev_answer(history_prefix)
        if sink is None:
            attempt = _Attempt(*await self._chat_once(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature))
        else:
            attempt = await self._stream_once(session, user_msg, labels, history_prefix, sink, num_predict=num_predict, temperature=temperature)
            prev = self._prev_answer(history_prefix)  # the streamed path has always read it after the stream
        answer, markers, remaining = attempt.answer, attempt.markers, attempt.remaining
        suppressed = False
        problem = None if (attempt.errored or attempt.spoke_any) else self._answer_problem(answer, user_msg, prev)
        if problem is not None:
            label, nudge = problem
            log.warning("echo guard%s: answer %s (%r) — retrying once", " (stream)" if streaming else "", label, answer)
            nudged = f"{user_msg}\n{nudge}"
            try:
                answer, markers = await self._chat_once(session, nudged, labels, history_prefix, num_predict=num_predict, temperature=temperature)
            except Exception:
                if not streaming:
                    raise  # a batch turn has always let a failed retry propagate
                log.exception("echo-guard retry failed — suppressing the turn")
                answer, markers = "", empty_markers()
            if self._answer_problem(answer, user_msg, prev) is not None:
                log.warning("echo guard: the retry misfired again — suppressing the turn")
                if not streaming:
                    # Kept deviation: a suppressed batch turn leaves here, before _queue_markers,
                    # so its replay capture has no "markers" key, while a suppressed streamed
                    # turn goes on and records empty markers. Why: aligning the two would change
                    # what the replay journal (ADR 046) records, and this split changes nothing.
                    return None, False
                answer, markers = "", empty_markers()
            suppressed = streaming and not answer
            remaining = [answer] if answer else []
        elif attempt.spoke_any and not attempt.errored and is_self_repetition(answer, prev):
            # A long repetition streams sentence-by-sentence before finish() can judge it — too
            # late to retract audio. Keep history parity (stored == spoken) but flag it loudly
            # for the tuning loop (W4 visibility).
            log.warning("echo guard: streamed answer re-narrated the previous one (already spoken)")
        if sink is not None:
            for sentence in remaining:
                if sink.should_abort is not None and sink.should_abort():
                    break
                if has_speakable_content(sentence):
                    await sink.on_sentence(sentence)
        self._queue_markers(session, markers)
        return (None if suppressed else answer), attempt.errored

    async def _run_turn(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history: list[dict[str, str]],
        *,
        sink: _Sink | None = None,
        check: Callable[[str], list[Violation]] | None = None,
        is_weak: Callable[[str], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """The turn core, shared by the batch and the streaming path of every turn kind
        (respond, redo, opening): the guarded answer (:meth:`_guarded_answer`), the two
        regenerate-once guards a batch turn can carry — the intro guard (``is_weak``, ADR 041
        follow-up) and the consistency guard (``check``, ADR 045) — and the history entry.
        Returns the answer for the table — ``""`` when the echo guard suppressed the turn (D43):
        content-less to the cog, the pair stays out of history.

        ``check`` and ``is_weak`` are for batch turns only: a streamed answer is already spoken
        when they could judge it, so the streaming entry points never pass them."""
        answer, errored = await self._guarded_answer(
            session, user_msg, labels, history,
            sink=sink, num_predict=num_predict, temperature=temperature,
        )
        if answer and is_weak is not None and is_weak(answer):
            log.warning("intro guard: opening came out weak — regenerating once")
            nudged = f"{user_msg}\n{INTRO_RETRY_NUDGE}"
            retry, _errored = await self._guarded_answer(
                session, nudged, labels, history, num_predict=num_predict, temperature=temperature
            )
            if retry:
                answer = retry  # keep the retry even if still weak — never speak less than we had
        if answer is None:
            return ""
        answer = await self._apply_consistency(session, user_msg, labels, history, answer, check)
        stored = answer
        if errored and stored:
            stored = f"{stored} … [Antwort unterbrochen]"  # noted in history; never spoken
        trimmed = self._append_turn(history, user_msg, stored)
        if trimmed and session.compact_consumed is not None and history is session.history:
            # A summarize is out and the cap just trimmed messages it counted from the head —
            # shift its count so clear_history doesn't delete this turn as well (finding 3).
            session.compact_consumed = max(0, session.compact_consumed - trimmed)
        return answer

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
        bookkeeping, but drive the LLM with :meth:`OllamaClient.chat_stream` and ``await
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

    def _append_turn(self, history: list[dict[str, str]], user_msg: str, answer: str) -> int:
        """Append the pair; return how many messages the history cap trimmed from the head."""
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": answer})
        trimmed = max(0, len(history) - self._max_messages)
        if trimmed:  # keep the tail; recaps will cover the rest later
            del history[:trimmed]
        return trimmed

    def take_pending(self, kind: str, channel_id: int) -> list:
        """Return and clear the queued requests of one marker-registry kind (ADR 051). The
        named ``take_pending_<kind>`` wrappers below stay the public surface — dicecog, the
        delivery handlers and dm-eval call those."""
        pending = self._session(channel_id).pending
        reqs, pending[kind] = pending[kind], []
        return reqs

    def _drop_pending(self, channel_id: int) -> None:
        """Drop every queued marker request of the channel — a redo/reset supersedes them."""
        self._session(channel_id).pending = empty_markers()

    def take_pending_tests(self, channel_id: int) -> list[TestRequest]:
        """Return and clear the dice tests the last DM turn requested (cog posts the buttons)."""
        return self.take_pending("tests", channel_id)

    def take_pending_manifests(self, channel_id: int) -> list[ManifestRequest]:
        """Return and clear the psychic Manifest requests the last DM turn made (ADR 022) — the
        cog posts a button for each that rolls the Manifest Test + bookkeeps Warp Charge."""
        return self.take_pending("manifests", channel_id)

    def take_pending_scenes(self, channel_id: int) -> list[SceneRequest]:
        """Return and clear the scene-transition requests the last DM turn made (ADR 026) — the cog
        validates the target against the adventure and posts a confirm button for the move."""
        return self.take_pending("scenes", channel_id)

    def take_pending_erledigt(self, channel_id: int) -> list[ErledigtRequest]:
        """Return and clear the scene-element flag requests the last DM turn made (ADR 043) — the
        delivery pipeline validates each id against the current scene card and confirms/applies."""
        return self.take_pending("erledigt", channel_id)

    def take_pending_uhr(self, channel_id: int) -> list[ClockTickRequest]:
        """Return and clear the clock-tick requests the last DM turn made (ADR 047) — the delivery
        pipeline validates each id against ``WorldState.clocks``, clamps to +1 per clock per turn
        and confirms/applies the tick."""
        return self.take_pending("uhr", channel_id)

    def take_pending_zeit(self, channel_id: int) -> list[ZeitRequest]:
        """Return and clear the time-advance requests the last DM turn made (ADR 048) — the
        delivery pipeline honours only the first valid one, clamps to +12h per turn and
        confirms/applies the advance."""
        return self.take_pending("zeit", channel_id)

    def add_gm_note(self, channel_id: int, note: str) -> None:
        """Queue a one-shot GM directive for the NEXT turn's user message (``[Regie] …`` line,
        ADR 047 — e.g. "clock X is full, the consequence hits now"). Code-queued only, never
        LLM-written; drained by ``_prepare_turn`` like dice results."""
        if note:
            self._session(channel_id).gm_notes.append(note)

    def discard_gm_notes(self, channel_id: int, *, containing: str) -> int:
        """Drop still-queued GM notes containing ``containing`` (ADR 047: ``!uhr zurück`` from a
        full clock must retract the not-yet-fired consequence note). Returns how many went."""
        session = self._session(channel_id)
        keep = [n for n in session.gm_notes if containing not in n]
        dropped = len(session.gm_notes) - len(keep)
        session.gm_notes = keep
        return dropped

    def last_action(self, channel_id: int) -> tuple[str, str] | None:
        """The latest player action (display-name, text) the last turn answered, or None — the
        roll-detection router (ADR 014) classifies this. None on a results-only turn."""
        return self._session(channel_id).last_action

    def last_actions(self, channel_id: int) -> list[tuple[str, str]]:
        """Every speaker's action of the turn just answered, one ``(display-name, text)`` each.

        The roll-detection router (ADR 014) walks this instead of :meth:`last_action`, so a turn
        in which two players each declared something can produce a test for both — before D111
        only the last speaker of a turn could ever be asked to roll.
        """
        return list(self._session(channel_id).last_actions)

    def take_replay_turn(self, channel_id: int) -> dict | None:
        """Return and clear the last turn's replay-journal fields (ADR 046): the structured
        input (``lines``/``results``/``opening``), the kept answer's ``raw`` LLM text and the
        ``markers`` it queued. ``None`` when nothing was captured (e.g. a stubbed brain path).
        The autosave merges this into the turn record; ``load_recent`` ignores the extras."""
        session = self._session(channel_id)
        turn, session.replay_turn = session.replay_turn, None
        gen, session.replay_gen = session.replay_gen, None
        if turn is None and gen is None:
            return None
        return {**(turn or {}), **(gen or {})}

    def last_user_msg(self, channel_id: int) -> str | None:
        """The user message of the most recent turn (for history autosave, D41), or None."""
        last = self._session(channel_id).last_turn
        return last[0] if last else None

    def restore_history(self, channel_id: int, turns: list[tuple[str, str]]) -> int:
        """Restore prior ``(user_msg, answer)`` turns into this channel's history on join — crash
        recovery (D41). Only fills an **empty** history (never clobbers a live session) and respects
        the history cap. Returns how many turns were restored. Note: ``last_turn`` is *not*
        restored, so ``!redo`` is unavailable for the restored last turn (known limitation)."""
        session = self._session(channel_id)
        if session.history:
            return 0
        history: list[dict[str, str]] = []
        for user_msg, answer in turns:
            if not answer.strip():
                continue  # marker-only/suppressed turns: don't re-teach empty answers on restore (D43)
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:
            history = history[len(history) - self._max_messages:]
        session.history = history
        return len(history) // 2

    @staticmethod
    def _log_classifier(kind: str, started: float, outcome: str) -> None:
        """One ``[classifier]`` line per side call: how long the verdict took, in ms, and what it
        was. Logging only. The number is the whole call as the turn experiences it — on the
        Claude backend that includes the CLI spawn (ADR 061), which is the point: it is the wait
        before the dice button, the scene change or the fact."""
        log.info("[classifier] %s %dms → %s", kind, round((time.monotonic() - started) * 1000), outcome)

    async def classify_test(
        self, *, action: str, character: str | None, skills: list[str]
    ) -> TestRequest | None:
        """Roll-detection router (ADR 014): a separate, stateless, constrained-JSON LLM call that
        decides whether ``action`` needs a test and which skill/difficulty — instead of trusting the
        narration model's inline marker. ``skills`` constrains the choice to the acting character's
        sheet. Returns a TestRequest (target_name = ``character``) or None. Never raises."""
        self.last_router = None  # replay capture (ADR 046): reset; set only on a clean verdict
        if self._profile is None or not action.strip():
            return None
        difficulties = list(self._profile.difficulty_ladder)
        schema = classifier_schema(skills, difficulties)
        system = classifier_system(
            skills, difficulties, self._profile.display_name or self._profile.name
        )
        started = time.monotonic()
        try:
            raw = await self._client.chat(
                system,
                [{"role": "user", "content": f"Spieler-Handlung: {action}"}],
                # Anti-repetition OFF for the constrained verdict (overrides the client's narration
                # default, B1): the classifier_system prompt lists every skill + difficulty in the
                # repeat_last_n window, so a repeat_penalty would penalise the very enum value the
                # router must pick — corrupting a deterministic, reliability-critical path (golden
                # rule #2 / ADR 014). Per-call options win over the instance default.
                options={"temperature": 0, "num_predict": 80, "repeat_penalty": 1.0, "repeat_last_n": 0},
                format=schema,
            )
            data = json.loads(raw)
        except Exception:
            log.exception("roll-router classification failed")
            self._log_classifier("roll", started, "failed")
            return None
        req = to_test_request(data, character=character)
        self._log_classifier(
            "roll", started,
            f"{req.skill} ({req.difficulty or 'Standard'})" if req is not None else "no test",
        )
        self.last_router = {"raw": raw, "decision": asdict(req) if req is not None else None}
        return req

    async def classify_scene_move(
        self, *, turn_text: str, exits, current_title: str = "", context: str = ""
    ) -> SceneVerdict:
        """Scene-move classifier (ADR 057 #1) — the same shape as :meth:`classify_test`: a
        separate, stateless, constrained-JSON call whose answer space is exactly the current
        scene's reachable exits plus "nein". The brain only lends its client and records the
        verdict for the replay journal; validation and the pointer write live outside
        (``llm/scene_router.py`` and ``rules/scene_flow.py``). Never raises."""
        started = time.monotonic()
        verdict = await classify_scene_move(
            self._client.chat, turn_text=turn_text, exits=exits, current_title=current_title,
            context=context,
        )
        self._log_classifier(
            "scene", started,
            verdict.failure.value if verdict.failure else (verdict.target_id or "stay"),
        )
        self.last_scene_router = {
            "raw": verdict.raw,
            "verdict": verdict.target_id,
            "failure": verdict.failure.value if verdict.failure else None,
        }
        return verdict

    async def classify_commitment(
        self, *, answer_text: str, recipients=(), givers=()
    ) -> FactVerdict:
        """Fact classifier (ADR 058 #1) — the second post-turn call, run on the same turn
        boundary as :meth:`classify_scene_move` so the two share one latency window. Reports what
        the narration committed to; the world-state write is the caller's, through
        ``WorldState.record_commitment``. Never raises."""
        started = time.monotonic()
        verdict = await classify_commitment(
            self._client.chat, answer_text=answer_text, recipients=recipients, givers=givers
        )
        self._log_classifier(
            "fact", started,
            verdict.failure.value if verdict.failure
            else (verdict.commitment.kind if verdict.commitment is not None else "none"),
        )
        self.last_facts = {
            "raw": verdict.raw,
            "verdict": asdict(verdict.commitment) if verdict.commitment is not None else None,
            "failure": verdict.failure.value if verdict.failure else None,
        }
        return verdict

    async def classify_present_npcs(
        self, *, answer_text: str, party=(), roster=(), present=()
    ) -> NpcVerdict:
        """Presence classifier (ADR 062) — the third post-turn call on the same boundary. Reports
        who newly appears in person; registering them is the caller's. Never raises."""
        started = time.monotonic()
        verdict = await classify_present_npcs(
            self._client.chat, answer_text=answer_text, party=party, roster=roster,
            present=present,
        )
        self._log_classifier(
            "npcs", started,
            verdict.failure.value if verdict.failure
            else (", ".join(s.label for s in verdict.sightings) or "none"),
        )
        self.last_npcs = {
            "raw": verdict.raw,
            "verdict": [asdict(s) for s in verdict.sightings],
            "failure": verdict.failure.value if verdict.failure else None,
        }
        return verdict

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

    async def summarize(self, channel_id: int, *, prior_recap: str = "") -> str | None:
        """Produce a German "Was bisher geschah" recap from this channel's history (the `wrap up`
        trigger, D14). Code stores the returned string in the world state; this only generates it.
        ``None`` if there's no history to summarise.

        ``prior_recap`` folds an earlier recap into the transcript so the new recap is **cumulative**:
        when the running history is cleared, the older recap still covers what scrolled out of it, and
        the new recap supersedes-and-extends it. Both the rolling auto-compaction (D57) AND ``!wrap up``
        pass the current recap so neither loses the part an earlier (auto-)recap already folded away;
        "" gives a plain summary of the visible history (e.g. a session's very first recap)."""
        session = self._session(channel_id)
        history = session.history
        if not history:
            return None
        # Record how many messages this recap consumes *before* the await, so a turn appended to the
        # live list while the LLM runs is preserved by clear_history (Finding #4). build_recap_user
        # reads the list synchronously here; the await below is where a concurrent append can land.
        session.compact_consumed = len(history)
        user = build_recap_user(history, prior_recap)
        cap = self._recap_num_predict() if self._recap_num_predict is not None else None
        raw = await self._client.chat(
            RECAP_SYSTEM_DE,
            [{"role": "user", "content": user}],
            options={"temperature": 0.3, "num_predict": cap or RECAP_NUM_PREDICT},
        )
        # Light cleanup only (no marker/test stripping — a recap has none): drop markdown + a leading
        # role label the model might prepend.
        text = _ROLE_LABEL.sub("", raw.replace("*", "").strip()).strip()
        if len(text) > RECAP_MAX_CHARS * 1.5:
            # The length is only prompted — code cannot shorten a recap without losing facts. Say
            # so, because a recap that keeps growing ends at the output cap again.
            log.warning("recap is %d characters, the prompt asks for at most %d — it is kept as it is",
                        len(text), RECAP_MAX_CHARS)
        return text or None

    def current_recap(self, channel_id: int) -> str:
        """The recap currently injected into this channel's prompt (set via :meth:`set_context`), or
        "" if none. The auto-compaction (D56) reads it to make the next recap cumulative."""
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
        """The shared Ollama client — injected into side-band callers that own their own prompt
        (the NPC-memory extractor, ADR 044), so they stay testable pure-function modules."""
        return self._client

    def clear_history(self, channel_id: int) -> None:
        """Drop the channel's rolling conversation history *only* (the auto-compaction reset, D56).

        Unlike :meth:`reset` (a fresh session), this keeps the recap, world-state/adventure blocks,
        pending tests/results and the buffer untouched — only the turn-by-turn history is cleared,
        because the just-generated cumulative recap now carries that thread forward. The next prompt
        is then persona + adventure + (longer) recap + state + empty history, safely under budget, so
        the persona/adventure are never the truncated head again. ``last_turn`` is also cleared so a
        stale ``!redo`` can't replay a turn that's no longer in history.

        Removes only the messages the matching :meth:`summarize` actually folded into the recap
        (recorded in ``compact_consumed``): a dice-button turn appended to the live list *during*
        the summarize await would otherwise be lost from both the recap and the history (Finding #4).
        With no recorded count (a direct call, not via the auto-compaction) it falls back to a full
        wipe; the count is clamped to the current length in case the list shrank meanwhile.

        The compaction path empties the live list in place: a turn still in flight holds that list
        and appends its pair there, and the recap never saw it (finding 2). Only the direct full
        wipe swaps in a new list."""
        session = self._session(channel_id)
        consumed, session.compact_consumed = session.compact_consumed, None
        if consumed is None:
            session.history = []  # no recorded count → original full-clear behaviour
        else:
            history = session.history
            n = min(consumed, len(history))
            del history[:n]  # keep any turn appended after summarize captured its transcript
        session.last_turn = None

    async def answer_rules(self, question: str, context: str, *, system_name: str) -> str | None:
        """Answer a player's rules question (``!rules <frage>``) in German, grounded ONLY in the
        retrieved rulebook excerpts ``context``. The rulebook is English layout-soup, so the model
        translates + condenses it — but must not invent rules (golden rule #7): if the excerpts
        don't cover it, it says so. Stateless (no channel history). ``None`` on an empty reply."""
        system = (
            f"Du bist ein Regel-Assistent für das Tabletop-Rollenspiel {system_name}. Beantworte "
            "die Regelfrage des Spielers kurz, klar und auf Deutsch — ausschließlich auf Grundlage "
            "der folgenden Auszüge aus dem (englischen) Regelbuch. Übersetze sinngemäß. Erfinde "
            "keine Regeln und keine Zahlen: Deckt der Text die Frage nicht ab, sag offen, dass das "
            "Regelbuch hier dazu nichts hergibt. Höchstens etwa fünf Sätze."
        )
        user = f"Regelbuch-Auszüge:\n{context}\n\nRegelfrage: {question}"
        raw = await self._client.chat(
            system,
            [{"role": "user", "content": user}],
            options={"temperature": 0.2, "num_predict": 320},
        )
        text = raw.replace("*", "").strip()
        return _ROLE_LABEL.sub("", text).strip() or None

    def reset(self, channel_id: int) -> None:
        """Forget a channel's history and pending lines (e.g. new session)."""
        # Reset in place, field by field: the session object stays, so a line the STT thread
        # buffers during the reset lands in the new buffer. ``known_speakers`` and the replay
        # capture are deliberately not touched — they never were.
        session = self._session(channel_id)
        with self._lock:
            session.buffer = []
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
