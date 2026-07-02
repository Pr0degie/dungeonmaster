"""Test-marker parsing (ADR 004) — turns the LLM's ``<<TEST …>>`` request into structured data.

The DM narrates and, when a roll is due, emits a machine-readable marker the model can produce
more reliably than strict JSON. Grammar (tolerant):

    <<TEST <skill> [<difficulty>|±N] [für <name>]>>

e.g. ``<<TEST Wahrnehmung Schwer für Tobi>>`` or ``<<TEST Heimlichkeit +10>>``. The difficulty
is a word from the active profile's ladder (the *number* stays in code — golden rule #2); an
explicit ``±N`` is accepted as a manual override. ``für``/``for`` names the player/character.

:func:`extract_tests` returns the narration with markers removed (so TTS never reads them aloud)
plus the parsed requests. An unparseable ``<<TEST …>>`` is still stripped and yields a generic
manual request (``parsed=False``), so a dice button appears and the flow never breaks (ADR 004
fallback). Pure + profile-driven, unit-tested without Discord.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .profile import SystemProfile

# Match the keyword then take everything up to ``>>`` as the payload. A ``\b`` boundary after the
# keyword would *reject* a glued id — ``<<ORT1>>``, ``<<ORTmud_gate>>``, ``<<TEST1>>``,
# ``<<MANIFESTSmite>>`` — so the marker would survive into the spoken text AND the test/manifest/
# scene action would never fire. Instead consume any whitespace/colon separator after the keyword
# (zero or more, so the glued form matches too) and capture the rest. ``_``/``-`` are NOT swallowed
# here: a leading ``-N`` on a TEST is a modifier, not a separator; the parsers strip a leading
# ``_``/``-`` only where it is unambiguously an id separator (scenes). No other keyword shares a
# prefix in this grammar, so capturing the remainder can't eat a different word.
_MARKER_RE = re.compile(r"<<\s*TEST[\s:]*(.*?)>>", re.IGNORECASE | re.DOTALL)
_MANIFEST_RE = re.compile(r"<<\s*MANIFEST[\s:]*(.*?)>>", re.IGNORECASE | re.DOTALL)
_ORT_RE = re.compile(r"<<\s*ORT[\s:]*(.*?)>>", re.IGNORECASE | re.DOTALL)
_ERLEDIGT_RE = re.compile(r"<<\s*ERLEDIGT[\s:]*(.*?)>>", re.IGNORECASE | re.DOTALL)
_FUER_RE = re.compile(r"\b(?:für|fuer|for)\b", re.IGNORECASE)
_MOD_RE = re.compile(r"([+\-−]\s*\d+)")  # ASCII +/- and the unicode minus the LLM may emit
_PUSH_RE = re.compile(r"\b(?:push|gepusht|pushen)\b", re.IGNORECASE)  # Pushing a Manifest Test


@dataclass(frozen=True, slots=True)
class TestRequest:
    """A parsed (or fallback) test request from a DM turn."""

    skill: str
    difficulty: str | None = None   # a ladder word, resolved against the profile later
    modifier: int | None = None     # explicit ±N override (wins over difficulty)
    target_name: str | None = None  # player/character named after "für"
    raw: str = ""                   # the original marker text
    parsed: bool = True             # False → unparseable; show a generic manual button


def _difficulty_phrases(profile: SystemProfile) -> list[str]:
    """Known difficulty phrases (ladder labels + aliases), longest first so multi-word
    phrases like 'sehr schwer' match before 'schwer'."""
    phrases = list(profile.difficulty_ladder) + list(profile.difficulty_aliases)
    return sorted({p.lower() for p in phrases}, key=lambda p: len(p.split()), reverse=True)


def _split_trailing_difficulty(text: str, phrases: list[str]) -> tuple[str, str | None]:
    """Peel a trailing difficulty phrase off ``text``; return (skill, difficulty|None)."""
    words = text.split()
    for phrase in phrases:
        plen = len(phrase.split())
        if plen <= len(words) and " ".join(words[-plen:]).lower() == phrase:
            return " ".join(words[:-plen]).strip(), " ".join(words[-plen:])
    return text.strip(), None


def _parse_one(inner: str, profile: SystemProfile, raw: str) -> TestRequest:
    body = inner.strip()
    target_name: str | None = None
    m = _FUER_RE.search(body)
    if m:
        target_name = body[m.end():].strip(" :.-") or None
        body = body[: m.start()].strip()

    modifier: int | None = None
    mod_m = _MOD_RE.search(body)
    if mod_m:
        modifier = int(mod_m.group(1).replace(" ", "").replace("−", "-"))
        body = (body[: mod_m.start()] + body[mod_m.end():]).strip()

    difficulty: str | None = None
    if modifier is None:
        body, difficulty = _split_trailing_difficulty(body, _difficulty_phrases(profile))

    skill = re.sub(r"\s{2,}", " ", body).strip(" :,-")
    if not skill:
        return TestRequest(skill="", target_name=target_name, raw=raw, parsed=False)
    return TestRequest(
        skill=skill, difficulty=difficulty, modifier=modifier,
        target_name=target_name, raw=raw, parsed=True,
    )


def _clean(text: str) -> str:
    """Tidy narration after markers are removed: collapse spaces, fix space-before-punctuation."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Public alias: the streaming assembler's no-marker fast path applies the same tidy as the three
