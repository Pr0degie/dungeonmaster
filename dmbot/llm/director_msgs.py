"""GM-side "director" instructions for the opening turns (pure prompt text).

Extracted from ``orchestrator.py`` (ADR 034). :func:`build_opening_director_msg` drives the short
``!start`` briefing; :func:`build_intro_director_msg` drives the longer ``!intro`` monologue
(ADR 031) and embeds the party roster. The DM never reads these aloud — they instruct the model to
OPEN the session. The cog (``dmcog.py``) imports these; nothing in ``DMBrain`` calls them (it
receives the resulting ``director_msg`` as a parameter).

D107 (`docs/plans/coherent-campaign-run.md`) reshaped the intro brief. It used to ask for a
personal *moment* per player character, which is exactly what ``prompts/dm_core_de.md``
forbids three blocks earlier; live (2026-08-22, findings A3/B5) the DM answered that by giving
all four figures dialogue and motives nobody had declared. The roster still rides along, but it
now feeds an *introduction from the outside* — appearance, trade, reputation — and the brief
spells out that no figure speaks, thinks or acts. The same round split the opening in two:
plain language first (who/where/what/why-now, no jargon), atmosphere after (findings A1/A9/A11),
optionally built on an opening text the adventure ships (``briefing_de``).
"""

from __future__ import annotations

from collections.abc import Sequence


# --- Opening briefing (!start) ------------------------------------------------------------------

# The director instruction that drives the !start opening turn. It is a GM-side ("director")
# message, NOT a player line: it tells the model to OPEN the session out loud so the table knows
# who they are and what their mission is (the first-session complaint: the bot "hat am Anfang
# nicht gesagt, was abgeht"). The concrete content — the Halikarn briefing, the three leads — is
# NOT spelled out here: it lives in the start scene's card (## Aktuelle Szene + guidance_de),
# which the system prompt already carries. So this only has to point the model at that scene and
# hold it to the persona's voice. Phrased as an instruction to the GM, never read aloud.
OPENING_DIRECTOR_MSG = (
    "[Regie] Eröffne jetzt die Sitzung: Spiele die Auftrags-/Eröffnungsszene aus deiner "
    "aktuellen Szene. Mach den Spielenden klar, wer sie sind und was ihr Auftrag ist, und "
    "deute die ersten Spuren über ein Detail der Umgebung an — nicht als Aufzählung. Halte "
    "dich an die Spielleitungs-Stimme (2–4 Sätze). Verlange keine Probe."
)


def build_opening_director_msg() -> str:
    """The GM-side director instruction for the ``!start`` opening turn (pure, unit-testable).

    Kept as a function so the cog never inlines the prompt text and a test can assert its shape
    (it must read as a GM/director instruction, not as a player action, and must forbid a dice
    test on the briefing)."""
    return OPENING_DIRECTOR_MSG


# --- Intro monologue (!intro) ------------------------------------------------------------------

