"""DMbot orchestrator — the DM brain that turns player input into a DM answer (Phase 5).

Wires the LLM layer: buffer the players' transcribed lines per channel, and on a trigger build
the prompt (system persona + running history + the buffered lines), ask Ollama, and return the
German DM answer — while keeping a per-channel conversation history.

Later phases extend the prompt (recap → JSON state → RAG) and add the dice-marker flow; for now
it is persona + history + the latest player turn. Player lines are buffered from the STT worker
thread and read on the event loop, so the buffer is lock-guarded.
"""

from __future__ import annotations

import logging
import re
import threading

from .llm.client import OllamaClient
from .llm.persona import load_system_prompt

log = logging.getLogger(__name__)

# Models sometimes prefix a "Spielleitung:" label or wrap text in markdown bold despite the
# prompt; that would be read out literally by TTS, so strip it as a safety net.
_ROLE_LABEL = re.compile(
    r"^\s*(spielleit(?:ung|er)|erzähler|sl|dm|gm|game ?master)\s*:\s*", re.IGNORECASE
)
# Small models (nemo) like to open with a meta-preamble despite the persona forbidding it —
# "Als Spielleitung beschreibe ich: …" — which would be read aloud verbatim. Strip a leading
# "Als <rolle> …:" too (bounded so it can't eat real narration that merely starts with "Als").
_META_PREAMBLE = re.compile(
    r"^\s*als\s+(?:die\s+)?(?:spielleit(?:ung|er)|erzähler|gm|dm|game ?master)\b[^:\n]{0,60}:\s*",
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


def _sanitize(text: str) -> str:
    text = text.replace("*", "").strip()  # drop markdown emphasis/bold
    text = _ROLE_LABEL.sub("", text).strip()  # drop a leading role label
    text = _META_PREAMBLE.sub("", text).strip()  # drop a leading "Als Spielleitung …:" preamble
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
        max_history_turns: int = 20,
        num_predict: int = 220,
        max_buffer_lines: int = 8,
    ) -> None:
        self._client = client
        self._num_predict = num_predict  # hard cap on a turn's length (spoken aloud — keep it tight)
        self._max_messages = max_history_turns * 2  # a turn = one user + one assistant message
        # Continuous transcription (no wake word) buffers table talk + jokes between !dm presses;
        # sending the whole pile drowns the real action. Keep only the most recent lines so the
        # latest intent dominates. 0 = unbounded. Tunable via DM_MAX_LINES.
        self._max_buffer_lines = max_buffer_lines
        self._history: dict[int, list[dict[str, str]]] = {}
        self._buffer: dict[int, list[tuple[str, str]]] = {}
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
        if not lines:
            return None

        user_msg = "\n".join(f"{name}: {text}" for name, text in lines)
        history = self._history.setdefault(channel_id, [])
        messages = [*history, {"role": "user", "content": user_msg}]

        # Stop the model before it starts a new speaker line (a fabricated player reply or a
        # second DM turn); the cut + sanitize are the safety net if a stop slips through.
        labels = [name for name, _ in lines] + _ROLE_LABELS
        options = {"stop": [f"\n{label}:" for label in labels], "num_predict": self._num_predict}
        raw = await self._client.chat(load_system_prompt(), messages, options=options)
        answer = _sanitize(_cut_at_labels(raw, labels)) or _sanitize(raw)
        answer = _strip_leading_label(answer, labels)  # kill a leaked leading "Name:"/"DM:" label
        answer = _trim_to_last_sentence(answer)  # clean ending if the num_predict cap cut it off

        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:  # keep the tail; recaps will cover the rest later
            del history[: len(history) - self._max_messages]
        return answer

    def reset(self, channel_id: int) -> None:
        """Forget a channel's history and pending lines (e.g. new session)."""
        with self._lock:
            self._buffer.pop(channel_id, None)
        self._history.pop(channel_id, None)

    async def aclose(self) -> None:
        await self._client.aclose()
