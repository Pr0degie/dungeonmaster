"""Roll-detection router (ADR 014).

A separate, stateless classifier pass that decides whether a player's action needs a dice test —
and which skill + difficulty — instead of relying on the narration model to emit an inline
``<<TEST …>>`` marker. Narrative models are documented to skip checks ("yes, you succeed");
crucially this is **not** a model-size limit — the same 12B that self-resolves in narration nails the
classification when it is a separate, structured step (verified: nemo 8/8 on a held-out set). So the
story model just tells the story; this small constrained-JSON call routes the mechanic to the engine.

Pure prompt/schema/parse helpers live here (unit-tested without the LLM); the actual call is wired in
:meth:`dmbot.orchestrator.DMBrain.classify_test`. Behind ``DM_ROLL_ROUTER`` (off by default); the
inline ``<<TEST>>`` marker stays as a fallback.
"""

from __future__ import annotations

import re

from ..rules.marker import TestRequest

# A turn that opens with a subordinating "dass"/"weil" is the tail of something the player said in
# character ("[sag ihnen,] dass wir das Ossarium suchen."), not a declared action. Deliberately
# narrow: "wenn"/"ob" can open a real conditional action ("Wenn er sich umdreht, schleiche ich …").
_CONTINUATION = re.compile(r"^\s*(?:dass|daß|weil)\b", re.IGNORECASE)


def classifier_schema(skills: list[str], difficulties: list[str]) -> dict:
    """JSON schema that constrains the verdict: a bool + a skill/difficulty from the allowed sets
    (empty string = none), so the model can't invent an off-list skill (gemma3's one slip)."""
    return {
        "type": "object",
        "properties": {
            "needs_test": {"type": "boolean"},
            "skill": {"type": "string", "enum": [*skills, ""]},
            "difficulty": {"type": "string", "enum": [*difficulties, ""]},
        },
        "required": ["needs_test", "skill", "difficulty"],
    }


def classifier_system(skills: list[str], difficulties: list[str], system_display: str) -> str:
    """The classifier's (tiny, stateless) system prompt — German, no narration, no history."""
    skill_list = ", ".join(skills) or "—"
    diff_list = ", ".join(difficulties) or "—"
    return (
        f"Du bist der Regel-Assistent für das Rollenspiel {system_display}.\n"
        "Entscheide für die zuletzt genannte Spieler-Handlung, ob sie eine Probe (Würfelwurf) erfordert.\n"
        "- Probe nötig, wenn der Ausgang unsicher ist (schleichen, wahrnehmen, überreden, klettern, "
        "kämpfen, eine Lüge erkennen, ein Schloss knacken …).\n"
        "- KEINE Probe bei trivialen/sicheren Handlungen (gehen, eine offene Tür öffnen, normal reden) "
        "oder bei reinem Tischgespräch.\n"
        f"Fertigkeit nur aus dieser Liste: {skill_list}.\n"
        f"Schwierigkeit nur aus: {diff_list}. Wähle sie nach der Lage, die die Handlung nennt: "
        "leichter bei einem Vorteil (aus nächster Nähe, wehrloses oder überraschtes Ziel, gute "
        "Vorbereitung, ein williges Gegenüber); schwerer nur bei einem klaren Nachteil (Dunkelheit, "
        "Deckung, große Entfernung, Fesseln, Hast). Die mittlere nur, wenn nichts leichter oder "
        "schwerer macht.\n"
        "Wenn keine Probe nötig: needs_test=false, skill und difficulty leer. Antworte NUR mit JSON."
    )


def roll_button_source(router_on: bool, marker_count: int) -> str:
    """Which path posts this turn's dice button — ``"router"`` | ``"marker"`` | ``"none"``.
    Flips D40's dedupe (D43/ADR 018): when the router is on, the **router wins** and the model's
    inline ``<<TEST>>`` requests are discarded — the constrained classifier picks reliable skills
    (ADR 014: 8/8), the narration model doesn't (seen live: ``<<TEST Heimlichkeit>>`` for an
    attack). Markers are the fallback only when the router is off. At most one button per action.
    On a Claude-narrated turn :func:`marker_decides` comes first (D140): a valid marker wins."""
    if router_on:
        return "router"
    return "marker" if marker_count else "none"


def marker_decides(narration_stats: dict | None) -> bool:
    """Does the narration model's inline ``<<TEST>>`` decide this turn's test (D140)?

    Yes when Claude narrated the turn: Opus judges the moment, the stateless classifier sees one
    player line (live 2026-11-14: one marker nine turns running, the router said "no test"
    every time). The narrator comes from the turn's stats — the failover names the side that
    answered the prose call — so a Nemo turn (``fallback``, ``!backend ollama``) and the
    Ollama-only bot (no ``backend`` key) keep D43: the router wins."""
    return (narration_stats or {}).get("backend") == "claude"


def marker_key(character: str | None, skill: str | None) -> tuple[str, str]:
    """``(character, skill)`` lower-cased — what makes two turns' markers "the same request"."""
    return ((character or "").strip().lower(), (skill or "").strip().lower())


class MarkerRepeats:
    """The repeat safety net (D140), per channel: the marker requests the previous turn left
    unrolled. A narration model that asks for the same character + skill turn after turn waits
    for a roll that never comes and re-narrates the undecided moment; the second time the
    marker is honoured even where the router said "no test". Any roll resets the channel."""

    def __init__(self) -> None:
        self._last: dict[int, set[tuple[str, str]]] = {}

    def turn(self, channel_id: int, keys: set[tuple[str, str]]) -> set[tuple[str, str]]:
        """Record this turn's unrolled marker ``keys``; return the ones the previous turn had too."""
        repeated = keys & self._last.get(channel_id, set())
        self._last[channel_id] = set(keys)
        return repeated

    def rolled(self, channel_id: int) -> None:
        """A die was rolled in the channel: the moment is decided, the chain starts over."""
        self._last.pop(channel_id, None)


def to_test_request(data: object, *, character: str | None) -> TestRequest | None:
    """Turn the classifier's parsed JSON into a :class:`TestRequest` (or ``None`` for no test)."""
    if not isinstance(data, dict) or not data.get("needs_test"):
        return None
    skill = str(data.get("skill") or "").strip()
    if not skill:
        return None
    difficulty = str(data.get("difficulty") or "").strip() or None
    return TestRequest(
        skill=skill, difficulty=difficulty, target_name=character, raw="[router]", parsed=True
    )


def is_continuation_fragment(action: str) -> bool:
    """Is ``action`` only a reported-speech / reasoning fragment (no test to classify)?

    Otherwise "dass wir das Osadium suchen." reads as a search — a Wahrnehmung test for a
    sentence that was talk (D121)."""
    return bool(_CONTINUATION.match(action or ""))


def superseded_by_manifest(character: str | None, *, manifesting: set[str]) -> bool:
    """Should the router's test for ``character`` be dropped because they manifest this turn?

    A power is rolled through its Manifest Test (ADR 022), and that is the character's roll for
    the action. Any skill counts, not only the manifest skill — a second router test on another
    skill ("Fel" for Dread Presence) is just as much a double roll (D121, D123). ``manifesting``
    holds the lower-cased names of the
    characters with a Manifest request this turn."""
    return bool(character) and character.strip().lower() in manifesting