# The director instruction for the one-time !intro opening MONOLOGUE (ADR 031). Unlike the short
# !start briefing (OPENING_DIRECTOR_MSG, 2-4 sentences), this asks for one coherent opening monologue
# in TWO parts: plain language first (where they are, who they are, what they want, why it is
# urgent), atmosphere after. The concrete adventure content lives in the start scene's card + the
# adventure summary already in the system prompt; an adventure that ships its own opening text hands
# it in as ``briefing_de``, and the party roster is embedded here (both ride in the turn's user
# message, so the ADR-019 prompt order is untouched). GM-side instruction, never read aloud.
_INTRO_DIRECTOR_HEAD = (
    "[Regie] Eröffne jetzt die Sitzung mit einem zusammenhängenden Eröffnungs-Monolog "
    "(mehrere Absätze, kein Aufzählen, keine Stichpunkte). Beginne sofort als Erzähler mitten "
    "in der Szene — schreibe NICHT, dass du die Sitzung eröffnest oder was du als Spielleitung "
    "gerade tust, und kündige den Monolog nicht an. Der Auftakt hat zwei Teile, in genau dieser "
    "Reihenfolge.\n\n"
    "ERSTER TEIL — Klartext, bevor irgendeine Stimmung kommt: Sag in wenigen schlichten Sätzen, "
    "die ein Mensch ohne jedes Vorwissen über diese Welt sofort versteht, wo die Gruppe gerade "
    "ist, wer sie ist und warum sie zusammen unterwegs ist, was sie erreichen will und warum es "
    "eilt — welche Frist läuft und was geschieht, wenn sie verstreicht. Beschreibe das Ziel der "
    "Gruppe so greifbar, dass man es sich vorstellen kann (Größe, Material, Aussehen, wozu es gut "
    "ist), nicht bloß mit seinem Namen. Sprich hier in Alltagssprache; brauchst du doch einen "
    "Fachbegriff dieser Welt, erklär ihn im selben Satz mit drei, vier gewöhnlichen Worten. Du "
    "bleibst dabei Erzähler in der Szene und sagst nicht, dass du gerade etwas erklärst.\n\n"
    "ZWEITER TEIL — erst jetzt die Atmosphäre: Male den Ort aus, wie er sich anfühlt, riecht und "
    "klingt, und wie die Gruppe hergekommen ist; stütz dich dabei auf deine aktuelle Szene und die "
    "Abenteuer-Zusammenfassung."
)
# Used only when the adventure ships its own opening text: the plain-language part is then spoken
# from that text instead of being invented (D107). The loader passes the field in; this module only
# defines the parameter.
_INTRO_DIRECTOR_BRIEFING = (
    "Für den ERSTEN TEIL bringt das Abenteuer einen eigenen Einstiegstext mit. Nimm ihn als "
    "Grundlage, statt dir selbst etwas auszudenken: sprich ihn flüssig in deiner Erzählstimme, "
    "halte dich inhaltlich genau daran und füg nichts hinzu, was nicht darin steht.\n\n{briefing}"
)
# The figures are INTRODUCED, not played (D107). Everything the roster carries is background for
# describing them from the outside; the prohibition is spelled out here because this is where the
# 2026-08-22 run broke it.
_INTRO_DIRECTOR_CHARS = (
    "Stelle im ZWEITEN TEIL jede der folgenden Figuren kurz vor — von außen, so wie die Übrigen "
    "am Tisch sie sehen: Erscheinung, Haltung, Ausrüstung, Handwerk, Herkunft, ihr Ruf. Nenne jede "
    "dabei beim Namen, damit am Tisch klar ist, wer dabei ist. Aber leg ihnen nichts in den Mund "
    "und nichts in die Hände: keine wörtliche Rede, kein Gedanke, kein Gefühl, keine Handlung, "
    "keine Entscheidung — die Figuren gehören allein ihren Spielenden, und die haben noch nichts "
    "gesagt. Was eine Figur will, deutest du höchstens als sichtbares Zeichen oder als Gerede "
    "anderer an, nie als erklärten Vorsatz; geheime oder rein private Ziele bleiben ungesagt. "
    "Falsch: „Die Enginseerin tritt vor und sagt: ‚Ich übernehme die Schleuse.‘“ "
    "Richtig: „Die Enginseerin steht etwas abseits, die Werkzeugarme unter dem Mantel — im "
    "Distrikt kennt man sie als die, die jede Schleuse wieder zum Laufen bringt.“ "
    "Die Angaben unten sind dein Hintergrundwissen; lies nichts davon wörtlich vor.\n\n{roster}"
)
_INTRO_DIRECTOR_TAIL = (
    "Bleib durchgehend in der Spielleitungs-Stimme und nimm dir Raum — das ist der Auftakt, er "
    "darf deutlich länger sein als ein normaler Zug. Schließ ihn stimmungsvoll ab und lade die "
    "Gruppe in die Szene ein (etwa welche Spur sie zuerst verfolgt); brich nicht nach wenigen "
    "Sätzen mit einer knappen „Was tut ihr?“-Frage ab. Verlange keine Probe."
)


