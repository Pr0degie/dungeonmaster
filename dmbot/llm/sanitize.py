"""Spoken-answer sanitisers — strip the small-model tics that would otherwise be read aloud.

Pure, regex-only (no project deps) so it stays unit-testable and an agent tuning these German-text
guards loads ~130 focused lines, not the whole orchestrator. Extracted from ``orchestrator.py``
(ADR 034); ``finalize_answer`` (still in orchestrator) and the streaming assembler call these.
Covers a leading role label / markdown / self-correction frame / "Als Spielleitung beschreibe
ich …" preamble (:func:`_sanitize_leading`), a trailing meta-disclaimer / "Was tut ihr?" closer
(:func:`_sanitize_trailing`), mid-text speaker-label truncation (:func:`_cut_at_labels`), a leaked
leading label (:func:`_strip_leading_label`), and a mid-sentence-cut fallback
(:func:`_trim_to_last_sentence`).
"""

from __future__ import annotations

import re


# Models sometimes prefix a "Spielleitung:" label or wrap text in markdown bold despite the
# prompt; that would be read out literally by TTS, so strip it as a safety net.
_ROLE_LABEL = re.compile(
    r"^\s*(spielleit(?:ung|er)|erzähler|sl|dm|gm|game ?master)\s*:\s*", re.IGNORECASE
)
# Small models (nemo) open with a self-referential meta-preamble despite the persona forbidding it —
# "Als Spielleitung beschreibe ich: …", but also colon-less forms read aloud verbatim:
# "Als Spielleitung beschreibe ich die Szene, wie …" / "… beschreibe ich eine dunkle Gasse …", and
# the !intro opener "Als Spielleitung beginne ich die Sitzung: …" (D84 — the brief forbids it but
# nemo writes it anyway, so strip it deterministically). Match "Als <rolle> <verb> ich" + an optional
# object + an optional connector, then strip. The "<verb> ich" anchor keeps it from eating real
# narration (the DM never says "ich" of itself — "Als der Inquisitor eintrifft …" doesn't match).
_META_PREAMBLE = re.compile(
    r"^\s*als\s+(?:die\s+)?(?:spielleit(?:ung|er)|erzähler|gm|dm|game ?master)\s+"
    r"(?:beschreib\w*|schilder\w*|erzähl\w*|sag\w*|gebe?|beginn\w*|eröffn\w*|er ?öffn\w*|start\w*|leite?)\s+ich\b"
    r"(?:\s+(?:dir|euch|(?:die|eine|folgende|unsere|heutige)\s+(?:szene|sitzung|runde|spielrunde)))?"
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


# A single pair of quotes wrapping the WHOLE answer (open char → close char). nemo sometimes renders
# an entire !intro monologue as one quotation ("…" / „…"), which TTS would read as "Anführungszeichen"
# and which also blocks the trailing-prompt strip (the text then ends '…?"' instead of '…?'). D84.
_ENCLOSING_QUOTES = (('"', '"'), ('„', '"'), ('“', '”'), ('»', '«'))


def _unwrap_enclosing_quotes(text: str) -> str:
    """Drop one pair of quotes that encloses the ENTIRE answer. Only strips a clean single envelope
    — the first char opens and the last closes a known pair AND that closing char doesn't recur
    inside — so an answer that merely *contains* a quotation (e.g. an NPC line) is untouched."""
    t = text.strip()
    if len(t) < 2:
        return text
    for open_q, close_q in _ENCLOSING_QUOTES:
        if t[0] == open_q and t[-1] == close_q and close_q not in t[1:-1]:
            return t[1:-1].strip()
    return text


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
    # leading (incl. the meta-preamble that may precede an enclosing quote) → unwrap a whole-answer
    # "…" envelope → trailing (so the now-unblocked "Was tut ihr?" closer strips). D84.
    return _sanitize_trailing(_unwrap_enclosing_quotes(_sanitize_leading(text)))


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
