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
    # "antworte/reagiere/erwidere ich" joined the list live 2026-08-15: asked in-fiction, nemo
    # answered "Als Spielleitung antworte ich: …" and stayed in narrator voice instead of playing
    # the NSC — read aloud verbatim, twice in one session.
    r"(?:beschreib\w*|schilder\w*|erzähl\w*|sag\w*|gebe?|beginn\w*|eröffn\w*|er ?öffn\w*|start\w*|leite?"
    r"|antwort\w*|reagier\w*|erwider\w*|entgegn\w*)\s+ich\b"
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


# The same director frame in the other word order — "In diesem Fall würde ich als Spielleitung
# antworten: …" (read aloud live on 2026-08-22, turn 4). _META_PREAMBLE anchors on
# "Als <rolle> <verb> ich" at the start and cannot see this shape.
_META_WOULD = re.compile(
    r"^[^.!?]{0,60}?\bwürde\s+ich\s+als\s+(?:die\s+)?"
    r"(?:spielleit(?:ung|er)|erzähler|gm|dm|game ?master)\s+"
    r"(?:antwort\w*|sag\w*|beschreib\w*|erzähl\w*|reagier\w*|erwider\w*)\s*[:,]\s*",
    re.IGNORECASE,
)
# --- Meta sentences: assistant register + handover stage directions (D112) ----------------------
#
# The 2026-08-22 run read three kinds of non-fiction aloud. The persona forbids all of them and
# nemo writes them anyway — docs/lessons/deterministic-guards-over-persona-hopes.md: the prompt
# shapes, code removes. Both filters work per SENTENCE and skip any sentence carrying a quote
# character: an NSC may apologise, ask formally or say it is waiting, and that is the game, not a
# chatbot. A sentence without a terminator (one still arriving mid-stream) never matches, so the
# same function is safe on the incremental streaming path.

# Stage directions that hand play back to the table: "Damit übergibt Kaad die Verantwortung wieder
# an die Gruppe.", "Damit endet dein Zug …", "Ich warte darauf, wie die Gruppe reagiert." The verb
# alone is not enough — "Damit endet die Schicht im Hafenbecken." is narration — so a handover
# object is required.
_HANDOVER_SENTENCE = re.compile(
    r"^(?:Damit\s+(?:übergib\w*|übergeb\w*|gib\w*|geb\w*|end\w*|ist|hast|habt|liegt)"
    r"|Ich\s+warte\b|Ich\s+übergebe\b)"
    r"[^.!?]*?"
    r"(?:an\s+die\s+Gruppe|die\s+Gruppe\s+reagiert|die\s+Gruppe\s+entscheidet"
    r"|(?:dein|deinen|ihren|euren|seinen|den)\s+(?:nächsten\s+)?Zug|nächsten\s+Zug"
    r"|das\s+Wort|die\s+Verantwortung|den\s+Ball|nächste\s+Aktion)"
    r"[^.!?]*[.!?]$",
    re.IGNORECASE,
)

# The assistant register: a helpful chatbot apologising, asking a formal follow-up question or
# promising to do better. Every pattern names the speaker as "ich" plus a service phrase, so
# narration *about* an apology ("Der Seneschall entschuldigt sich …") is untouched.
_ASSISTANT_SENTENCE = re.compile(
    r"(?:ich\s+(?:kann|konnte)\s+(?:Ihre|Ihren|deine|eure)\s+(?:Frage|Anfrage|Bitte|Aussage)\b[^.!?]*\bnicht\b"
    r"|es\s+tut\s+mir\s+leid\b[^.!?]*\bich\s+(?:kann|konnte|verstehe)\b[^.!?]*\bnicht\b"
    r"|könnt(?:en)?\s+Sie\s+bitte\b"
    r"|ich\s+entschuldige\s+mich\s+für\b"
    r"|ich\s+werde\s+(?:in\s+Zukunft|künftig|ab\s+jetzt|fortan)\s+darauf\s+achten\b"
    r"|als\s+(?:Sprachmodell|Sprach-Modell|KI|AI)\b"
    r"|ich\s+bin\s+(?:nur\s+)?ein(?:e)?\s+(?:Sprachmodell|KI|Assistent|Assistenz)\w*\b)",
    re.IGNORECASE,
)

# Spoken when a whole answer was nothing but meta. Silence after someone pressed the mic reads as
# a broken bot at the table — this keeps the model's actual intent (I did not follow you) and drops
# only the register. Du/ihr like every other DM line, never the formal "Sie".
META_FALLBACK_DE = "Ich habe das nicht mitbekommen — sagt es noch einmal."

# A quote character anywhere in the sentence means someone is speaking in the fiction: hands off.
_QUOTE_CHARS = "\"'„“”»«‚‘’"

def _sentences(text: str) -> list[str]:
    """Split into sentences by slicing at the ends found by :data:`_SENTENCE_END`.

    Slicing, not ``re.split``: the boundary pattern swallows a closing quote, and a split would
    drop it — an NSC's line would come back missing its final ``"``.
    """
    out: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        out.append(text[start:match.end()])
        start = match.end()
    if text[start:].strip():
        out.append(text[start:])
    return out


