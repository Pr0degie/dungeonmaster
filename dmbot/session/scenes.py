"""Scene flow for :class:`~dmbot.runtime.SessionRuntime`: the code-owned scene pointer (set it,
register the scene's NPCs, journal the change, flag scene elements) and the **post-turn boundary**
(ADR 057/058/059) — once a turn is narrated the in-game clock ticks, the scene and fact
classifiers run in one shared latency window, and a validated verdict moves the pointer or writes
a hard fact. All four scene movers (classifier, flag gate, ``!ort``, the demoted ``<<ORT>>``
marker) go through the same :meth:`SceneFlowMixin.move_scene`.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord

from ..discord_ui.scene import retire_scene_proposal
from ..discord_ui.undo import SceneUndoView
from ..llm.director_msgs import scene_rejected_note_de
from ..llm.npc_router import Candidate, card_person
from ..llm.scene_router import SceneExit
from ..memory import history as history_store
from ..memory.state import WorldState
from ..rag.adventure import Scene
from ..rules.scene_flow import (
    MoveTrigger,
    apply_scene_undo,
    capture_scene_undo,
    is_scene_exhausted,
    next_scene_on_exhaustion,
    reachable_exits,
    resolve_exit,
)

log = logging.getLogger(__name__)


class SceneFlowMixin:
    """Scene pointer and post-turn boundary. Mixed into ``SessionRuntime``; holds no state of its
    own."""

    def _set_scene(self, state: WorldState, scene_id: str) -> Scene | None:
        """Move the code-owned scene pointer (golden rule #3): set ``state.scene_id`` and sync the
        prose location. The single deterministic move shared by ``!ort`` and the auto-transition
        path (ADR 026). Returns the Scene moved to, or None if ``scene_id`` is unknown to the
        adventure. The caller persists + refreshes the prompt. A real move (pointer actually
        changes) is journaled as a ``{"kind": "scene"}`` event (ADR 053)."""
        if self._adventure is None:
            return None
        scene = self._adventure.get_scene(scene_id)
        if scene is None:
            return None
        changed = state.scene_id != scene.id
        state.scene_id = scene.id
        if scene.title_de:
            state.set_location(scene.title_de)  # keep the prose state block in sync
        # Entering a scene registers its NPCs as present (PRD block 3, story 21) — the switch that
        # feeds NPC memory (ADR 044), agendas (ADR 049) and the consistency guard (ADR 045), all
        # of which need a populated state.npcs. Done here, in the one deterministic pointer
        # mover, so all four movers get it.
        self._register_scene_npcs(state, scene)
        if changed:
            self._journal_scene_event(state)
            # The card's people are at home here, wherever a sighting had put them: one filed
            # in a neighbouring scene (ADR 062, amendment #8) must not stay there for good.
            for person in self._card_people(scene.id).values():
                npc = state.find(person.name)
                if npc is not None and npc.is_npc:
                    npc.scene = ""
            cid = next((c for c, st in self._state.items() if st is state), None)
            if cid is not None:
                self._scene_turns[cid] = 0  # the guidance impulse fires again on the first turn here
        return scene

    #: The movers the people of the open turn follow (ADR 062, amendment #6): the narration
    #: carried the move (classifier, ``<<ORT>>`` button) or the operator set it (``!ort``). The
    #: flag gate moves on because a room is played out — nobody was narrated anywhere.
    _CARRYING_TRIGGERS = (MoveTrigger.CLASSIFIER, MoveTrigger.MARKER, MoveTrigger.COMMAND)

    def _carry_turn_sightings(self, cid: int, state: WorldState, left: str) -> None:
        """The NPCs filed in the turn that is still open follow the pointer from ``left`` to
        where it stands now (ADR 062, amendment 2026-11-13 #6): the classifier's own move, the
        ``<<ORT>>`` button confirmed after the verdict, ``!ort``, the ↩ undo. Whoever has been
        placed elsewhere since stays there, and so does a person on the
        card of ``left``: that scene is where she belongs (amendment #9). The caller decides
        whether this move carries anyone (:attr:`_CARRYING_TRIGGERS`) and persists."""
        moved: list[str] = []
        home = self._card_people(left)
        for name in self._turn_sightings.get(cid, ()):
            npc = state.find(name)
            if npc is not None and npc.name.strip().casefold() in home:
                continue
            if left and npc is not None and npc.is_npc and npc.scene == left:
                npc.scene = state.scene_id
                moved.append(npc.name)
        if moved:
            log.info("👥 mit der Gruppe nach '%s': %s", state.scene_id, ", ".join(moved))

    def _register_scene_npcs(self, state: WorldState, scene: Scene | None) -> list[str]:
        """Register the scene card's NPCs in the world state as present, with their statblock
        values (ADR 044's ``!npc add`` shape). Returns the names newly added.

        Only *named campaign* NPCs are registered — the card's ``npcs_here``. Incidental figures
        the DM invents (a runner, a bystander) are never registered here, and the consistency
        guard's presence check is additionally scoped to :meth:`Adventure.npc_names` in
        :meth:`consistency_checker`, so an accidental registration by the NPC-memory extractor
        cannot turn the DM's extras into violations either (the trap named in the PRD).

        Idempotent: an already-registered NPC keeps its drifted attitude, wounds and memories —
        ``attitude=""`` on the update path means "don't touch". A name belonging to a player
        character is skipped."""
        if self._adventure is None or scene is None:
            return []
        players = {c.name.strip().lower() for c in state.characters}
        known = {n.name.strip().lower() for n in state.npcs}
        added: list[str] = []
        for raw in scene.npcs_here:
            name = raw.strip()
            key = name.lower()
            if not name or key in players:
                continue
            block = self._adventure.npc(name)
            state.add_or_update_npc(
                name,
                wounds=block.wounds if block and key not in known else None,
                toughness_bonus=block.toughness_bonus if block else 0,
                armour=block.armour if block else 0,
                attitude="" if key in known else "neutral",
                faction=block.faction if block else "",
                goal=block.goal_de if block else "",
            )
            if key not in known:
                added.append(name)
        if added:
            log.info("👥 Szene '%s': %s als anwesend registriert", scene.id, ", ".join(added))
        return added

    def _journal_scene_event(self, state: WorldState) -> None:
        """Append a ``{"kind": "scene", "scene_id", "ts"}`` record to the session journal
        (ADR 053): rotated transcripts carry their own scene boundaries for the upcoming
        session-transcript ingest. ``load_recent`` skips it (no ``user_msg``/``answer``,
        ADR 046). Journaling must never break a scene move: a write error is only logged."""
        if not self._autosave:
            return
        cid = next((c for c, st in self._state.items() if st is state), None)
        if cid is None:
            return
        try:
            history_store.append_event(self._history_path(cid), {
                "kind": "scene",
                "scene_id": state.scene_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
        except OSError:
            log.exception("could not journal the scene event for channel %s", cid)

    def _set_scene_flag(self, state: WorldState, element_id: str, *, resolved: bool) -> str | None:
        """Deterministically flag an element of the CURRENT scene resolved/open (ADR 043, golden
        rule #3) — the single mutator shared by ``!erledigt``/``!offen`` and the ``<<ERLEDIGT>>``
        auto path. Validates ``element_id`` against the current scene card; returns the element's
        German text on success (for the reply), None for an unknown/foreign id or no adventure.
        Idempotent. The caller persists + refreshes the prompt."""
        if self._adventure is None:
            return None
        scene = self._adventure.get_scene(state.scene_id)
        if scene is None:
            return None
        text = scene.element_text(element_id)
        if text is None:
            return None
        if resolved:
            state.mark_resolved(scene.id, element_id)
        else:
            state.mark_open(scene.id, element_id)
        return text

    # ----- The post-turn boundary: scene, facts, clock (ADR 057/058/059) ---------------------

    async def close_turn(self, channel, answer: str) -> None:
        """Everything code decides once a turn has been narrated — the seam the whole D107 round
        hangs on. Called by the delivery pipeline concurrently with playback (like the dice
        button), so its latency is hidden behind the DM's own voice.

        In order: the clock ticks (ADR 059), the two classifiers run in ONE ``gather`` — one
        latency window for both, as ADR 058 requires — the fact verdict goes through the world
        state's validating writers, the scene verdict (or the model-free flag gate) moves the
        pointer, and the player panel is re-anchored at the bottom. Best-effort end to end: a
        failure here logs and never breaks a turn."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return
        try:
            self._scene_turns[cid] = self._scene_turns.get(cid, 0) + 1
            self._turn_sightings.pop(cid, None)  # the last turn's people stop following the pointer
            await self.advance_turn_time(channel)
            classified_from = state.scene_id     # snapshot: the classifier call takes seconds
            context = self._scene_context(cid, answer)  # snapshot too, before any await
            scene_verdict, fact_verdict, npc_verdict = await self._classify_turn(
                channel, state, answer, context=context
            )
            self._apply_commitment(channel, state, fact_verdict)
            # Under the pointer as it stands NOW, not ``classified_from``: an answer that narrates
            # an arrival shows the people of the new scene. A move still to come in this turn —
            # the verdict just below, a late button — takes them along (ADR 062, amendment #6).
            self._apply_npc_sightings(channel, state, npc_verdict, state.scene_id,
                                      began_in=classified_from)
            if scene_verdict is not None and state.scene_id != classified_from:
                # Someone moved the pointer while the classifier was thinking (``!ort``, the
                # ``<<ORT>>`` button, an undo). The verdict was built against the *old* scene's
                # exits, so it is stale — drop it silently rather than reject it loudly and tell
                # the model the group did NOT go where it just went
                # (docs/lessons/snapshot-state-at-event-time.md).
                log.info("🗺️ Szenen-Verdikt '%s' verworfen — der Zeiger stand bei der "
                         "Klassifikation auf '%s' und steht jetzt auf '%s'",
                         getattr(scene_verdict, "target_id", ""), classified_from, state.scene_id)
                scene_verdict = None
            await self._apply_scene_verdict(channel, state, scene_verdict)
            await self.update_player_panel()  # edited in place, never re-posted (D132)
        except Exception:
            log.exception("post-turn boundary failed — the turn itself is unaffected")

    def _scene_context(self, cid: int, answer: str) -> str:
        """The scene router's context for this turn: the previous narration and this turn's
        player lines, as ``Speaker: text`` lines. The narration is kept here, not read back from
        the brain's history, so it does not depend on when the history is written. Then this
        turn's answer becomes the next turn's previous narration."""
        narrations = self._last_narration
        lines = []
        previous = narrations.get(cid, "").strip()
        if previous:
            lines.append(f"Spielleitung: {previous}")
        for name, text in self._brain.last_actions(cid) or ():
            if str(text).strip():
                lines.append(f"{name}: {str(text).strip()}")
        narrations[cid] = answer
        return "\n".join(lines)

    async def _classify_turn(self, channel, state: WorldState, answer: str, *, context: str = ""):
        """Run the scene (ADR 057), fact (ADR 058) and presence (ADR 062) classifiers on the same
        turn boundary.

        All are optional layers and fail open: a switched-off block or a degenerate verdict
        yields ``None`` and changes nothing. With two or more layers asking and the brain's hook
        saying so (Claude answering, ``DM_AUX_COMBINED=1``), the questions go out as ONE schema
        call (ADR 066 B); otherwise each is its own call, as on Ollama. Both paths get the same
        question sets. Returns
        ``(scene_verdict | None, fact_verdict | None, npc_verdict | None)``."""
        questions = self._post_turn_questions(state, answer, context=context)
        if not questions:
            return None, None, None
        out: dict[str, object] = {}
        combined = len(questions) >= 2 and self._brain.combines_post_turn()
        if combined:
            try:
                out = await self._brain.classify_post_turn(**questions)
            except Exception:
                log.exception("combined post-turn classifier raised — ignored (fail-open)")
        else:
            methods = {"scene": self._brain.classify_scene_move,
                       "fact": self._brain.classify_commitment,
                       "npc": self._brain.classify_present_npcs}
            jobs = [(kind, methods[kind](**question)) for kind, question in questions.items()]
            results = await asyncio.gather(*(coro for _, coro in jobs), return_exceptions=True)
            for (kind, _), result in zip(jobs, results):
                if isinstance(result, BaseException):
                    log.exception("%s classifier raised — ignored (fail-open)", kind,
                                  exc_info=result)
                    continue
                out[kind] = result
        # Replay journal (ADR 046): the raw verdicts, exactly like the roll router's — for the
        # layers asked this turn, so a layer that sat out does not repeat an older turn's note.
        for kind, key, attr in (("scene", "scene_router", "last_scene_router"),
                                ("fact", "facts", "last_facts"), ("npc", "npcs", "last_npcs")):
            note = getattr(self._brain, attr)
            if kind in questions and isinstance(note, dict):
                self.replay_note(channel, key, note)
        if combined and isinstance(self._brain.last_post_turn, dict):
            self.replay_note(channel, "post_turn", self._brain.last_post_turn)
        return out.get("scene"), out.get("fact"), out.get("npc")

    def _post_turn_questions(self, state: WorldState, answer: str, *,
                             context: str = "") -> dict[str, dict]:
        """This turn's post-turn questions, ``{kind: keyword set}`` for the layers that ask —
        each set exactly what the matching separate classifier takes, so the separate calls and
        the combined one (ADR 066 B) are asked the same thing."""
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        party = self._characters.character_names() if self._characters else []
        questions: dict[str, dict] = {}
        if self._scene_router and scene is not None:
            exits = self._exit_labels(scene, state)
            if exits:
                questions["scene"] = {"turn_text": answer, "exits": exits,
                                      "current_title": scene.title_de, "context": context}
        if self._fact_router:
            questions["fact"] = {
                "answer_text": answer,
                "recipients": list(party),
                "givers": list(scene.npcs_here) if scene is not None else [],
            }
        if self._npc_router:
            questions["npc"] = {
                "answer_text": answer,
                "party": list(party),
                "roster": self._adventure.statblock_names() if self._adventure is not None else [],
                "present": [n.name for n in self._scene_npcs(state)],
                "candidates": self._npc_candidates(state, state.scene_id),
            }
        return questions

    def _npc_candidates(self, state: WorldState, scene_id: str) -> list[Candidate]:
        """The single people a sighting in ``scene_id`` may turn out to be, with role and
        authored aliases: the card NPCs of that scene and of every exit reachable from it right
        now (ADR 062, amendment 2026-11-13 #7/#8). The classifier is offered them, and code
        merges a sighting only into one of them.

        The data decides who is a person: a figure on a scene card's ``npcs_here`` is one; a
        statblock on no card is a template for numbers, as is one the adventure flags
        ``generic`` ("Kettenbund-Schläger" stands on a card and is still a role, not a man)."""
        scene = self._adventure.get_scene(scene_id) if self._adventure is not None else None
        if scene is None:
            return []
        people: dict[str, Candidate] = {}
        for sid in (scene.id, *self._exit_labels(scene, state)):
            for key, person in self._card_people(sid, living_in=state).items():
                people.setdefault(key, person)
        return list(people.values())

    def _neighbour_homes(self, state: WorldState, scene_id: str, *,
                         skip: tuple[str, ...] = ()) -> dict[str, str]:
        """``{casefolded name: home scene}`` for the card people of the exits reachable from
        ``scene_id`` right now — minus anyone on the card of a scene in ``skip`` (the scene
        itself, the one the turn began in). The first exit listing a person wins."""
        scene = self._adventure.get_scene(scene_id) if self._adventure is not None else None
        if scene is None:
            return {}
        excluded = {key for sid in skip if sid for key in self._card_people(sid)}
        homes: dict[str, str] = {}
        for sid in self._exit_labels(scene, state):
            for key in self._card_people(sid, living_in=state):
                if key not in excluded:
                    homes.setdefault(key, sid)
        return homes

    def _card_people(self, scene_id: str, *,
                     living_in: WorldState | None = None) -> dict[str, Candidate]:
        """The single people on one scene's card, ``{casefolded name: Candidate}`` — its
        ``npcs_here`` minus the statblocks flagged ``generic`` (see :meth:`_npc_candidates`).

        With ``living_in`` the dead of that state are left out: nobody new *is* a corpse (ADR 062,
        amendment #8)."""
        card = self._adventure.get_scene(scene_id) if self._adventure is not None else None
        people: dict[str, Candidate] = {}
        for raw in (card.npcs_here if card is not None else ()):
            name = raw.strip()
            block = self._adventure.npc(name)
            if not name or (block is not None and block.generic):
                continue
            known = living_in.find(name) if living_in is not None else None
            if known is not None and known.is_npc and known.wounds <= 0:
                continue
            people.setdefault(name.casefold(), Candidate(
                name, block.role_de if block else "", block.aliases if block else ()))
        return people

    def _apply_npc_sightings(self, channel, state: WorldState, verdict, scene_id: str, *,
                             began_in: str = "") -> None:
        """Place the people the presence classifier saw into ``scene_id`` (ADR 062 #2): a known
        NPC moves there, a new one is registered with its adventure statblock or the profile's
        improvised defaults. A sighting that is one of the scene-card people around
        (:meth:`_npc_candidates`) is that person under their own name, never a second entry
        (amendment 2026-11-13 #8). Code decides scene, identity and numbers; the verdict only
        names people. The names filed are remembered so they can follow a move in this turn.

        ``began_in`` is the scene the turn started in. When the pointer has left it meanwhile,
        its card people are candidates too, and a sighting that is one of them stays there: the
        fence who sees the group off does not turn up in the warehouse (amendment #9).

        A card figure of a neighbouring scene (an open exit, not ``scene_id`` or ``began_in``)
        seen once stays in her own scene: the narration usually walked the group to her door a
        turn before the pointer moved (live 2026-11-14, Bree Marlok filed in the shrine). Seen
        again the next turn in the same scene, she is really there (amendment 2026-11-14 #11)."""
        cid = self._brain_channel(channel)
        seen_before = self._neighbour_seen.pop(cid, set())
        sightings = getattr(verdict, "sightings", None)
        if not sightings or not scene_id:
            return
        defaults = (self._profile.improvised_npc() if self._profile is not None
                    else {"wounds": 10, "toughness_bonus": 0, "armour": 0})
        home = (self._card_people(began_in, living_in=state)
                if began_in and began_in != scene_id else {})
        candidates = [*self._npc_candidates(state, scene_id), *home.values()]
        neighbour = self._neighbour_homes(state, scene_id, skip=(scene_id, began_in))
        seen_now: set[tuple[str, str]] = set()
        placed: list[str] = []
        filed: list[str] = []
        for sighting in sightings:
            known = state.find(sighting.label)
            person = "" if known is not None else card_person(sighting, candidates)
            target = state.find(person) if person else known
            if target is not None and not target.is_npc:
                continue  # a player character — the verdict gate should already have dropped it
            statblock = person or sighting.statblock
            block = (self._adventure.npc(statblock)
                     if self._adventure is not None and statblock else None)
            name = person or sighting.label
            stays = name.casefold() in home
            elsewhere = "" if stays else neighbour.get(name.casefold(), "")
            if elsewhere:
                key = (name.casefold(), scene_id)
                if key in seen_before:
                    elsewhere = ""  # seen here two turns running: she really came over
                else:
                    seen_now.add(key)
            npc, new = state.place_npc(
                name, began_in if stays else (elsewhere or scene_id),
                wounds=block.wounds if block else defaults["wounds"],
                toughness_bonus=block.toughness_bonus if block else defaults["toughness_bonus"],
                armour=block.armour if block else defaults["armour"],
                faction=block.faction if block else "",
                goal=block.goal_de if block and person else "",
            )
            notes =[f"neu, {block.name if block else 'Standardwerte'}"] if new else []
            if person and person.casefold() != sighting.label.casefold():
                notes.append(f"gemeldet als „{sighting.label}“")
            if stays:
                notes.append(f"bleibt in '{began_in}'")
            if elsewhere:
                notes.append(f"gehört nach '{elsewhere}', bleibt dort")
            placed.append(f"{npc.name} ({'; '.join(notes)})" if notes else npc.name)
            if not elsewhere:
                filed.append(npc.name)
        if seen_now:
            self._neighbour_seen[cid] = seen_now
        if not placed:
            return
        # A neighbour's card figure kept at home is not filed: she does not follow a move.
        self._turn_sightings[cid] = tuple(filed)
        self._persist_and_refresh(channel)
        log.info("👥 anwesend in '%s': %s", scene_id, ", ".join(placed))

    def _exit_labels(self, scene: Scene | None, state: WorldState) -> dict[str, str]:
        """``{scene_id: title}`` for the exits reachable from ``scene`` right now (ADR 057 #6).

        The title is what lets the model map "zum Hafen" onto ``pier_neun``; a gated exit whose
        element isn't resolved yet is simply not offered."""
        if scene is None or self._adventure is None:
            return {}
        labels: dict[str, str] = {}
        for sid in reachable_exits(scene, state.resolved_ids(scene.id)):
            target = self._adventure.get_scene(sid)
            labels[sid] = target.title_de if target is not None else ""
        return labels

    def _apply_commitment(self, channel, state: WorldState, verdict) -> None:
        """Write a validated commitment into the world state (ADR 058 #2).

        Code decides what the verdict *means*: ``record_commitment`` re-validates the kind and
        the label and returns ``None`` for anything it won't accept, so a malformed verdict
        changes nothing. The write is logged because a prompt-resident wrong fact is worse than a
        forgotten right one and the operator must be able to see (and ``!fakt weg``) it."""
        commitment = getattr(verdict, "commitment", None)
        if commitment is None:
            return
        written = state.record_commitment(commitment.kind, **commitment.record_kwargs())
        if written is None:
            return
        self._persist_and_refresh(channel)
        log.info("📌 Fakt aufgenommen (%s): %s → %s%s", commitment.kind, commitment.text,
                 commitment.to or "Gruppe",
                 f" (von {commitment.by})" if commitment.by else "")

    async def _apply_scene_verdict(self, channel, state: WorldState, verdict) -> None:
        """Turn the classifier verdict — or, failing that, the flag gate — into a pointer move.

        The classifier wins when it saw an arrival: it read the narration, the gate only counts
        flags. The gate (ADR 057 #2) then covers the other failure the run showed, a room squeezed
        empty with nobody moving on, and only when the answer is unambiguous (exactly one open
        exit). Both proposals are re-checked by ``scene_flow.resolve_exit`` before anything is
        written, and a rejection is loud (ADR 057 #5)."""
        if self._adventure is None:
            return
        scene = self._adventure.get_scene(state.scene_id)
        resolved = state.resolved_ids(scene.id) if scene is not None else []
        target, trigger = "", None
        if verdict is not None and getattr(verdict, "moved", False):
            target, trigger = verdict.target_id, MoveTrigger.CLASSIFIER
        elif self._scene_flag_gate and is_scene_exhausted(scene, resolved):
            choice = next_scene_on_exhaustion(scene, resolved)
            if choice.auto_target:
                target, trigger = choice.auto_target, MoveTrigger.FLAG_GATE
                log.info("🔓 Szene '%s' ist ausgespielt — Flag-Zwang schiebt weiter nach '%s'",
                         scene.id if scene else "—", target)
            elif choice.candidates:
                log.info("🔓 Szene '%s' ist ausgespielt, aber %d Ausgänge offen — kein Automatik-"
                         "Wechsel", scene.id if scene else "—", len(choice.candidates))
        if not target:
            return
        await self.request_scene_move(channel, target, trigger=trigger)

    async def request_scene_move(self, channel, target_id: str, *, trigger=None) -> Scene | None:
        """Validate a proposed move and perform it, or report the rejection loudly.

        The single gate every automatic mover goes through (classifier, flag gate, and the demoted
        ``<<ORT>>`` marker). Returns the Scene moved to, or ``None``."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or self._adventure is None:
            return None
        scene = self._adventure.get_scene(state.scene_id)
        verdict = resolve_exit(
            scene, target_id,
            resolved_ids=state.resolved_ids(scene.id) if scene is not None else [],
            known_scene_ids=[sid for _, sid, _ in self._adventure.scene_overview()],
        )
        self.replay_note(channel, "scene_move", {
            "requested": target_id,
            "trigger": getattr(trigger, "value", trigger),
            "accepted": verdict.permitted,
            "reason": getattr(verdict.reason, "value", verdict.reason),
        })
        if not verdict.permitted:
            await self.report_rejected_move(channel, verdict)
            return None
        return await self.move_scene(channel, verdict.target_id, trigger=trigger)

    async def report_rejected_move(self, channel, verdict) -> None:
        """Make a refused scene change loud (ADR 057 #5) — a director note for the next turn AND
        an operator-visible line, never just a ``log.info``.

        Spoiler discipline decides where each half lands: the ``[Regie]`` note (model-facing) and
        the log carry the reachable exits and the element that would unlock a gated one, and the
        operator line goes to ``DM_DEBUG_CHANNEL`` *only*. Without one configured there is no
        channel line at all — a scene id like ``pier_neun`` in the game channel names a locked
        finale to the players, which is exactly what this docstring claims not to do."""
        cid = self._brain_channel(channel)
        labels = [SceneExit(sid, self._scene_title(sid)).label()
                  for sid in verdict.reachable_exits]
        note = scene_rejected_note_de(verdict.target_id, verdict.reason, labels)
        self._brain.add_gm_note(cid, note)
        log.warning("🚫 Szenenwechsel '%s' abgelehnt (%s)%s — erreichbar: %s; Regie-Hinweis für "
                    "den nächsten Zug eingereiht", verdict.target_id,
                    getattr(verdict.reason, "value", verdict.reason),
                    f", Bedingung '{verdict.required_element_id}' offen"
                    if verdict.required_element_id else "",
                    ", ".join(verdict.reachable_exits) or "—")
        target = self._operator_channel()
        if target is None:
            return          # no operator channel — log + [Regie] note are the whole delivery
        name = self._scene_title(verdict.target_id) or verdict.target_id
        try:
            await target.send(
                f"🚫 Szenenwechsel nach „{name}“ abgelehnt — die Gruppe bleibt, wo "
                f"sie ist. (Grund im Log; die Spielleitung bekommt einen Hinweis.)"
            )
        except discord.HTTPException:
            log.warning("could not post the rejected-move line", exc_info=True)

    def _scene_title(self, scene_id: str) -> str:
        scene = self._adventure.get_scene(scene_id) if self._adventure is not None else None
        return scene.title_de if scene is not None else ""

    async def move_scene(self, channel, scene_id: str, *, trigger=None,
                         announce: bool = True) -> Scene | None:
        """Move the scene pointer and do everything a *real* move entails, in one place.

        Deterministic pointer + NPC registration (``_set_scene``), persist + prompt refresh, NPC
        memory mining for the scene just left (ADR 044), the scene-change time cost (ADR 048 #10),
        the 🧪 overlay and the player panel — plus, when ``announce``, the channel line and the
        one-minute ↩ control of ADR 057 #4. The change happens FIRST and is undone on click: a
        confirmation nobody knows about is the same as no mechanism."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        undo = capture_scene_undo(state, scene_id, trigger=trigger)
        old_scene = state.scene_id
        moved = self._set_scene(state, scene_id)
        if moved is None:
            return None
        if old_scene != moved.id and trigger in self._CARRYING_TRIGGERS:
            self._carry_turn_sightings(cid, state, old_scene)
        self._persist_and_refresh(channel)
        log.info("scene → %s (%s) [%s]", moved.id, moved.title_de,
                 getattr(trigger, "value", trigger) or "auto")
        await retire_scene_proposal(self._scene_proposals, cid, moved)
        if old_scene and old_scene != moved.id:
            self.schedule_npc_memory_extraction(channel, old_scene)
            await self.advance_scene_time(channel)
        await self.update_debug_overlay()
        await self.update_player_panel()
        if announce:
            await self._announce_scene_change(channel, moved, undo)
        return moved

    async def _announce_scene_change(self, channel, scene: Scene, undo) -> None:
        """Say in the channel that the scene moved, with a ↩ control that stays live for about a
        minute (ADR 057 #4). ``DM_SCENE_UNDO_SECONDS=0`` posts the line without the button."""
        text = f"📖 Szene gewechselt: **{scene.title_de}** (Teil {scene.part})."
        view = None
        if self._scene_undo_seconds > 0:
            view = SceneUndoView(self._make_scene_undo(channel, undo),
                                 timeout=float(self._scene_undo_seconds))
        try:
            message = await self._send_with_retry(channel, text, view=view)
        except discord.HTTPException:
            log.warning("could not announce the scene change", exc_info=True)
            return
        if view is not None:
            view.message = message  # so the view can grey its button out when the minute is up

    def _make_scene_undo(self, channel, undo):
        """Build the ↩ callback for one scene change: restore pointer + in-game time, refresh the
        prompt and the panels, and edit the announcement. ``apply_scene_undo`` refuses (and writes
        nothing) when the pointer has moved on since — which also makes a second click a no-op."""
        async def _undo(interaction: discord.Interaction) -> None:
            cid = self._brain_channel(channel)
            state = self._state.get(cid)
            if state is None:
                return
            left = state.scene_id
            if not apply_scene_undo(undo, state):
                await interaction.edit_original_response(
                    content="Nicht mehr aktuell — die Szene ist inzwischen weitergezogen."
                )
                return
            self._carry_turn_sightings(cid, state, left)  # the group did not go: nor did they
            self._persist_and_refresh(channel)
            self._scene_turns[cid] = 0
            log.info("scene ↩ zurückgenommen → %s (%s)", state.scene_id,
                     getattr(undo.trigger, "value", undo.trigger) or "auto")
            await self.update_debug_overlay()
            await self.update_player_panel()
            await self.update_clock_panel()
            scene = self._adventure.get_scene(state.scene_id) if self._adventure else None
            title = scene.title_de if scene is not None else state.scene_id
            await interaction.edit_original_response(
                content=f"↩ Szenenwechsel zurückgenommen — ihr seid weiter in **{title}**."
            )
        return _undo