def build_intro_director_msg(roster_de: str = "", briefing_de: str = "") -> str:
    """The GM-side director instruction for the ``!intro`` opening monologue (pure, unit-testable).

    Asks for one coherent opening monologue in two parts — plain language for a newcomer first
    (place, group, goal, why it is urgent), atmosphere after — and INTRODUCES each player figure
    from the outside via the embedded ``roster_de`` block (from ``CharacterStore.intro_roster_de``).
    It never asks the model to speak, think or act for a player figure; that contradiction (and the
    invented player dialogue it produced live) is what D107 removed.

    ``briefing_de`` is the adventure's own opening text, if it ships one: passed in, it becomes the
    basis of the plain-language part instead of the model inventing it. Reading the adventure field
    is the loader's job — this function only takes the text. With both arguments empty the brief
    degrades to the place/mission monologue alone. Kept as a function so the cog never inlines the
    prompt text and a test can assert its shape."""
    msg = _INTRO_DIRECTOR_HEAD
    if briefing_de.strip():
        msg += "\n\n" + _INTRO_DIRECTOR_BRIEFING.format(briefing=briefing_de.strip())
    if roster_de.strip():
        msg += "\n\n" + _INTRO_DIRECTOR_CHARS.format(roster=roster_de.strip())
    msg += "\n\n" + _INTRO_DIRECTOR_TAIL
    return msg


# --- Rejected scene change (ADR 057 #5) ---------------------------------------------------------

# Why the move was refused, in one clause the model can act on. Keys are the *values* of
# :class:`dmbot.rules.scene_flow.MoveRejection` (a str-Enum), so this module needs no import from
# rules/ and a reason the table doesn't know degrades to the generic clause below.
_MOVE_REJECTION_DE: dict[str, str] = {
    "unknown_scene": "diesen Ort gibt es hier nicht",
    "not_connected": "von hier aus kommt die Gruppe dort nicht hin",
    "locked": "dieser Weg ist noch versperrt",
    "same_scene": "dort ist die Gruppe bereits",
    "no_current_scene": "die Gruppe steht gerade in keiner bekannten Szene",
    "no_target": "es wurde kein Ort genannt",
}
_MOVE_REJECTION_FALLBACK_DE = "dieser Wechsel ist nicht möglich"


def scene_rejected_note_de(target: str, reason: object, exits: Sequence[str] = ()) -> str:
    """The one-shot ``[Regie]`` note queued for the NEXT turn when a scene change was refused.

    On 2026-08-22 a rejected move produced a single ``log.info`` line: neither the table nor the
    model ever learned that the world had not followed the narration, so the DM kept describing a
    harbour while the state sat in the customs sacristy. ADR 057 #5 makes it loud — this is the
    model-facing half, queued through the same ``add_gm_note`` path a full clock (ADR 047) and an
    expired deadline (ADR 048) already use.

    ``target`` is the refused destination as it was proposed, ``reason`` a
    :class:`~dmbot.rules.scene_flow.MoveRejection` (or its plain string value), ``exits`` the
    labels of the exits that ARE reachable — ``"id — Titel"`` reads best, since the model has to
    map a fictional direction onto one of them. Pure text; the caller queues it."""
    key = getattr(reason, "value", reason)
    clause = _MOVE_REJECTION_DE.get(str(key or ""), _MOVE_REJECTION_FALLBACK_DE)
    named = f"„{str(target).strip()}“" if str(target).strip() else "der genannte Ort"
    note = (
        f"Die Gruppe ist NICHT nach {named} gelangt — {clause}. Erzähle den nächsten Beitrag so, "
        "dass die Gruppe noch am selben Ort steht, und lass sie merken, warum es dort nicht "
        "weitergeht."
    )
    labels = [str(e).strip() for e in exits if str(e).strip()]
    if labels:
        note += " Von hier aus erreichbar sind nur: " + "; ".join(labels) + "."
    return note
