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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .llm.client import OllamaClient
from .llm.persona import load_system_prompt
from .llm.roll_router import classifier_schema, classifier_system, to_test_request
from .memory.recap import RECAP_SYSTEM_DE, build_recap_user
from .rules.marker import TestRequest, extract_tests
from .rules.profile import SystemProfile
from .tts.textsplit import has_speakable_content, split_completed

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
# Small models sometimes break the fiction to "correct themselves" out loud — they narrate, then
# "Nein, warte kurz. Das ist ein Meta-Kommentar von mir als Sprachmodell … Hier ist die korrekte
# Antwort: <echte Erzählung>". Drop everything up to such a self-correction frame so only the real
# narration is spoken (the frame admits to being an AI — exactly what must never be read aloud).
_META_SELFCORRECT = re.compile(
    r"^.*?\bHier ist die (?:korrekte|richtige)\b[^:]*:\s*",
    re.IGNORECASE | re.DOTALL,
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


def _sanitize_leading(text: str) -> str:
    """The leading/global half of :func:`_sanitize`: drop markdown, a self-correction frame, a
    leading role label and a leading meta-preamble. Split out so the streaming assembler (ADR 017)
    can apply it incrementally *without* the trailing strips, which only ever touch the held-back
    last sentence."""
    text = text.replace("*", "").replace("`", "").strip()  # drop markdown bold + code-fence backticks
    text = _META_SELFCORRECT.sub("", text, count=1).strip()  # drop a "…Sprachmodell… Hier ist die korrekte Antwort:" frame
    text = _ROLE_LABEL.sub("", text).strip()  # drop a leading role label
    text = _strip_meta_preamble(text)  # drop a leading "Als Spielleitung beschreibe ich …" preamble
    return text


def _sanitize_trailing(text: str) -> str:
    """The trailing half of :func:`_sanitize`: drop a trailing meta-disclaimer parenthetical and a
    repetitive trailing 'Was tut ihr?' closer. Applied last, on the final/held-back sentence."""
    text = _META_PAREN.sub("", text).strip()  # drop a trailing meta-disclaimer in parentheses
    text = _strip_trailing_prompt(text)  # drop a repetitive trailing "Was tut ihr?" closer
    return text


def _sanitize(text: str) -> str:
    return _sanitize_trailing(_sanitize_leading(text))


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


def finalize_answer(
    raw: str, labels: list[str], profile: SystemProfile | None
) -> tuple[str, list[TestRequest]]:
    """The full non-streaming post-processing of a raw LLM answer → (clean spoken answer, parsed
    dice tests). The single source of truth shared by the batch path (:meth:`DMBrain._generate`)
    and the streaming assembler's :meth:`StreamAssembler.finish` — so the two can never drift and
    the stored history is identical for the same raw text (the parity guarantee, ADR 017)."""
    answer = _sanitize(_cut_at_labels(raw, labels)) or _sanitize(raw)
    answer = _strip_leading_label(answer, labels)  # kill a leaked leading "Name:"/"DM:" label
    tests: list[TestRequest] = []
    if profile is not None:
        answer, tests = extract_tests(answer, profile)  # strip markers, collect requests
    return _trim_to_last_sentence(answer), tests


# --- Echo guard (D43 / ADR 018) ------------------------------------------------------------------

# Appended to the retry prompt when the model parroted a player line instead of narrating.
_ECHO_NUDGE = (
    "Antworte als Spielleitung: Beschreibe, was daraufhin in der Szene geschieht, "
    "und wiederhole nicht die Worte der Spielenden."
)

# Explicit directive on a results-only (post-roll) turn — without it the model sees a bare
# "[Würfel] …" line and tends to predict the *next player line* instead of narrating (seen live
# 2026-06-12: three identical echo turns poisoned the history).
_ROLL_DIRECTIVE = (
    "Beschreibe als Spielleitung kurz die Folgen dieses Würfelergebnisses in der Szene."
)


def _normalize_echo(text: str) -> str:
    """Case/punctuation-insensitive view for the echo comparison."""
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def is_echo(answer: str, user_msg: str) -> bool:
    """True when ``answer`` merely parrots a line of this turn's ``user_msg`` — the model
    predicted the next table line ("Pr0degie: Ich greife den Kultisten an.") instead of narrating.
    Once such an echo lands in history it self-reinforces, so the caller retries/suppresses.
    Compares each user line (with and without its ``Name:``/``[Würfel] …:`` lead) normalized;
    an echo is an exact match, the answer being a fragment of the line, or the line covering
    ≥90% of the answer. Lines under 10 normalized chars never count (too short to call)."""
    norm_answer = _normalize_echo(answer)
    if not norm_answer:
        return False
    for line in user_msg.splitlines():
        body = line.split(":", 1)[1] if ":" in line else line
        for candidate in (line, body):
            norm_line = _normalize_echo(candidate)
            if len(norm_line) < 10:
                continue
            if (
                norm_answer == norm_line
                or norm_answer in norm_line
                or (norm_line in norm_answer and len(norm_line) >= 0.9 * len(norm_answer))
            ):
                return True
    return False


# --- Streaming assembler (ADR 017) --------------------------------------------------------------

# Hold the first chunk until it's a full sentence or this many chars, so a leading meta-preamble /
# role label is strippable before anything is spoken.
_FIRST_CHUNK_MIN_CHARS = 80


def _open_marker_index(text: str) -> int | None:
    """Index of an *unclosed* ``<<`` (a ``<<TEST …>>`` marker still arriving), or None — so the
    streaming view can withhold the dangling marker fragment and never speak a partial ``<<``."""
    i = text.rfind("<<")
    if i == -1 or ">>" in text[i:]:
        return None
    return i


@dataclass
class StreamResult:
    """Outcome of :meth:`StreamAssembler.finish`: sentences not yet spoken, the canonical stored
    answer (history parity), and the dice tests parsed from the whole turn."""

    remaining: list[str]
    answer: str
    tests: list[TestRequest]


class StreamAssembler:
    """Turns a stream of raw LLM deltas into speakable sentences while preserving the *exact*
    non-streaming sanitisation (ADR 017). Pure + unit-testable against a list of fake deltas.

    Hold-back rules:
    - the **first** sentence is withheld until it's complete (one sentence or ``_FIRST_CHUNK_MIN_CHARS``
      chars) so a leading meta-preamble / role label is strippable before anything is spoken;
    - the **latest** completed sentence is always held back (emit N only when N+1 exists) so the
      trailing strips (parenthetical, 'Was tut ihr?', mid-word cut) apply before it's spoken;
    - text is withheld from any unmatched ``<<`` — a ``<<TEST …>>`` marker may span deltas;
    - a mid-text speaker label (``_cut_at_labels``) sets :attr:`stopped` so the caller aborts the
      HTTP stream and only the pre-label narration is kept.

    :meth:`finish` recomputes the answer with :func:`finalize_answer` on the accumulated raw, so
    history parity holds by construction; ``remaining`` is whatever of that answer wasn't spoken.
    """

    def __init__(self, labels: list[str], profile: SystemProfile | None) -> None:
        self._labels = labels
        self._profile = profile
        self._raw = ""
        self._released = False
        self._emitted: list[str] = []
        self.stopped = False

    @property
    def raw(self) -> str:
        return self._raw

    def feed(self, delta: str) -> list[str]:
        """Accumulate ``delta`` and return any newly-speakable sentences (already sanitised)."""
        if self.stopped:
            return []
        self._raw += delta
        cut = _cut_at_labels(self._raw, self._labels)
        if len(cut) < len(self._raw.strip()):
            self.stopped = True  # a speaker label appeared mid-text → caller aborts the stream
        body = self._body(cut)
        if body is None:
            return []
        sentences, _tail = split_completed(body)
        emittable = sentences[:-1] if sentences else []  # hold back the latest completed sentence
        new = emittable[len(self._emitted):]
        self._emitted.extend(new)
        return new

    def _body(self, cut: str) -> str | None:
        """The leading-sanitised, marker-stripped speakable view of the cut buffer, or None while
        the first chunk is still being held back."""
        text = cut.replace("*", "")
        idx = _open_marker_index(text)
        if idx is not None:
            text = text[:idx]  # withhold from an unmatched "<<" (a marker may span deltas)
        if self._profile is not None:
            text, _ = extract_tests(text, self._profile)  # strip complete <<TEST …>> markers
        text = _sanitize_leading(text)
        text = _strip_leading_label(text, self._labels)
        if not self._released:
            sentences, _tail = split_completed(text)
            if not sentences and len(text) < _FIRST_CHUNK_MIN_CHARS:
                return None
            self._released = True
        return text

    def finish(self) -> StreamResult:
        """Stream ended (or aborted): compute the canonical answer + tests and return whatever of
        it hasn't been spoken yet (the held-back tail / final sentence)."""
        answer, tests = finalize_answer(self._raw, self._labels, self._profile)
        sentences, tail = split_completed(answer)
        all_sentences = [s for s in (*sentences, tail) if s]
        if all_sentences[: len(self._emitted)] == self._emitted:
            remaining = all_sentences[len(self._emitted):]
        else:
            # The canonical answer diverged from what we already spoke — only the rare mid-text
            # self-correction frame ("Hier ist die korrekte Antwort: …") or a stop-label edit can
            # do this. Speak the canonical remainder so the real answer is still heard; history
            # already stores the canonical text, so parity is intact.
            log.warning(
                "streaming: spoken text diverged from the finalized answer (self-correction / "
                "stop-label) — speaking the canonical remainder; %d sentences already spoken",
                len(self._emitted),
            )
            remaining = all_sentences
        return StreamResult(remaining=remaining, answer=answer, tests=tests)


class DMBrain:
    """Per-channel history + a pending-player-lines buffer, driving one Ollama client."""

    def __init__(
        self,
        client: OllamaClient,
        *,
        profile: SystemProfile | None = None,
        max_history_turns: int = 20,
        num_predict: int = 160,
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
        # Every character + player name at the table (CharacterStore.speaker_labels). They join the
        # turn's own speakers as cut-labels + stop sequences (see _generate / respond), so a puppeted
        # "Seskin: …"/"Pr0degie: …" script the model tacks on is truncated — the deterministic guard
        # behind the persona's no-puppeting rule (the live fix; nemo ignores the soft rule).
        self._known_speakers: dict[int, list[str]] = {}
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
        # Token stats (prompt_eval_count / eval_count / num_ctx) from the most recent *narration*
        # call — set only by _generate (respond/redo), so the router's classify_test and summarize
        # calls don't overwrite it. The cog reads it right after respond()/redo() for the [latency]
        # line. None until the first turn.
        self.last_llm_stats: dict | None = None

    @property
    def max_history_turns(self) -> int:
        """How many turns the in-memory history keeps — used to bound the autosave restore (D41)."""
        return self._max_messages // 2

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

        # Remember the latest player action for the roll-detection router (ADR 014); None on a
        # results-only turn so the router doesn't re-fire on a stale action after a dice roll.
        self._last_action[channel_id] = lines[-1] if lines else None

        # Result lines (engine rolls) lead, then the player lines — both as context for this turn.
        parts = [f"[Würfel] {r}" for r in results]
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
        known = self._known_speakers.get(channel_id, [])
        labels = list(dict.fromkeys([name for name, _ in lines] + known + _ROLE_LABELS))
        self._last_turn[channel_id] = (user_msg, labels)
        history = self._history.setdefault(channel_id, [])
        return user_msg, labels, history

    async def respond(
        self, channel_id: int, *, extra_text: str | None = None
    ) -> str | None:
        """Run one DM turn for ``channel_id``: consume the buffered player lines (plus any
        directly typed ``extra_text``), ask the LLM, append to history and return the answer.
        Returns ``None`` if there is nothing to respond to.
        """
        prep = self._prepare_turn(channel_id, extra_text)
        if prep is None:
            return None
        user_msg, labels, history = prep
        answer = await self._generate(channel_id, user_msg, labels, history)
        if answer is None:
            return ""  # echo-suppressed (D43): content-less to the cog, the pair stays out of history
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
        if answer is None:
            return ""  # echo-suppressed (D43): content-less to the cog, the pair stays out of history
        self._append_turn(history, user_msg, answer)
        return answer

    def _build_request(
        self,
        channel_id: int,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]], dict]:
        """Assemble ``(system, messages, options)`` for one DM turn — the shared head both the
        batch (:meth:`_generate`) and streaming (:meth:`_stream_and_store`) paths use, so they
        can't drift. Memory order per CLAUDE.md: persona (core+tone) → recap → JSON state →
        who-plays-whom → history. Labels become Ollama stop sequences (the anti-puppeting guard)."""
        system = load_system_prompt()
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
        return system, messages, options

    async def _chat_once(
        self,
        channel_id: int,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
    ) -> tuple[str, list[TestRequest]]:
        """One non-streaming LLM call for ``user_msg`` on top of ``history_prefix`` → (sanitised
        answer, parsed dice tests). The raw building block of :meth:`_generate` (which wraps the
        echo-guard retry around it) and of the streaming path's echo retry."""
        system, messages, options = self._build_request(channel_id, user_msg, labels, history_prefix)
        raw = await self._client.chat(system, messages, options=options)
        # narration call's token counts (for [latency]); getattr so a test double without the attr
        # (or a future client) degrades to None instead of raising.
        self.last_llm_stats = getattr(self._client, "last_stats", None)
        # Debug aid (lands in debug.log only — 🪵 is filtered off the console + terminal mirror):
        # the raw LLM output BEFORE marker-stripping, so we can see whether the model emitted a
        # <<TEST …>> marker at all (the prime suspect when the dice-marker flow doesn't fire).
        log.info("🪵 LLM roh: %s", raw.replace("\n", " ⏎ "))
        return finalize_answer(raw, labels, self._profile)

    async def _generate(
        self,
        channel_id: int,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
    ) -> str | None:
        """One DM answer for ``user_msg`` with the echo guard (D43/ADR 018): if the answer merely
        parrots a player line, retry once with a corrective nudge; if the retry parrots again,
        return ``None`` so the caller suppresses the turn entirely (nothing spoken, nothing
        stored — an echo in history self-reinforces, seen live 2026-06-12)."""
        answer, tests = await self._chat_once(channel_id, user_msg, labels, history_prefix)
        if answer and is_echo(answer, user_msg):
            log.warning("echo guard: answer parrots a player line (%r) — retrying once", answer)
            nudged = f"{user_msg}\n{_ECHO_NUDGE}"
            answer, tests = await self._chat_once(channel_id, nudged, labels, history_prefix)
            if answer and is_echo(answer, user_msg):
                log.warning("echo guard: the retry parroted again — suppressing the turn")
                return None
        # Suppress inline <<TEST>> markers on a results-only (post-roll consequence) turn — a
        # consequence narration must not request a NEW roll or the dice loop never ends (seen live).
        if tests and self._last_action.get(channel_id) is not None:
            self._pending_tests.setdefault(channel_id, []).extend(tests)
        return answer

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
        prep = self._prepare_turn(channel_id, extra_text)
        if prep is None:
            return None
        user_msg, labels, history = prep
        return await self._stream_and_store(
            channel_id, user_msg, labels, history, on_sentence, should_abort
        )

    async def redo_streaming(
        self,
        channel_id: int,
        *,
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None = None,
    ) -> str | None:
        """Streaming variant of :meth:`redo`: re-stream the last turn's input, replacing (not
        stacking) the previous answer in history."""
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
        return await self._stream_and_store(
            channel_id, user_msg, labels, history, on_sentence, should_abort
        )

    async def _stream_and_store(
        self,
        channel_id: int,
        user_msg: str,
        labels: list[str],
        history: list[dict[str, str]],
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None,
    ) -> str:
        """Drive ``chat_stream`` through a :class:`StreamAssembler`, speaking sentences via
        ``on_sentence`` as they're ready, then finalise: store the canonical answer (parity with
        the batch path), surface pending tests, set the latency stats. Degrades on a mid-stream
        error — keeps what was spoken, marks the stored answer, never raises out of a half-spoken
        turn."""
        system, messages, options = self._build_request(channel_id, user_msg, labels, history)
        assembler = StreamAssembler(labels, self._profile)
        errored = False
        spoke_any = False
        agen = self._client.chat_stream(system, messages, options=options)
        try:
            async for delta in agen:
                for sentence in assembler.feed(delta):
                    if has_speakable_content(sentence):  # skip a lone "."/quote/backtick (don't synth it)
                        await on_sentence(sentence)
                        spoke_any = True
                if assembler.stopped:
                    break  # a mid-text speaker label — abort the stream, keep the narration
                if should_abort is not None and should_abort():
                    break  # paused (ADR 013): stop emitting; resume won't replay
        except Exception:
            log.exception("streaming turn failed mid-generation — keeping the partial answer")
            errored = True
        finally:
            await agen.aclose()  # closes the httpx stream (the client-side stop)
        self.last_llm_stats = getattr(self._client, "last_stats", None)
        log.info("🪵 LLM roh (stream): %s", assembler.raw.replace("\n", " ⏎ "))
        result = assembler.finish()
        answer, tests, remaining = result.answer, result.tests, list(result.remaining)
        suppressed = False
        # Echo guard (D43/ADR 018). Only when nothing was spoken yet — an echo is a short single
        # sentence the assembler held back; a half-spoken turn is never retried. The retry is a
        # plain batch call: corrective rare path, the answer is short anyway.
        if not errored and not spoke_any and answer and is_echo(answer, user_msg):
            log.warning("echo guard (stream): answer parrots a player line (%r) — retrying once", answer)
            nudged = f"{user_msg}\n{_ECHO_NUDGE}"
            try:
                answer, tests = await self._chat_once(channel_id, nudged, labels, history)
            except Exception:
                log.exception("echo-guard retry failed — suppressing the turn")
                answer, tests = "", []
            if answer and is_echo(answer, user_msg):
                log.warning("echo guard: the retry parroted again — suppressing the turn")
                answer, tests = "", []
            suppressed = not answer
            remaining = [answer] if answer else []
        for sentence in remaining:
            if should_abort is not None and should_abort():
                break
            if has_speakable_content(sentence):
                await on_sentence(sentence)
        # Suppress inline <<TEST>> markers on a results-only (post-roll consequence) turn — a
        # consequence narration must not request a NEW roll or the dice loop never ends (seen live).
        if tests and self._last_action.get(channel_id) is not None:
            self._pending_tests.setdefault(channel_id, []).extend(tests)
        stored = answer
        if errored and stored:
            stored = f"{stored} … [Antwort unterbrochen]"  # noted in history; never spoken
        if not suppressed:
            self._append_turn(history, user_msg, stored)
        return answer

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

    def last_user_msg(self, channel_id: int) -> str | None:
        """The user message of the most recent turn (for history autosave, D41), or None."""
        last = self._last_turn.get(channel_id)
        return last[0] if last else None

    def restore_history(self, channel_id: int, turns: list[tuple[str, str]]) -> int:
        """Restore prior ``(user_msg, answer)`` turns into this channel's history on join — crash
        recovery (D41). Only fills an **empty** history (never clobbers a live session) and respects
        the history cap. Returns how many turns were restored. Note: ``_last_turn`` is *not*
        restored, so ``!redo`` is unavailable for the restored last turn (known limitation)."""
        if self._history.get(channel_id):
            return 0
        history: list[dict[str, str]] = []
        for user_msg, answer in turns:
            if not answer.strip():
                continue  # marker-only/suppressed turns: don't re-teach empty answers on restore (D43)
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:
            history = history[len(history) - self._max_messages:]
        self._history[channel_id] = history
        return len(history) // 2

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

    def set_known_speakers(self, channel_id: int, names: list[str]) -> None:
        """Register every character + player name at the table (CharacterStore.speaker_labels). They
        join the turn's own speakers as cut-labels + stop sequences, so a puppeted "Seskin: …" /
        "Pr0degie: …" script the model appends is truncated — the deterministic backstop to the
        persona's no-puppeting rule. An empty list clears it."""
        if names:
            self._known_speakers[channel_id] = list(names)
        else:
            self._known_speakers.pop(channel_id, None)

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