def _drop_meta_sentences(text: str) -> str:
    """Drop whole sentences that are assistant register or a handover stage direction (D112).

    Sentence-level and quote-safe, so an NSC apologising or waiting survives. Returns ``""`` when
    the answer was nothing else — the caller decides what to say instead
    (:data:`META_FALLBACK_DE`), because "speak nothing" and "speak a fallback" are different
    decisions at different seams.
    """
    if not text.strip():
        return text
    kept: list[str] = []
    for sentence in _sentences(text):
        stripped = sentence.strip()
        if not stripped:
            continue
        if not any(ch in stripped for ch in _QUOTE_CHARS) and (
            _HANDOVER_SENTENCE.match(stripped) or _ASSISTANT_SENTENCE.search(stripped)
        ):
            continue
        kept.append(stripped)
    return " ".join(kept).strip()


# --- Puppeting: the DM speaks NSCs, never the player characters (D113) --------------------------
#
# On 2026-08-22 the DM put words in the players' mouths — "'Ich sehe hier keine illegalen Waffen',
# sagst du kühl." — and two players called it out at the table. D110 deferred a filter in favour of
# a prompt fix plus measurement; Tobi overrode that, so the rule is enforced in code.
#
# Scope is speech only. A player character *acting* in the narration stays: the line between
# narrating a consequence and steering someone's character is not sharp enough to cut with a
# regex, and a filter that eats real narration costs more than the tic it removes.

# German 2nd-person singular verb forms are unambiguous — "sagst" can only have "du" as its
# subject — so the verb alone identifies the speaker. "ihr" needs its pronoun, because "sagt" is
# also third person ("Kaad sagt").
_SPEECH_VERB_DU = (r"sagst|antwortest|fragst|flüsterst|erwiderst|rufst|entgegnest|murmelst"
                   r"|br(?:ü|ue)llst|zischst|stammelst|erkl(?:ä|ae)rst|befiehlst|wiederholst")
_SPEECH_VERB_3 = (r"sagt|sagte|antwortet|antwortete|fragt|fragte|fl(?:ü|ue)stert|fl(?:ü|ue)sterte"
                  r"|erwidert|erwiderte|ruft|rief|entgegnet|entgegnete|murmelt|murmelte"
                  r"|br(?:ü|ue)llt|zischt|stammelt|erkl(?:ä|ae)rt|meint|meinte|spricht")

_SECOND_PERSON_SPEECH = re.compile(
    rf"\b(?:{_SPEECH_VERB_DU})\b"
    rf"|\bihr\s+(?:{_SPEECH_VERB_3})\b"
    rf"|\b(?:{_SPEECH_VERB_3})\s+ihr\b",
    re.IGNORECASE,
)


def _speaks_as(name: str) -> re.Pattern:
    """Pattern for "<name> … <speech verb>" or "<speech verb> <name>" — an attribution of quoted
    speech to that name, in either German word order."""
    escaped = re.escape(name)
    return re.compile(
        rf"\b{escaped}\b[^\"„“”»«]{{0,40}}?\b(?:{_SPEECH_VERB_3})\b"
        rf"|\b(?:{_SPEECH_VERB_3})\s+(?:\w+\s+){{0,2}}?{escaped}\b",
        re.IGNORECASE,
    )


def _party_variants(labels: list[str]) -> list[str]:
    """Every string that names a player character: the label itself plus its first token, so
    "Fridolin" counts as "Fridolin Feuchtgebietheld". Short tokens are dropped — a three-letter
    fragment matches half the German language."""
    out: list[str] = []
    for label in labels:
        label = (label or "").strip()
        if not label:
            continue
        out.append(label)
        head = re.split(r"[\s\-]+", label)[0]
        if len(head) >= 4 and head != label:
            out.append(head)
    return out


def _drop_puppet_speech(text: str, labels: list[str], *, allow_empty: bool = False) -> str:
    """Drop sentences in which the DM speaks *as* a player character (D113).

    A sentence has to do two things at once to qualify: carry quoted speech, and attribute it to a
    player — either in the second person ("sagst du") or by a name from ``labels`` (the table's
    character and player names, the same roster the anti-puppeting stop sequences use). One alone
    is not enough: "Du fragst dich, ob er lügt." has no quote, and "Kaad mustert Gellicus lange."
    has no speech.

    Never strips a turn down to nothing — silence at the table is worse than the tic, the same
    rule :func:`_strip_trailing_prompt` already follows.

    ``allow_empty`` turns that rule off, and the streaming assembler needs it: it tracks spoken
    sentences by index, so a sentence that survives early (because it was briefly the only one)
    and disappears later would shift the list and skip a line. On the incremental view a dropped
    sentence must stay dropped from the first moment it is complete.
    """
    if not text.strip():
        return text
    speakers = [_speaks_as(name) for name in _party_variants(labels)]
    kept: list[str] = []
    dropped = False
    for sentence in _sentences(text):
        stripped = sentence.strip()
        if not stripped:
            continue
        quoted = any(ch in stripped for ch in _QUOTE_CHARS)
        if quoted and (
            _SECOND_PERSON_SPEECH.search(stripped)
            or any(pattern.search(stripped) for pattern in speakers)
        ):
            dropped = True
            continue
        kept.append(stripped)
    if not dropped:
        return text
    cleaned = " ".join(kept).strip()
    return cleaned if (cleaned or allow_empty) else text


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
    text = _META_WOULD.sub("", text, count=1).strip()  # "In diesem Fall würde ich als SL antworten:"
    text = _drop_meta_sentences(text)  # drop assistant-register + handover stage-direction sentences
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
