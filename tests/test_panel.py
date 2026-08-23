"""The player panel (D107, PRD ``docs/plans/coherent-campaign-run.md``, user stories 14-17):
the pure renderer behind the message the table reads while playing — where we are, what we
want, what time it is, how long we have, what is still open here, who is up, and what the
evening is supposed to exercise, all in players' German.

Everything here is exact-string assertion on a pure function: no Discord, no runtime, no
network. The spoiler test is load-bearing — a scene's ``secrets_de`` and the "(Guter Erfolg:
...)" outcomes of its opportunities must never reach the channel.
"""

from __future__ import annotations

from dmbot.discord_ui.panel import (
    ALL_DONE_DE,
    NO_DEADLINE_DE,
    NO_MISSION_DE,
    NO_SCENE_DE,
    gate_hints_de,
    opportunity_teaser_de,
    render_player_panel_de,
)
from dmbot.memory.state import WorldState
from dmbot.rag.adventure import Scene


# --- fixtures ---------------------------------------------------------------------------------

def _scene() -> Scene:
    return Scene(
        id="zollhaus",
        title_de="Die Zoll-Sakristei",
        part=1,
        description_de="Eine beschlagnahmte Sakristei.",
        npcs_here=["Seneschall Bramwell Kaad"],
        opportunities_de=[
            "Technologie (Routine): Kaads Datentafel die Siegelmeldung entlocken. "
            "(Guter Erfolg: Niemand hat die Diebe aufgehalten.)",
            "Wissen (Routine): Das Zeichen des Kettenbunds erkennen.",
            "Überreden (Herausfordernd): Kaad rückt eine Zollvollmacht heraus.",
        ],
        opportunity_ids=["siegelmeldung", "kettenbund-zeichen", "zollvollmacht"],
        secrets_de=["Kaad verschweigt, WAS im Ossarium liegt."],
        secret_ids=["geh-1"],
        leads_to=["schrein"],
        guidance_de="Kaad nennt den Schrein.",
    )


def _state(**kw) -> WorldState:
    st = WorldState()
    st.scene_id = "zollhaus"
    st.time_minutes = 1260  # Tag 1, 21:00
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def _with_mission() -> WorldState:
    st = _state()
    st.set_mission(
        "Das Ossarium ungeöffnet zurückholen",
        detail="ein bleibeschlagener Knochenkasten",
        given_by="Seneschall Bramwell Kaad",
    )
    return st


# --- the full panel ---------------------------------------------------------------------------

def test_full_panel_renders_every_block_in_order() -> None:
    st = _with_mission()
    st.add_deadline("Mitternachtssirene: Der Leichter legt ab", 180,
                    deadline_id="mitternachtssirene")
    st.mark_resolved("zollhaus", "siegelmeldung")
    panel = render_player_panel_de(
        st, _scene(), ["G1 Regelfrage (RAG)", "G8 Kampf/Wunden"], active_player="Seskin")
    assert panel == (
        "📍 **Wo ihr seid:** Die Zoll-Sakristei\n"
        "🎯 **Was ihr wollt:** Das Ossarium ungeöffnet zurückholen — "
        "ein bleibeschlagener Knochenkasten (von Seneschall Bramwell Kaad)\n"
        "🕐 **Wie spät es ist:** Tag 1, 21:00 (Abend)\n"
        "⏳ **Mitternachtssirene: Der Leichter legt ab** — noch ~3 Std\n"
        "🗣 **Am Zug:** Seskin\n"
        "🔎 **Hier ist noch etwas zu holen:**\n"
        "• eine Probe auf Wissen (Routine)\n"
        "• eine Probe auf Überreden (Herausfordernd)\n"
        "🧪 **Testet in dieser Szene:**\n"
        "• Fragt laut nach einer Regel — die Spielleitung darf im Regelbuch nachschlagen.\n"
        "• Sucht die Auseinandersetzung und würfelt einen Angriff — jemand soll wirklich "
        "Schaden nehmen."
    )


def test_panel_without_turn_order_omits_the_turn_line() -> None:
    panel = render_player_panel_de(_with_mission(), _scene())
    assert "Am Zug" not in panel
    assert "🗣" not in panel


def test_panel_lines_are_stable_under_repeated_rendering() -> None:
    st = _with_mission()
    assert render_player_panel_de(st, _scene()) == render_player_panel_de(st, _scene())


# --- edge case: nothing open any more ---------------------------------------------------------

