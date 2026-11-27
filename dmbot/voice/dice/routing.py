"""Which roll does this turn ask for: the players' own lines the buttons are decided from (D151),
the marker check and who decides — the narrator's inline ``<<TEST>>`` markers or the roll router
(D140, D43) —, the characters a Manifest request already covers, and the roll-detection router
itself (ADR 014).

A mixin (ADR 065): its methods are methods of the one ``DiceCog`` object — ``self`` is the cog,
all state is created in ``DiceCog.__init__``, and the shared session state lives on the
SessionRuntime (``self._rt``). The button itself is posted by ``DiceCog._post_dice_button``,
called through ``self``.
"""
from __future__ import annotations

import logging

from ...llm.roll_router import is_continuation_fragment, marker_key, superseded_by_manifest
from ...rules import combat
from ...rules.characters import Character, resolve_manifest_request
from ...rules.marker import ManifestRequest, TestRequest

log = logging.getLogger(__name__)


class RollRoutingMixin:
    """Decides the turn's dice buttons. Mixed into ``DiceCog``; holds no state of its own."""

    def _spoken(self, cid: int) -> dict[str, str]:
        """Each character's own line of the turn just answered (lower-cased character name →
        text). Taken once, when the turn's buttons are decided: a hit reads its target from the
        line that asked for the roll (D151), and the brain's actions are replaced by the next turn."""
        store = self._rt._characters
        if store is None:
            return {}
        spoken: dict[str, str] = {}
        for name, text in self._rt._brain.last_actions(cid):
            char = store.get(name)
            if char is not None:
                spoken[char.name.lower()] = text
        return spoken

    def _said(self, spoken: dict[str, str] | None, who: str | None) -> str:
        """``who``'s own line out of :meth:`_spoken`; "" when they said nothing this turn."""
        store = self._rt._characters
        char = store.get(who) if (store is not None and who) else None
        return (spoken or {}).get(char.name.lower(), "") if char is not None else ""

    def _check_marker(self, req: TestRequest) -> tuple[str | None, str | None]:
        """``(character name, None)`` for a marker the engine can roll as written, else
        ``(None, reason)``. Valid: parsed, a party character, the skill (or a same-named
        characteristic) on that sheet, a difficulty the profile's ladder/aliases know. An unknown
        difficulty word stays glued to the skill in the marker grammar, so it fails on the sheet."""
        profile, store = self._rt._profile, self._rt._characters
        if profile is None or store is None:
            return None, "keine Party geladen"
        if not req.parsed or not req.skill:
            return None, "unlesbar"
        if req.modifier is None and req.difficulty is not None \
                and profile.difficulty_modifier(req.difficulty) is None:
            return None, f"Schwierigkeit '{req.difficulty}' unbekannt"
        char = store.get(req.target_name)
        if char is None:
            return None, f"Figur '{req.target_name or '—'}' unbekannt"
        if store.skill_value(char, req.skill) is None:
            return None, f"'{req.skill}' steht nicht auf dem Bogen von {char.name}"
        return char.name, None

    @staticmethod
    def _difficulty_label(req: TestRequest) -> str:
        if req.modifier is not None:
            return f"{req.modifier:+d}"
        return req.difficulty or "Standard"

    async def _markers_decide(self, channel, cid: int, markers: list[TestRequest], *,
                              manifesting: set[str], spoken: dict[str, str] | None = None) -> None:
        """Claude narrated (D140): each valid marker posts its own button. The router still
        classifies every speaker no valid marker covers — one whose marker was invalid, and one
        the narrator asked nothing for (the persona allows one test per reply, so with two players
        acting the second action would otherwise get no button; D111: one router pass per speaker)."""
        covered: set[str] = set()
        posted: set[tuple[str, str]] = set()
        for req in markers:
            name, problem = self._check_marker(req)
            if name is None:
                log.info("🎲 Marker %s ungültig (%s) — der Router entscheidet diese Runde",
                         req.raw, problem)
                continue
            covered.add(name.lower())
            key = marker_key(name, req.skill)
            if key in posted:
                continue  # the same request twice in one turn: one button
            if superseded_by_manifest(name, manifesting=manifesting):
                log.info("🎲 Marker: %s — %s verworfen, die Manifestation deckt die Handlung ab",
                         name, req.skill)
                continue
            posted.add(key)
            log.info("🎲 Marker entscheidet: %s — %s (%s)", name, req.skill, self._difficulty_label(req))
            await self._post_dice_button(channel, req, said=(spoken or {}).get(name.lower(), ""))
        await self._post_router_dice(channel, manifesting=manifesting, skip=covered)
        self._repeats.turn(cid, set())  # the narrator's requests were honoured: nothing hangs

    async def _router_decides(self, channel, cid: int, markers: list[TestRequest], *,
                              manifesting: set[str], spoken: dict[str, str] | None = None) -> None:
        """Ollama narrated, or Claude asked nothing (D43): the router decides. The repeat safety
        net (D140) then honours a valid marker the previous turn already asked for (same
        character + skill, no roll in between) where the router posted nothing for that
        character — the narrator is otherwise stuck re-narrating a moment that waits for a roll."""
        decided = await self._post_router_dice(channel, manifesting=manifesting)
        valid = [(req, name) for req in markers if (name := self._check_marker(req)[0]) is not None]
        repeated = self._repeats.turn(cid, {marker_key(name, req.skill) for req, name in valid})
        rescued = 0
        for req, name in valid:
            key = marker_key(name, req.skill)
            if key not in repeated or name.lower() in decided \
                    or superseded_by_manifest(name, manifesting=manifesting):
                continue
            repeated.discard(key)  # one button per request
            rescued += 1
            log.info("🎲 Sicherheitsnetz: %s — %s (%s) zum zweiten Mal angefordert, kein Wurf "
                     "dazwischen → der Marker gilt", name, req.skill, self._difficulty_label(req))
            await self._post_dice_button(channel, req, said=(spoken or {}).get(name.lower(), ""))
        if len(markers) > rescued:
            log.info("🎲 %d Inline-Marker verworfen — der Router entscheidet (D43)",
                     len(markers) - rescued)

    def _manifesting(self, manifests: list[ManifestRequest]) -> set[str]:
        """Lower-cased names of the characters a Manifest request this turn resolves to."""
        names: set[str] = set()
        if self._rt._profile is None:
            return names
        for m in manifests:
            resolved = resolve_manifest_request(
                self._rt._profile, self._rt._characters, power=m.power, target_name=m.target_name,
            )
            name = (resolved.character.name if resolved and resolved.character else m.target_name) or ""
            if name.strip():
                names.add(name.strip().lower())
        return names

    def _toughness_bonus(self, target: Character | None) -> int:
        """Toughness Bonus for a player from the sheet: the profile's soak characteristic (IM: Tgh),
        rendered per soak mode (IM: tens digit). 0 if no profile/character/characteristic."""
        return combat.toughness_bonus(self._rt._profile, self._rt._characters, target)

    async def _post_router_dice(self, channel, *, manifesting: set[str] | None = None,
                                skip: set[str] | None = None) -> set[str]:
        """Roll-detection router (ADR 014): classify each player action of the turn in a separate
        constrained-JSON call and post a dice button per action that needs a test. Skips silently
        when there's no player action this turn (e.g. a post-roll narration) or no matching
        character, and the characters in ``skip`` (lower-cased; a valid marker decided theirs,
        D140). Returns the lower-cased names the router posted a button for.

        One action per *speaker* (D111), so no declaration in a multi-speaker turn is lost. The character always
        comes from the speaker of the action, never from who presses the button, so a player may
        press a team-mate's button without stealing their test.

        Deliberately sequential, not gathered: the brain exposes the router's raw verdict as a
        single ``last_router`` attribute that each call overwrites, so parallel calls would
        cross-attribute the replay journal (ADR 046). This runs off the hot path while the DM is
        speaking, and multi-speaker turns are the minority.
        """
        decided: set[str] = set()
        if self._rt._profile is None or self._rt._characters is None:
            return decided
        actions = self._rt._brain.last_actions(self._rt._brain_channel(channel))
        for name, text in actions:
            char = self._rt._characters.get(name)
            if char is None or (skip and char.name.lower() in skip):
                continue
            if is_continuation_fragment(text):  # talk, not a declared action
                log.info("🎲 router: %s — '%s' übersprungen (Satzfragment, keine Handlung)",
                         char.name, text[:50])
                continue
            # Constrain the classifier to this character's sheet: skills first, then any same-named
            # governing characteristic (skill_value falls back to those).
            skills = list(char.skills) + [c for c in char.characteristics if c not in char.skills]
            req = await self._rt._brain.classify_test(action=text, character=char.name, skills=skills)
            # Replay journal (ADR 046): the router's raw constrained-JSON verdict + parsed decision,
            # so dm-eval can re-run the classification offline. None (a failed call) records nothing.
            recorded = self._rt._brain.last_router
            if recorded is not None:
                self._rt.replay_note(channel, "router", {
                    "action": text, "character": char.name, "skills": skills, **recorded,
                })
            if req is not None and superseded_by_manifest(char.name, manifesting=manifesting or set()):
                log.info("🎲 router: %s — %s verworfen, die Manifestation deckt die Handlung ab",
                         char.name, req.skill)
                continue
            if req is not None:
                log.info("🎲 router: %s — '%s' → %s (%s)",
                         char.name, text[:50], req.skill, req.difficulty or "Standard")
                decided.add(char.name.lower())
                await self._post_dice_button(channel, req, said=text)  # the line it was classified from
        return decided
