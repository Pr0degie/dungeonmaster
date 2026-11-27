"""Psychic powers (ADR 022): the Manifest button and its roll, the Warp Charge and Perils
bookkeeping, the Fate choice under a failed Manifest Test (ADR 063), and a damaging power's
target and wounds (D153).

A mixin (ADR 065): its methods are methods of the one ``DiceCog`` object — ``self`` is the cog,
all state is created in ``DiceCog.__init__``, and the shared session state lives on the
SessionRuntime (``self._rt``). The throw and the result picture stay in dicecog.py and are called
through ``self`` (``_prepare_throw``, ``_animate_result``, ``_result_edit``): the tests replace
the renderers on the dicecog namespace, and only a function defined there sees that.
"""
from __future__ import annotations

import logging

import discord

from ...dice_images import palette_for
from ...discord_ui.dice import DiceTestView
from ...discord_ui.fate import FateView
from ...discord_ui.target import TargetSelectView
from ...rules import combat, engine
from ...rules.characters import resolve_manifest_request
from ...rules.marker import ManifestRequest

log = logging.getLogger(__name__)

# The way out of the power target picker: the power hit a thing or someone the state does not know.
_NO_TARGET = "Niemand davon — nur erzählen"


class ManifestMixin:
    """A Manifest Test from the button to the booked result. Mixed into ``DiceCog``; holds no
    state of its own."""

    async def _post_manifest_button(self, channel, req: ManifestRequest, *, said: str = "") -> None:
        """Post a Manifest button and count it as an open roll of the turn (D152), like
        :meth:`_post_dice_button`; an unknown power or a failed post is not counted."""
        cid = self._rt._brain_channel(channel)
        self._open_rolls.posted(cid)
        try:
            posted = await self._send_manifest_button(channel, req, said=said)
        except BaseException:
            self._open_rolls.withdrawn(cid)
            raise
        if not posted:
            self._open_rolls.withdrawn(cid)

    async def _send_manifest_button(self, channel, req: ManifestRequest, *, said: str = "") -> bool:
        """Resolve a Manifest request (power → Warp Rating + Difficulty + the psyker's Psi-Meisterschaft
        value, all in code) and post its button (ADR 022). False: no button (unknown power)."""
        resolved = resolve_manifest_request(
            self._rt._profile, self._rt._characters, power=req.power, target_name=req.target_name,
        )
        if resolved is None:  # no psyker block or the power isn't catalogued — note it, don't crash
            note = f"„{req.power}“" if req.power else "Kraft"
            await self._rt._send_with_retry(
                channel, f"🌀 Unbekannte psychische Kraft {note} — nicht im Regelprofil hinterlegt.",
            )
            return False
        who = (resolved.character.name if resolved.character else req.target_name) or "Psioniker"
        diff = f" ({resolved.difficulty})" if resolved.difficulty else ""
        push = " · Push" if req.pushed else ""
        label = f"{who} manifestiert: {resolved.power}{diff}{push}"
        # The throw is prepared at post time, as for a skill test (ADR 064): the click only lands it.
        prep = (self._prepare_throw()
                if self._dice_animation_on() and resolved.target is not None else None)
        await self._rt._send_with_retry(
            channel, "🌀 Manifestation angefordert:",
            view=DiceTestView(label, self._make_manifest_roll(channel, req, resolved, prep=prep,
                                                              said=said)),
        )
        return True

    def _make_manifest_roll(self, channel, req: ManifestRequest, resolved, *, prep=None,
                            said: str = ""):
        """Build the roll callback for a Manifest button: the engine rolls the Psychic Mastery Test,
        bookkeeps Warp Charge against the Threshold, resolves Perils when triggered, persists the
        psyker's Warp Charge, and feeds every line back so the DM narrates the consequence.

        A failed Manifest Test by a character with Fate left gets the Fate choice first (IM p.220:
        Fate rerolls a failed Test, the Manifest Test is one). Warp Charge and Perils follow from the
        result that stands (IM p.161, step 3), so nothing is booked before the choice. ``said`` is
        the psyker's own line — a damaging power reads its target from it (D153)."""
        power = resolved.power
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            guild_id = channel.guild.id if channel.guild else None
            cid = self._rt._brain_channel(channel)
            self._repeats.rolled(cid)  # a roll decides the moment (D140)
            dice_msg = {"message": interaction.message}
            if resolved.target is None:  # no Psi-Meisterschaft value on the sheet — roll, ask to compare
                d = engine.roll(self._rt._profile.dice, self._rt._rng)
                line = (f"🌀 {power}: {d.total} — kein Psi-Meisterschaft-Wert hinterlegt, "
                        "vergleicht mit eurem Bogen.")
                log.info("%s", line)
                await self._present_manifest(channel, dice_msg, resolved, line, d.total, None)
                await self._feed_manifest(channel, guild_id, [line])
                return
            state = self._rt._state.get(cid)
            combatant = state.find(who) if (state and who) else None
            current = combatant.warp_charge if combatant is not None else 0
            result = self._manifest_once(resolved, req, current)
            line = engine.describe_manifest_de(result, character=who)
            log.info("%s", line)
            pc = self._fate_holder(channel, who) if not result.test.success else None
            if pc is None:
                lines = [line, *self._book_manifest(channel, cid, who, resolved, result)]
                await self._present_manifest(channel, dice_msg, resolved, "\n".join(lines),
                                             result.test.roll, result.test, prep=prep)
                await self._finish_manifest(channel, guild_id, lines, resolved=resolved,
                                            result=result, who=who, said=said)
                return
            view = FateView(
                pc.fate_available,
                self._make_manifest_fate(channel, guild_id, dice_msg, req, resolved, result, line,
                                         current, said=said),
                timeout=float(self._rt._fate_wait_seconds),
            )
            await self._present_manifest(channel, dice_msg, resolved, line, result.test.roll,
                                         result.test, prep=prep, view=view)

        return _roll

    def _manifest_once(self, resolved, req: ManifestRequest, current: int):
        """One Manifest Test through the engine against ``current`` Warp Charge — nothing booked."""
        return engine.resolve_manifest(
            self._rt._profile, test_target=resolved.target, power=resolved.power,
            warp_rating=resolved.warp_rating, current_charge=current,
            willpower_bonus=resolved.willpower_bonus, threshold=resolved.threshold,
            pushed=req.pushed, rng=self._rt._rng,
        )

    def _book_manifest(self, channel, cid: int, who, resolved, result) -> list[str]:
        """Book the Manifest result that stands: Warp Charge, a Sustained power, the Perils risk.
        Returns the extra lines (Perils, containment, the untracked-charge warning)."""
        state = self._rt._state.get(cid)
        combatant = state.find(who) if (state and who) else None
        if state is not None and combatant is not None:
            state.set_warp_charge(who, result.warp_charge)
            if result.test.success and (resolved.stats or {}).get("duration", "") == "Anhaltend":
                state.sustain_power(who, resolved.power)
            extra = self._resolve_warp_consequences(state, who, resolved, result)
            self._rt._persist_and_refresh(channel)
            return extra
        if state is not None and self._rt._characters and self._rt._characters.get(who):
            # Known party psyker, but not seeded into this session's WorldState — Warp Charge
            # would silently never accumulate (current_charge stays 0 each call) and Perils
            # never fire. There is no safe single-character add on WorldState (seed_from_store
            # rebuilds the whole state, add_or_update_npc would mistype a PC as an NPC), so warn the GM
            # once instead of losing the resource silently.
            key = (cid, (who or "").lower())
            if key not in self._warp_untracked_warned:
                self._warp_untracked_warned.add(key)
                log.warning("Warp charge not tracked: %s is not in the current encounter state", who)
                return [f"⚠️ Warp-Aufladung wird nicht verfolgt — {who} ist nicht in der "
                        "aktuellen Szene/Encounter."]
        return []

    async def _present_manifest(self, channel, dice_msg: dict, resolved, line: str, face,
                                test_result, *, prep=None, view=None) -> None:
        """Show a Manifest result in the button message: the throw first when the animation is on
        (live 2026-11-14: a Manifest showed only the result), else the result straight away."""
        if self._dice_animation_on() and resolved.target is not None:
            # Cosmetic, in its own task; the caller feeds the DM without waiting for it.
            self._spawn_presentation(self._animate_result(
                channel, dice_msg, target=resolved.target, line=line, face=face,
                palette=palette_for(test_result), view=view, prep=prep,
            ))
            return
        shown = await self._result_edit(line, face, palette_for(test_result))
        try:
            await dice_msg["message"].edit(**shown, view=view)
        except discord.HTTPException:
            await self._rt._send_with_retry(channel, line, view=view)

    async def _feed_manifest(self, channel, guild_id, lines: list[str]) -> None:
        cid = self._rt._brain_channel(channel)
        for ln in lines:
            self._rt._brain.add_test_result(cid, ln)
        await self._narrate_rolls(channel, guild_id)

    async def _finish_manifest(self, channel, guild_id, lines: list[str], *, resolved, result,
                               who: str | None, said: str) -> None:
        """Feed the Manifest result that stands and narrate it — or, when the power succeeded and
        the profile gives it a single-target ``damage`` block (ADR 022, amendment 2026-11-27),
        hand over to the damage flow like a weapon hit: wounds are booked by code, never by the
        narration (golden rules #2 and #3; live 2026-11-27 a Smite hit left the target at 10/10)."""
        cid = self._rt._brain_channel(channel)
        for ln in lines:
            self._rt._brain.add_test_result(cid, ln)
        if result.test.success and await self._begin_power_damage(
                channel, psyker=who, resolved=resolved, result=result, said=said):
            return  # the damage flow narrates once a target is chosen/auto-applied
        await self._narrate_rolls(channel, guild_id)

    async def _begin_power_damage(self, channel, *, psyker: str | None, resolved, result,
                                  said: str) -> bool:
        """Start the damage flow for a manifested power. True if it took over (a target was hit
        or a picker posted — it narrates); False when there is nothing to book in code: no
        ``damage`` block, an area power ("Nova" — its targets stay the GM's call), no state, or
        no NPC in the scene (an enemy the state does not know is narrated, never a team-mate
        offered instead). The target is read from the psyker's own line (D151); unlike a weapon
        hit there is no shortcut for a lone NPC — a power may be aimed at a door — and the
        picker offers "nobody", so the narration is never stuck behind it."""
        profile = self._rt._profile
        state = self._rt._state.get(self._rt._brain_channel(channel))
        block = profile.power_damage(resolved.power) if profile is not None else None
        if block is None or state is None or block["targets"] != "one":
            return False
        npcs = [n.name for n in self._rt._scene_npcs(state)]
        party = [c.name for c in state.characters if c.name.lower() != (psyker or "").lower()]
        if not npcs:
            return False
        choice = combat.choose_attack_target(
            said, self._target_phrases(npcs), self._target_phrases(party, party=True))
        if choice.auto is not None:
            log.info("🎯 Ziel aus der Ansage: %s — '%s'", choice.auto, said[:60])
            await self._apply_power_damage(channel, psyker=psyker, resolved=resolved,
                                           result=result, target_name=choice.auto)
            return True

        async def _pick(interaction: discord.Interaction, name: str) -> None:
            if name == _NO_TARGET:  # aimed at a thing, or at someone the state does not know
                await self._narrate_rolls(channel, channel.guild.id if channel.guild else None)
                return
            await self._apply_power_damage(channel, psyker=psyker, resolved=resolved,
                                           result=result, target_name=name)

        await self._rt._send_with_retry(
            channel, f"🌀 **{psyker}** trifft mit {resolved.power} — wen trifft es?",
            view=TargetSelectView([*choice.order, _NO_TARGET], _pick),
        )
        return True

    async def _apply_power_damage(self, channel, *, psyker: str | None, resolved, result,
                                  target_name: str) -> None:
        """Resolve the power's damage against the target from the profile (base + the psyker's
        bonus + SL, minus the soak the power does not ignore) and book it like a weapon hit."""
        state = self._rt._state.get(self._rt._brain_channel(channel))
        target = state.find(target_name) if state is not None else None
        outcome = None
        if target is not None:
            sheet = None if target.is_npc else (
                self._rt._characters.get(target_name) if self._rt._characters else None)
            outcome = combat.resolve_power_damage(
                self._rt._profile, self._rt._characters, power=resolved.power,
                psyker_sheet=resolved.character, target=target, target_sheet=sheet,
                success_level=result.test.degrees, rng=self._rt._rng,
            )
        if outcome is None:  # the picked figure left the state meanwhile: say so, book nothing
            await self._rt._send_with_retry(
                channel, f"🌀 {target_name} ist nicht mehr in der Szene — kein Schaden gebucht.")
            await self._narrate_rolls(channel, channel.guild.id if channel.guild else None)
            return
        await self._book_damage(channel, state, outcome.damage, attacker=psyker,
                                target_name=target_name, weapon=outcome.power)

    def _make_manifest_fate(self, channel, guild_id, dice_msg: dict, req: ManifestRequest,
                            resolved, result, line: str, current: int, *, said: str = ""):
        """The Fate choice under a failed Manifest Test (ADR 063 on ADR 022): spend → the point is
        booked and the Test rerolled against the same Warp Charge, the second result stands; keep /
        timeout → the first stands. Only then is Warp Charge booked and the DM fed."""
        who = resolved.character.name if resolved.character else req.target_name

        async def _decide(interaction, spend: bool) -> None:
            cid = self._rt._brain_channel(channel)
            state = self._rt._state.get(cid)
            final, head, shown = result, line, line
            if spend and state is not None and state.spend_fate(who):
                left = state.find(who).fate_available
                final = self._manifest_once(resolved, req, current)
                head = (f"🙏 {who} gibt einen Schicksalspunkt aus (noch {left}) und würfelt neu — "
                        f"dieses Ergebnis gilt: {engine.describe_manifest_de(final, character=who)}")
                shown = f"{line}\n{head}"
                log.info("%s", head)
                self._rt._persist_and_refresh(channel)
            lines = [head, *self._book_manifest(channel, cid, who, resolved, final)]
            text = "\n".join([shown, *lines[1:]])
            if final is not result:  # the reroll is thrown like the first roll
                await self._present_manifest(channel, dice_msg, resolved, text, final.test.roll,
                                             final.test,
                                             prep=(self._prepare_throw()
                                                   if self._dice_animation_on() else None))
            elif len(lines) > 1 or not self._dice_images_on():
                await self._edit_manifest_text(channel, dice_msg, text, final)
            else:
                try:  # kept, nothing new: the embed with the die stays, only the buttons go
                    await dice_msg["message"].edit(view=None)
                except discord.HTTPException:
                    pass
            await self._finish_manifest(channel, guild_id, lines, resolved=resolved,
                                        result=final, who=who, said=said)

        return _decide

    async def _edit_manifest_text(self, channel, dice_msg: dict, text: str, result) -> None:
        """Replace the kept Manifest result with ``text`` (it gained Perils/containment lines)."""
        shown = (await self._result_edit(text, result.test.roll, palette_for(result.test), large=True)
                 if self._dice_images_on() else {"content": text})
        try:
            await dice_msg["message"].edit(**shown, view=None)
        except discord.HTTPException:
            await self._rt._send_with_retry(channel, text)

    def _resolve_warp_consequences(self, state, who, resolved, result) -> list[str]:
        """Resolve the Perils-of-the-Warp risk a manifest just created (ADR 022). A Push-Fumble
        triggers Perils immediately (IM p.163); otherwise, if Warp Charge now exceeds the Threshold,
        the psyker makes the Challenging containment Test — on success the energy is held (powers
        turn Overt), on failure Perils erupt. Timing note: IM runs the containment check at the
        psyker's end of turn; the conversational loop has no hard turn boundary, so we resolve it at
        the end of the manifesting action — deterministic and visible rather than left to the LLM."""
        consq = combat.resolve_warp_consequences(
            self._rt._profile,
            immediate_perils=result.immediate_perils,
            over_threshold=result.over_threshold,
            warp_charge=result.warp_charge,
            threshold=result.threshold,
            contain_base=resolved.contain_base,
            character=who,
            rng=self._rt._rng,
        )
        if consq.reset_charge:
            state.reset_warp_charge(who)  # Perils resets Warp Charge to 0 and ends Sustained powers
        return consq.lines
