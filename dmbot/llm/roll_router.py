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

from ..rules.marker import TestRequest


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
        f"Schwierigkeit nur aus: {diff_list} (Standard: die mittlere/herausfordernde).\n"
        "Wenn keine Probe nötig: needs_test=false, skill und difficulty leer. Antworte NUR mit JSON."
    )


def should_post_router(router_on: bool, marker_posted: int) -> bool:
    """Dedupe the two roll-trigger paths (D40): an inline ``<<TEST>>`` marker the model emitted
    (already posted, ``marker_posted`` > 0) **wins**, so the router stays silent — at most one dice
    button per action. The router only fills in when the router is on and the model emitted none."""
    return router_on and marker_posted == 0


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