# extractors do (each ends in ``_clean``), so it can skip the regex marker scans on a ``<<``-free
# buffer while keeping the spoken text byte-identical. Idempotent, so re-cleaning is harmless.
clean_narration = _clean


def extract_tests(text: str, profile: SystemProfile) -> tuple[str, list[TestRequest]]:
    """Strip every ``<<TEST …>>`` from ``text`` and return (clean narration, parsed requests)."""
    requests = [_parse_one(m.group(1), profile, m.group(0)) for m in _MARKER_RE.finditer(text)]
    clean = _clean(_MARKER_RE.sub("", text))
    return clean, requests


@dataclass(frozen=True, slots=True)
class ManifestRequest:
    """A parsed (or fallback) psychic-power Manifest request from a DM turn (ADR 022).

    Grammar (tolerant): ``<<MANIFEST <power> [für <name>] [push]>>``, e.g.
    ``<<MANIFEST Smite für Mortn>>`` or ``<<MANIFEST Seal Wounds für Mortn push>>``. The power
    name is matched against the active profile's catalog when resolved; the difficulty + Warp
    Rating stay in code (golden rule #2)."""

    power: str
    target_name: str | None = None  # the psyker named after "für"
    pushed: bool = False            # the psyker Pushed the Manifest Test
    raw: str = ""
    parsed: bool = True


def _parse_manifest(inner: str, profile: SystemProfile, raw: str) -> ManifestRequest:
    body = inner.strip()
    target_name: str | None = None
    m = _FUER_RE.search(body)
    if m:
        target_name = body[m.end():].strip(" :.-") or None
        body = body[: m.start()].strip()

    pushed = False
    push_m = _PUSH_RE.search(body)
    if push_m:  # "push" may sit before or after "für …"; strip it from wherever it lands
        pushed = True
        body = (body[: push_m.start()] + body[push_m.end():]).strip()
    # also allow a trailing "push" that ended up in the target name (e.g. "Mortn push")
    if target_name:
        t_push = _PUSH_RE.search(target_name)
        if t_push:
            pushed = True
            target_name = _PUSH_RE.sub("", target_name).strip(" :.-") or None

    power = re.sub(r"\s{2,}", " ", body).strip(" :,-")
    if not power:
        return ManifestRequest(power="", target_name=target_name, pushed=pushed, raw=raw, parsed=False)
    return ManifestRequest(power=power, target_name=target_name, pushed=pushed, raw=raw, parsed=True)


