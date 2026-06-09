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
import re
import threading

from .llm.client import OllamaClient
from .llm.persona import load_system_prompt
from .llm.roll_router import classifier_schema, classifier_system, to_test_request
from .memory.recap import RECAP_SYSTEM_DE, build_recap_user
from .rules.marker import TestRequest, extract_tests
from .rules.profile import SystemProfile

log = logging.getLogger(__name__)

# Models sometimes prefix a "Spielleitung:" label or wrap text in markdown bold despite the
# prompt; that would be read out literally by TTS, so strip it as a safety net.
_ROLE_LABEL = re.compile(
    r"^\s*(spielleit(?:ung|er)|erzähler|sl|dm|gm|game ?master)\s*:\s*", re.IGNORECASE
)
# Small models (nemo) open with a self-referential meta-preamble despite the persona forbidding it —
# "Als Spielleitung beschreibe ich: …", but also colon-less forms read aloud verbatim:
# "Als Spielleitung beschreibe ich die Szene, wie …" / "… beschreibe ich eine dunkle Gasse …".
# Match "Als <rolle> <describe-verb> ich" + an optional object + an optional connector, then strip.
# The "<verb> ich" anchor keeps it from eating real narration (the DM never says "ich" of itself).
_META_PREAMBLE = re.compile(
    r"^\s*als\s+(?:die\s+)?(?:spielleit(?:ung|er)|erzähler|gm|dm|game ?master)\s+"
    r"(?:beschreib\w*|schilder\w*|erzähl\w*|sag\w*|gebe?)\s+ich\b"
    r"(?:\s+(?:dir|euch|die\s+szene|eine\s+szene|folgende\s+szene))?"
    # zero+ connector words ("so", "wie", "folgendermaßen", …), each maybe after a ":"/"," — so
    # "… beschreibe ich die Szene so:" strips fully instead of leaving a stray "So:" (seen live).
    r"(?:\s*[:,]?\s*(?:so|folgenderma(?:ß|ss)en|wie\s+folgt|wie|dass|in\s+der|in\s+dem))*"
    r"\s*[:,]?\s*",
    re.IGNORECASE,
)
# Small models echo their own instructions as a trailing parenthetical ("(Bitte beachte, dass ich
# keine Repliken der Spielenden erfinde …)") that TTS would read aloud. Strip a trailing "(…)" only
# when it carries meta-language, so a genuine in-fiction aside ("(ein Schuss fällt)") survives.
_META_PAREN = re.compile(
    r"\s*\((?=[^)]*\b(?:beachte|repliken|spielleit\w*|spielenden|figuren|erfinde\w*|entscheid\w*|"
    r"transkri\w*|hinweis|anmerk\w*|na ?repl)\b)[^)]*\)\s*$",
    re.IGNORECASE,
)
# nemo ends almost every turn with a generic "Was tut ihr?" / "Was tust du?" prompt despite the
# persona asking it not to. Strip a *trailing* generic action-prompt question (a real mid-scene
# question or an NPC's question doesn't match these verbs and survives).
_TRAILING_PROMPT = re.compile(
    r"\s*Was\s+(?:tust\s+du|tut\s+ihr|macht\s+ihr|unternehmt\s+ihr|"
    r"(?:möchtet|wollt|werdet)\s+ihr(?:\s+tun)?)\b[^?]*\?\s*$",
    re.IGNORECASE,
)
# Generic role labels small models like to keep talking as / for. Combined with the player
# names this turn, they become both Ollama stop sequences and a post-hoc truncation guard
# against the model fabricating player replies and playing several turns itself.
_ROLE_LABELS = ["Spielleitung", "Spielleiter", "Spieler", "Erzähler", "GM", "DM"]


def _cut_at_labels(text: str, labels: list[str]) -> str:
    """Truncate at the first ``<label>:`` after the start — where the model began inventing a
    next speaker (a player reply or another DM turn). Position 0 (a leading label) is left for
    :func:`_strip_leading_label`."""
    cut = len(text)
    for label in labels:
        idx = text.find(f"{label}:")
        if 0 < idx < cut:
            cut = idx
    return text[:cut].strip()


def _strip_leading_label(text: str, labels: list[str]) -> str:
    """Strip a single leading ``<label>:`` the model emits when it answers **as** a player
    ("SezBoss69: …") or relabels itself — ``_cut_at_labels`` only cuts labels *mid*-text, and the
    ``\\n<label>:`` stop sequence misses a label with no preceding newline. Only the turn's own
    labels (player names this turn + the generic role labels) are stripped, case-insensitively, so
    real narration that merely contains a colon is untouched."""
    for label in labels:
        prefix = f"{label}:"
        if text[: len(prefix)].lower() == prefix.lower():
            return text[len(prefix):].lstrip()
    return text