def test_all_opportunities_resolved_says_move_on() -> None:
    st = _with_mission()
    for eid in ("siegelmeldung", "kettenbund-zeichen", "zollvollmacht"):
        st.mark_resolved("zollhaus", eid)
    panel = render_player_panel_de(st, _scene())
    assert ALL_DONE_DE == "✅ **Hier ist nichts mehr offen — zieht weiter.**"
    assert ALL_DONE_DE in panel
    assert "Hier ist noch etwas zu holen" not in panel
    assert "eine Probe auf" not in panel


def test_scene_without_opportunities_says_move_on_too() -> None:
    bare = Scene(id="zollhaus", title_de="Die Zoll-Sakristei")
    assert ALL_DONE_DE in render_player_panel_de(_with_mission(), bare)


def test_resolved_secret_never_turns_into_an_open_line() -> None:
    # Secret ids live in the same flag list; they must not count as open opportunities.
    st = _with_mission()
    st.mark_resolved("zollhaus", "geh-1")
    panel = render_player_panel_de(st, _scene())
    assert panel.count("• eine Probe auf") == 3


# --- edge case: no deadline -------------------------------------------------------------------

def test_no_deadline_renders_the_explicit_line() -> None:
    panel = render_player_panel_de(_with_mission(), _scene())
    assert NO_DEADLINE_DE == "⏳ Keine laufende Frist."
    assert NO_DEADLINE_DE in panel
    assert "noch ~" not in panel


def test_two_deadlines_render_nearest_first() -> None:
    st = _with_mission()
    st.add_deadline("Die Sirene", 180, deadline_id="sirene")
    st.add_deadline("Die Flut", 45, deadline_id="flut")
    panel = render_player_panel_de(st, _scene())
    assert "⏳ **Die Flut** — noch ~45 Min\n⏳ **Die Sirene** — noch ~3 Std" in panel


def test_expired_deadline_says_so() -> None:
    st = _with_mission()
    st.add_deadline("Die Sirene", 180, deadline_id="sirene")
    st.time_minutes += 200
    assert "⏳ **Die Sirene** — ABGELAUFEN" in render_player_panel_de(st, _scene())


# --- edge case: no mission --------------------------------------------------------------------

def test_unknown_mission_renders_a_prompt_to_ask() -> None:
    panel = render_player_panel_de(_state(), _scene())
    assert NO_MISSION_DE == (
        "🎯 **Was ihr wollt:** noch unklar — fragt nach, wer euch beauftragt hat.")
    assert NO_MISSION_DE in panel


def test_mission_without_detail_renders_only_the_title() -> None:
    st = _state()
    st.set_mission("Das Ossarium zurückholen")
    panel = render_player_panel_de(st, _scene())
    assert "🎯 **Was ihr wollt:** Das Ossarium zurückholen\n" in panel


def test_finished_mission_shows_its_status() -> None:
    st = _with_mission()
    st.set_quest_status("Das Ossarium ungeöffnet zurückholen", "erledigt")
    assert "(von Seneschall Bramwell Kaad) [erledigt]" in render_player_panel_de(st, _scene())


def test_a_side_quest_is_not_mistaken_for_the_mission() -> None:
    st = _state()
    st.add_quest("Bree einen Gefallen schulden")
    assert NO_MISSION_DE in render_player_panel_de(st, _scene())


# --- edge case: no scene ----------------------------------------------------------------------

def test_panel_without_a_scene_still_renders() -> None:
    panel = render_player_panel_de(_with_mission(), None)
    assert NO_SCENE_DE == (
        "📍 **Wo ihr seid:** noch nirgends — die Sitzung hat noch keine Szene.")
    assert panel.startswith(NO_SCENE_DE + "\n")
    assert "Hier ist noch etwas zu holen" not in panel
    assert ALL_DONE_DE not in panel
    assert "🕐 **Wie spät es ist:** Tag 1, 21:00 (Abend)" in panel


# --- edge case: no test plan ------------------------------------------------------------------

def test_no_gates_means_no_test_block() -> None:
    panel = render_player_panel_de(_with_mission(), _scene())
    assert "🧪" not in panel
    assert "Testet in dieser Szene" not in panel


def test_unknown_gate_labels_are_dropped_instead_of_shown_raw() -> None:
    panel = render_player_panel_de(_with_mission(), _scene(), ["G42 Irgendwas", "Freitext"])
    assert "🧪" not in panel
    assert "G42" not in panel and "Freitext" not in panel


def test_gate_jargon_never_reaches_the_panel() -> None:
    panel = render_player_panel_de(
        _with_mission(), _scene(), ["G4 Scene-Card-Gate", "G5 NPC-Gedächtnis (Saat: Lüge)"])
    for jargon in ("G4", "G5", "Scene-Card-Gate", "NPC-Gedächtnis", "Saat"):
        assert jargon not in panel