def extract_manifests(text: str, profile: SystemProfile) -> tuple[str, list[ManifestRequest]]:
    """Strip every ``<<MANIFEST …>>`` from ``text`` and return (clean narration, parsed requests)."""
    requests = [_parse_manifest(m.group(1), profile, m.group(0)) for m in _MANIFEST_RE.finditer(text)]
    clean = _clean(_MANIFEST_RE.sub("", text))
    return clean, requests


@dataclass(frozen=True, slots=True)
class SceneRequest:
    """A parsed scene-transition request from a DM turn (ADR 026, auto scene transitions).

    Grammar: ``<<ORT <scene-id>>>``, e.g. ``<<ORT mud_gate>>`` — the model *requests* a move to a
    connected location; code validates the id against the adventure (and the current scene's
    ``leads_to``) and performs the deterministic pointer move (golden rule #3). The model never
    writes scene state directly, exactly as it never rolls its own dice (golden rule #2).

    This extractor is **profile-free** on purpose: scenes belong to the *adventure*, not the rules
    profile, so validation happens where the adventure lives (the cog), not here."""

    scene_id: str
    raw: str = ""          # the original marker text
    parsed: bool = True    # False → empty/garbled marker; stripped but ignored


def extract_scenes(text: str) -> tuple[str, list[SceneRequest]]:
    """Strip every ``<<ORT …>>`` from ``text`` and return (clean narration, parsed requests).

    Like the test/manifest extractors, markers are removed so TTS never reads them aloud; an empty
    ``<<ORT >>`` is still stripped and yields a ``parsed=False`` request the cog ignores."""
    requests: list[SceneRequest] = []
    for m in _ORT_RE.finditer(text):
        # Strip a leading ``_``/``-`` separator too (``<<ORT_mud>>`` / ``<<ORT-mud>>`` glued forms),
        # not just spaces/colons — an id never *starts* with a separator, so this only peels the glue.
        scene_id = re.sub(r"\s{2,}", " ", m.group(1)).strip(" :,-_")
        requests.append(SceneRequest(scene_id=scene_id, raw=m.group(0), parsed=bool(scene_id)))
    clean = _clean(_ORT_RE.sub("", text))
    return clean, requests


@dataclass(frozen=True, slots=True)
class ErledigtRequest:
    """A parsed scene-element flag request from a DM turn (ADR 043, stateful scene cards).

    Grammar: ``<<ERLEDIGT <element-id>>>``, e.g. ``<<ERLEDIGT opp-1>>`` — the model *requests*
    marking an opportunity/secret of the current scene resolved; code validates the id against
    the scene card and applies the flag (golden rule #3). Unlike ``<<ORT>>`` (one move per turn),
    every valid flag in a turn is processed — flags are idempotent and low-stakes.

    Profile-free like :class:`SceneRequest`: elements belong to the *adventure*, so validation
    happens where the adventure lives (the delivery pipeline), not here."""

    element_id: str
    raw: str = ""          # the original marker text
    parsed: bool = True    # False → empty/garbled marker; stripped but ignored


def extract_erledigt(text: str) -> tuple[str, list[ErledigtRequest]]:
    """Strip every ``<<ERLEDIGT …>>`` from ``text`` and return (clean narration, parsed requests).

    Same glue tolerance as ``extract_scenes``: a leading ``_``/``-`` separator is peeled too, so
    the glued forms (``<<ERLEDIGTopp-1>>``, ``<<ERLEDIGT_geh-2>>``) still parse and never reach TTS.
    Note the trailing strip means an element id must not *end* in ``-``/``_`` (derived ids are
    digit-final, so always safe)."""
    requests: list[ErledigtRequest] = []
    for m in _ERLEDIGT_RE.finditer(text):
        element_id = re.sub(r"\s{2,}", " ", m.group(1)).strip(" :,-_")
        requests.append(ErledigtRequest(element_id=element_id, raw=m.group(0), parsed=bool(element_id)))
    clean = _clean(_ERLEDIGT_RE.sub("", text))
    return clean, requests