def _strip_meta_preamble(text: str) -> str:
    """Drop a leading "Als Spielleitung beschreibe ich …" preamble (with or without a colon) and
    re-capitalise the narration that follows, so it isn't read aloud verbatim."""
    m = _META_PREAMBLE.match(text)
    if not m or m.end() == 0:
        return text
    rest = text[m.end():].lstrip()
    return rest[0].upper() + rest[1:] if rest else text


def _strip_trailing_prompt(text: str) -> str:
    """Drop a trailing generic "Was tut ihr?"/"Was tust du?" closing question — nemo tacks one on
    almost every turn despite the persona. Only the *trailing* generic form goes (a real mid-scene
    or NPC question survives), and never strips the answer down to nothing."""
    stripped = _TRAILING_PROMPT.sub("", text).strip()
    return stripped or text


def _sanitize(text: str) -> str:
    text = text.replace("*", "").strip()  # drop markdown emphasis/bold
    text = _ROLE_LABEL.sub("", text).strip()  # drop a leading role label
    text = _strip_meta_preamble(text)  # drop a leading "Als Spielleitung beschreibe ich …" preamble
    text = _META_PAREN.sub("", text).strip()  # drop a trailing meta-disclaimer in parentheses
    text = _strip_trailing_prompt(text)  # drop a repetitive trailing "Was tut ihr?" closer
    return text


# Sentence-ending punctuation, optionally followed by a closing quote/bracket.
_SENTENCE_END = re.compile(r"[.!?…](?:[\"»”’)\]]+)?(?=\s|$)")


def _trim_to_last_sentence(text: str) -> str:
    """If a turn was cut mid-sentence (it hit the ``num_predict`` cap), drop the dangling
    fragment so TTS doesn't read half a sentence aloud. Only trims when there *is* a complete
    sentence to fall back to and real text follows it; a fully-punctuated answer is unchanged."""
    ends = list(_SENTENCE_END.finditer(text))
    if not ends:
        return text  # nothing to fall back to — leave it rather than nuke the whole turn
    last = ends[-1].end()
    return text[:last].strip() if text[last:].strip() else text


