"""A hit becomes booked wounds: the attacker's weapon, the target — named in the player's own
line (D151) or picked from a menu —, the damage roll against the target's soak (D155), and the
booking that a weapon hit and a damaging psychic power share (D153).

A mixin (ADR 065): its methods are methods of the one ``DiceCog`` object — ``self`` is the cog,
all state is created in ``DiceCog.__init__``, and the shared session state lives on the
SessionRuntime (``self._rt``). The narration after the booking goes through
``DiceCog._narrate_rolls``, called through ``self``.
"""
from __future__ import annotations

import logging

import discord

from ...discord_ui.target import TargetSelectView
from ...rules import combat, engine
from ...rules.characters import Character

log = logging.getLogger(__name__)


class DamageMixin:
    """The auto-damage flow after a successful attack. Mixed into ``DiceCog``; holds no state of
    its own."""

    def _choose_weapon(self, attacker: Character | None) -> tuple[str | None, str]:
        """Pick the attacker's weapon + its damage notation: the first inventory item the profile
        knows a damage value for, else the profile's default damage. ('', '') if neither exists."""
        if self._rt._profile is None:
            return None, ""
        if attacker is not None:
            for item in attacker.inventory:
                notation = self._rt._profile.weapon_damage(item)
                if notation:
                    return item, notation
        return None, self._rt._profile.default_damage()

    def _target_phrases(self, names: list[str], *, party: bool = False) -> list[tuple[str, tuple[str, ...]]]:
        """Attack candidates with the names a player may call them by: an NPC's authored card
        aliases ("Fenk"), a team-mate's first name."""
        if party:
            return [(name, tuple(name.split()[:1]) if len(name.split()) > 1 else ()) for name in names]
        adventure = self._rt._adventure
        blocks = [(name, adventure.npc(name) if adventure is not None else None) for name in names]
        return [(name, tuple(block.aliases) if block is not None else ()) for name, block in blocks]

    async def _begin_attack_damage(self, channel, *, attacker: str | None, result,
                                   said: str = "") -> bool:
        """Start the auto-damage flow for a successful attack. Returns True if it took over (a target
        was auto-hit or a picker was posted — it will narrate); False if it couldn't (no weapon data
        or no target), so the caller narrates the hit plainly.

        ``said`` is the attacker's own line that asked for the roll; ``combat.choose_attack_target``
        reads the target from it (D151): exactly one present NPC named → hit without the picker,
        otherwise the picker. A lone NPC candidate is hit as before; a team-mate never without
        the picker."""
        cid = self._rt._brain_channel(channel)
        state = self._rt._state.get(cid)
        if state is None:
            return False
        attacker_char = self._rt._characters.get(attacker) if self._rt._characters else None
        weapon, notation = self._choose_weapon(attacker_char)
        if not notation:
            return False  # no weapon damage data → can't auto-roll; narrate the hit plainly
        # Candidates: the living NPCs PRESENT in this scene (ADR 062) first, then other party
        # members (friendly fire). Never NPCs elsewhere.
        npcs = [n.name for n in self._rt._scene_npcs(state)]
        party = [c.name for c in state.characters if c.name.lower() != (attacker or "").lower()]
        candidates = npcs + party
        if not candidates:
            await self._rt._send_with_retry(
                channel,
                "💥 Treffer! Aber kein Ziel hinterlegt — `!npc add <Name> [Wunden]`, dann erneut würfeln.",
            )
            return False
        choice = combat.choose_attack_target(
            said, self._target_phrases(npcs), self._target_phrases(party, party=True))
        lone_npc = npcs[0] if (len(npcs) == 1 and not party) else None
        target = lone_npc or choice.auto
        if target is not None:
            if lone_npc is None:
                log.info("🎯 Ziel aus der Ansage: %s — '%s'", target, said[:60])
            await self._apply_attack_damage(
                channel, attacker=attacker, weapon=weapon, notation=notation,
                result=result, target_name=target,
            )
            return True
        candidates = choice.order

        async def _pick(interaction: discord.Interaction, name: str) -> None:
            await self._apply_attack_damage(
                channel, attacker=attacker, weapon=weapon, notation=notation,
                result=result, target_name=name,
            )

        weap = f" ({weapon})" if weapon else ""
        await self._rt._send_with_retry(
            channel, f"💥 Treffer von **{attacker}**{weap} — wen trifft es?",
            view=TargetSelectView(candidates, _pick),
        )
        return True

    async def _apply_attack_damage(
        self, channel, *, attacker: str | None, weapon: str | None, notation: str, result, target_name: str
    ) -> None:
        """Roll the weapon's damage, subtract the target's soak (per profile; IM: armour only), apply the
        rest to its wounds, persist, and feed the result back so the DM narrates the consequence."""
        cid = self._rt._brain_channel(channel)
        state = self._rt._state.get(cid)
        if state is None:  # no session state to book damage in: the hit is narrated plainly
            await self._narrate_rolls(channel, channel.guild.id if channel.guild else None)
            return
        target = state.find(target_name)
        if target is None:  # picker only lists state names, but guard: register an ad-hoc enemy
            target = state.add_or_update_npc(target_name, wounds=10)
        sheet = None if target.is_npc else (self._rt._characters.get(target_name) if self._rt._characters else None)
        outcome = combat.resolve_attack(
            self._rt._profile, self._rt._characters,
            target=target, target_sheet=sheet,
            notation=notation, success_level=result.degrees, rng=self._rt._rng,
        )
        await self._book_damage(channel, state, outcome.damage, attacker=attacker,
                                target_name=target_name, weapon=weapon)

    async def _book_damage(self, channel, state, damage, *, attacker: str | None,
                           target_name: str, weapon: str | None) -> None:
        """Apply resolved damage to the target's wounds, post and persist it, and feed the line
        back so the DM narrates the consequence — the shared end of a weapon hit and a
        damaging psychic power."""
        state.apply_damage(target_name, damage.applied)
        updated = state.find(target_name)
        downed = updated is not None and updated.wounds <= 0
        line = engine.describe_damage_de(
            damage, attacker=attacker, target=target_name, weapon=weapon,
            new_wounds=updated.wounds if updated else 0,
            max_wounds=updated.max_wounds if updated else 0, downed=downed,
        )
        log.info("%s", line)
        await self._rt._send_with_retry(channel, line)
        self._rt._persist_and_refresh(channel)
        self._rt._brain.add_test_result(self._rt._brain_channel(channel), line)
        await self._narrate_rolls(channel, channel.guild.id if channel.guild else None)