# --- the gate → player-language mapping -------------------------------------------------------

def test_gate_hints_are_player_language() -> None:
    assert gate_hints_de(["G1 Regelfrage (RAG)"]) == [
        "Fragt laut nach einer Regel — die Spielleitung darf im Regelbuch nachschlagen."]
    assert gate_hints_de(["G3 Zeit & Fristen (Saat)"]) == [
        "Redet über die Zeit: Wie spät ist es, und wie lange bleibt euch noch?"]
    assert gate_hints_de(["G9 Chekhov (Saat 1)"]) == [
        "Merkt euch eine Kleinigkeit am Rand, ohne ihr nachzugehen — sie kommt später wieder."]


def test_the_same_code_can_mean_two_things_and_the_label_decides() -> None:
    combat = ("Sucht die Auseinandersetzung und würfelt einen Angriff — jemand soll wirklich "
              "Schaden nehmen.")
    restart = ("Legt eine Pause ein; wenn die Spielleitung zurück ist, lasst euch erzählen, "
               "was bisher geschah.")
    assert gate_hints_de(["G8 Kampf/Wunden"]) == [combat]
    assert gate_hints_de(["G8 Neustart/Recap"]) == [restart]
    assert gate_hints_de(["G8"]) == [restart]


def test_gate_hints_deduplicate_and_keep_order() -> None:
    assert gate_hints_de([
        "G3 Zeit & Fristen (Saat)",
        "G1 Regelfrage (RAG)",
        "G3 Frist-Ablauf",
    ]) == [
        "Redet über die Zeit: Wie spät ist es, und wie lange bleibt euch noch?",
        "Fragt laut nach einer Regel — die Spielleitung darf im Regelbuch nachschlagen.",
    ]


def test_gate_hints_survive_junk() -> None:
    assert gate_hints_de([]) == []
    assert gate_hints_de(["", "   ", "g1"]) == [
        "Fragt laut nach einer Regel — die Spielleitung darf im Regelbuch nachschlagen."]


def test_no_gate_hint_contains_a_command() -> None:
    every = gate_hints_de([f"G{n}" for n in range(1, 11)] + ["G8 Kampf/Wunden"])
    assert len(every) == 11
    for hint in every:
        assert "!" not in hint
        assert "<<" not in hint


# --- the opportunity teaser (spoiler discipline) ----------------------------------------------

def test_teaser_keeps_only_the_invitation() -> None:
    assert opportunity_teaser_de(
        "Wahrnehmung (Routine): Vosks Gürteltasche birgt den Verladebrief — Pier Neun."
    ) == "Wahrnehmung (Routine)"
    assert opportunity_teaser_de(
        "Disziplin (Psi) (Herausfordernd): Das Ziehen des Flüsterns abschütteln."
    ) == "Disziplin (Psi) (Herausfordernd)"


def test_teaser_of_an_unlabelled_opportunity_stays_vague() -> None:
    assert opportunity_teaser_de("Irgendwo hier liegt der Verladebrief.") == ""
    assert opportunity_teaser_de("") == ""


def test_unlabelled_opportunities_render_as_a_vague_bullet() -> None:
    scene = Scene(
        id="zollhaus", title_de="Die Zoll-Sakristei",
        opportunities_de=["Irgendwo hier liegt der Verladebrief."],
        opportunity_ids=["brief"],
    )
    panel = render_player_panel_de(_with_mission(), scene)
    assert "• noch etwas Unentdecktes" in panel
    assert "Verladebrief" not in panel


def test_secrets_never_reach_the_panel() -> None:
    scene = _scene()
    scene.secrets_de = ["Kaad verschweigt, dass im Ossarium der Finger eines Heiligen liegt."]
    scene.secret_ids = ["geh-1"]
    panel = render_player_panel_de(
        _with_mission(), scene, ["G1 Regelfrage (RAG)"], active_player="Seskin")
    for spoiler in ("verschweigt", "Finger", "Heiligen", "Ossarium liegt"):
        assert spoiler not in panel
    # The GM-side halves of the scene card stay out too: description, guidance, NPC roster.
    assert "beschlagnahmte" not in panel
    assert "Kaad nennt den Schrein" not in panel


def test_good_success_outcomes_never_reach_the_panel() -> None:
    panel = render_player_panel_de(_with_mission(), _scene())
    assert "Guter Erfolg" not in panel
    assert "Diebe" not in panel
    assert "Datentafel" not in panel