class DMBrain:
    """Per-channel history + a pending-player-lines buffer, driving one Ollama client."""

    def __init__(
        self,
        client: OllamaClient,
        *,
        profile: SystemProfile | None = None,
        max_history_turns: int = 20,
        num_predict: int = 220,
        max_buffer_lines: int = 8,
    ) -> None:
        self._client = client
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
        self._history: dict[int, list[dict[str, str]]] = {}
        self._buffer: dict[int, list[tuple[str, str]]] = {}
        # Pending dice tests parsed from the last DM turn (per channel) — the cog drains these and
        # posts a dice button for each. Test results fed back in (engine roll → narrate consequence)
        # are buffered here and prepended to the next turn, exempt from the player-line cap.
        self._pending_tests: dict[int, list[TestRequest]] = {}
        self._test_results: dict[int, list[str]] = {}
        # A light "who plays whom" hint (display name → character) appended to the system prompt,
        # so the model stops confusing player and character names (open item F). Set per channel.
        self._alias_hint: dict[int, str] = {}
        # Memory (Phase 9): the stored session recap + a compact world-state block, injected into the
        # system prompt after the persona (CLAUDE.md order: core → tone → recap → JSON state →
        # history). Set per channel by the cog from the world state, refreshed when state changes.
        self._recap: dict[int, str] = {}
        self._state_summary: dict[int, str] = {}
        # The last turn's (user_msg, labels) per channel, so !redo can re-generate it when the DM
        # misunderstood — same input, a fresh answer that replaces the last one in history.
        self._last_turn: dict[int, tuple[str, list[str]]] = {}
        # The last player action (name, text) consumed per channel — the roll-detection router
        # (ADR 014) classifies it after the narration turn. None when a turn had no player line
        # (e.g. a test-result feedback turn), so the router skips it.
        self._last_action: dict[int, tuple[str, str] | None] = {}
        self._lock = threading.Lock()  # buffer written from STT thread, read on event loop

    def add_player_line(self, channel_id: int, name: str, text: str) -> None:
        """Buffer a transcribed player line for the next DM turn (STT thread-safe)."""
        with self._lock:
            self._buffer.setdefault(channel_id, []).append((name, text))

    def pending_count(self, channel_id: int) -> int:
        with self._lock:
            return len(self._buffer.get(channel_id, []))

    def _drain(self, channel_id: int) -> list[tuple[str, str]]:
        with self._lock:
            lines = self._buffer.get(channel_id, [])
            self._buffer[channel_id] = []
            return lines

    async def respond(
        self, channel_id: int, *, extra_text: str | None = None
    ) -> str | None:
        """Run one DM turn for ``channel_id``: consume the buffered player lines (plus any
        directly typed ``extra_text``), ask the LLM, append to history and return the answer.
        Returns ``None`` if there is nothing to respond to.
        """
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

        # Remember the latest player action for the roll-detection router (ADR 014); None on a
        # results-only turn so the router doesn't re-fire on a stale action after a dice roll.
        self._last_action[channel_id] = lines[-1] if lines else None

        # Result lines (engine rolls) lead, then the player lines — both as context for this turn.
        parts = [f"[Würfel] {r}" for r in results]
        parts += [f"{name}: {text}" for name, text in lines]
        user_msg = "\n".join(parts)
        # Labels (player names this turn + generic roles) become Ollama stop sequences and the
        # post-hoc truncation guard against the model fabricating replies / playing several turns.
        labels = [name for name, _ in lines] + _ROLE_LABELS
        self._last_turn[channel_id] = (user_msg, labels)

        history = self._history.setdefault(channel_id, [])
        answer = await self._generate(channel_id, user_msg, labels, history)
        self._append_turn(history, user_msg, answer)
        return answer

    async def redo(self, channel_id: int) -> str | None:
        """Re-generate the **last** DM turn (same player input, a fresh answer) — for when the DM
        misunderstood. Drops the previous answer + its user turn from history first, so the new one
        replaces it rather than stacking. ``None`` if there is no turn to redo yet."""
        last = self._last_turn.get(channel_id)
        if last is None:
            return None
        user_msg, labels = last
        history = self._history.setdefault(channel_id, [])
        if (
            len(history) >= 2
            and history[-1]["role"] == "assistant"
            and history[-2]["role"] == "user"
        ):
            del history[-2:]  # drop the turn we're redoing so it isn't duplicated
        self._pending_tests.pop(channel_id, None)  # the redo supersedes the old turn's test markers
        answer = await self._generate(channel_id, user_msg, labels, history)
        self._append_turn(history, user_msg, answer)
        return answer

    async def _generate(
        self,
        channel_id: int,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
    ) -> str:
        """One LLM call for ``user_msg`` on top of ``history_prefix`` → a sanitised DM answer.

        With an active profile, ``<<TEST …>>`` markers are extracted **before** the last-sentence
        trim (the trim would otherwise drop a trailing marker) and surfaced as pending tests."""
        system = load_system_prompt()
        # Memory (Phase 9), in the CLAUDE.md prompt order: persona (core+tone) → recap → JSON state →
        # who-plays-whom → history. The recap is the narrative thread; the state block the hard facts.
        recap = self._recap.get(channel_id)
        if recap:
            system = f"{system}\n\n## Was bisher geschah\n{recap}"
        state_summary = self._state_summary.get(channel_id)
        if state_summary:
            system = f"{system}\n\n{state_summary}"
        hint = self._alias_hint.get(channel_id)
        if hint:
            system = f"{system}\n\n{hint}"
        messages = [*history_prefix, {"role": "user", "content": user_msg}]
        options = {"stop": [f"\n{label}:" for label in labels], "num_predict": self._num_predict}
        raw = await self._client.chat(system, messages, options=options)
        # Debug aid (lands in debug.log only — 🪵 is filtered off the console + terminal mirror):
        # the raw LLM output BEFORE marker-stripping, so we can see whether the model emitted a
        # <<TEST …>> marker at all (the prime suspect when the dice-marker flow doesn't fire).
        log.info("🪵 LLM roh: %s", raw.replace("\n", " ⏎ "))
        answer = _sanitize(_cut_at_labels(raw, labels)) or _sanitize(raw)
        answer = _strip_leading_label(answer, labels)  # kill a leaked leading "Name:"/"DM:" label
        if self._profile is not None:
            answer, tests = extract_tests(answer, self._profile)  # strip markers, collect requests
            if tests:
                self._pending_tests.setdefault(channel_id, []).extend(tests)
        return _trim_to_last_sentence(answer)  # clean ending if the num_predict cap cut it off

    def _append_turn(self, history: list[dict[str, str]], user_msg: str, answer: str) -> None:
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:  # keep the tail; recaps will cover the rest later
            del history[: len(history) - self._max_messages]

    def take_pending_tests(self, channel_id: int) -> list[TestRequest]:
        """Return and clear the dice tests the last DM turn requested (cog posts the buttons)."""
        return self._pending_tests.pop(channel_id, [])

    def last_action(self, channel_id: int) -> tuple[str, str] | None:
        """The latest player action (display-name, text) the last turn answered, or None — the
        roll-detection router (ADR 014) classifies this. None on a results-only turn."""
        return self._last_action.get(channel_id)

    async def classify_test(
        self, *, action: str, character: str | None, skills: list[str]
    ) -> TestRequest | None:
        """Roll-detection router (ADR 014): a separate, stateless, constrained-JSON LLM call that
        decides whether ``action`` needs a test and which skill/difficulty — instead of trusting the
        narration model's inline marker. ``skills`` constrains the choice to the acting character's
        sheet. Returns a TestRequest (target_name = ``character``) or None. Never raises."""
        if self._profile is None or not action.strip():
            return None
        difficulties = list(self._profile.difficulty_ladder)
        schema = classifier_schema(skills, difficulties)
        system = classifier_system(
            skills, difficulties, self._profile.display_name or self._profile.name
        )
        try:
            raw = await self._client.chat(
                system,
                [{"role": "user", "content": f"Spieler-Handlung: {action}"}],
                options={"temperature": 0, "num_predict": 80},
                format=schema,
            )
            data = json.loads(raw)
        except Exception:
            log.exception("roll-router classification failed")
            return None
        return to_test_request(data, character=character)

    def add_test_result(self, channel_id: int, line: str) -> None:
        """Buffer a rolled test result (a German summary line) to feed the next turn so the DM
        narrates its consequence (architecture §9: 'back into the next prompt')."""
        self._test_results.setdefault(channel_id, []).append(line)

    def _drain_test_results(self, channel_id: int) -> list[str]:
        return self._test_results.pop(channel_id, [])

    def set_alias_hint(self, channel_id: int, hint: str) -> None:
        """Set (or clear, with '') the 'who plays whom' hint appended to this channel's prompt."""
        if hint:
            self._alias_hint[channel_id] = hint
        else:
            self._alias_hint.pop(channel_id, None)

    def set_context(self, channel_id: int, *, recap: str = "", state_summary: str = "") -> None:
        """Set the memory context injected into this channel's prompt (Phase 9): the stored recap
        (narrative thread) and the compact world-state block (hard facts). Empty strings clear them.
        The cog calls this on join (from the loaded state) and after every state change."""
        if recap:
            self._recap[channel_id] = recap
        else:
            self._recap.pop(channel_id, None)
        if state_summary:
            self._state_summary[channel_id] = state_summary
        else:
            self._state_summary.pop(channel_id, None)

    async def summarize(self, channel_id: int) -> str | None:
        """Produce a German "Was bisher geschah" recap from this channel's history (the `wrap up`
        trigger, D14). Code stores the returned string in the world state; this only generates it.
        ``None`` if there's no history to summarise."""
        history = self._history.get(channel_id) or []
        if not history:
            return None
        user = build_recap_user(history)
        raw = await self._client.chat(
            RECAP_SYSTEM_DE,
            [{"role": "user", "content": user}],
            options={"temperature": 0.3, "num_predict": 400},
        )
        # Light cleanup only (no marker/test stripping — a recap has none): drop markdown + a leading
        # role label the model might prepend.
        text = raw.replace("*", "").strip()
        return _ROLE_LABEL.sub("", text).strip() or None

    def reset(self, channel_id: int) -> None:
        """Forget a channel's history and pending lines (e.g. new session)."""
        with self._lock:
            self._buffer.pop(channel_id, None)
        self._history.pop(channel_id, None)
        self._last_turn.pop(channel_id, None)
        self._pending_tests.pop(channel_id, None)
        self._test_results.pop(channel_id, None)
        self._last_action.pop(channel_id, None)
        self._alias_hint.pop(channel_id, None)
        self._recap.pop(channel_id, None)
        self._state_summary.pop(channel_id, None)

    async def aclose(self) -> None:
        await self._client.aclose()
