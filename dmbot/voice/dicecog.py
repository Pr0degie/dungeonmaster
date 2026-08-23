"""Discord commands for the dice/rules surface: !roll/!test, dice+manifest buttons, auto-combat,
!turn/!order, !rules, !npc/!damage/!heal. Shared state lives on SessionRuntime (dmbot/runtime.py);
cross-cog flow goes through its hooks (ADR 029). Bot replies are German; logs English.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ..llm.roll_router import roll_button_source
from ..discord_ui.dice import DiceTestView
from ..discord_ui.turnorder import TurnOrderView
from ..discord_ui.rules import RulesView
from ..discord_ui.target import TargetSelectView
from ..rules import combat, engine
from ..rules.characters import (
    Character, resolve_manifest_request, resolve_target,
)
from ..rules.marker import ManifestRequest, TestRequest, extract_tests
from ..rules.summary import rules_pages_de
from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class DiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime
        runtime.handle_dice = self._handle_dice          # hook: DMCog delivery posts the dice button
        runtime.post_turn_order = self._post_turn_order  # hook: VoiceCog !join posts the turn panel
        # (cid, name) pairs already warned about an untracked party psyker — keep it one-time so the
        # channel isn't spammed every Manifest Test (finding #2).
        self._warp_untracked_warned: set[tuple[int, str]] = set()

    async def _handle_dice(self, channel) -> None:
        """Post the turn's dice button. The router wins when it's on (D43, flips D40's dedupe):
        the model's inline ``<<TEST>>`` requests are drained and **discarded** — the constrained
        classifier picks reliable skills, the narration model doesn't (seen live: Heimlichkeit
        for an attack). Markers post only as the fallback when the router is off. Runs
        concurrently with playback (D40) so the button appears while the DM still speaks."""
        markers = self._rt._brain.take_pending_tests(self._rt._brain_channel(channel))
        source = roll_button_source(self._rt._roll_router, len(markers))
        if source == "router":
            if markers:
                log.info("🎲 %d Inline-Marker verworfen — der Router entscheidet (D43)", len(markers))
            await self._post_router_dice(channel)
        elif source == "marker":
            for req in markers:
                await self._post_dice_button(channel, req)
        # Psychic Manifest requests (ADR 022) are independent of the skill-roll router: post a
        # button for each so the engine rolls the Manifest Test + bookkeeps Warp Charge.
        for m in self._rt._brain.take_pending_manifests(self._rt._brain_channel(channel)):
            await self._post_manifest_button(channel, m)

    def _toughness_bonus(self, target: Character | None) -> int:
        """Toughness Bonus for a player from the sheet: the profile's soak characteristic (IM: Tgh),
        rendered per soak mode (IM: tens digit). 0 if no profile/character/characteristic."""
        return combat.toughness_bonus(self._rt._profile, self._rt._characters, target)

    async def _post_router_dice(self, channel) -> None:
        """Roll-detection router (ADR 014): classify each player action of the turn in a separate
        constrained-JSON call and post a dice button per action that needs a test. Skips silently
        when there's no player action this turn (e.g. a post-roll narration) or no matching
        character.

        One action per *speaker* (D111). Until then only the last buffered line was classified, so
        in a turn where two players each declared something only whoever spoke last could ever be
        asked to roll — the other declaration vanished without a log line. The character always
        comes from the speaker of the action, never from who presses the button, so a player may
        press a team-mate's button without stealing their test.

        Deliberately sequential, not gathered: the brain exposes the router's raw verdict as a
        single ``last_router`` attribute that each call overwrites, so parallel calls would
        cross-attribute the replay journal (ADR 046). This runs off the hot path while the DM is
        speaking, and multi-speaker turns are the minority.
        """
        if self._rt._profile is None or self._rt._characters is None:
            return
        actions = self._rt._brain.last_actions(self._rt._brain_channel(channel))
        if not actions:
            return
        for name, text in actions:
            char = self._rt._characters.get(name)
            if char is None:
                continue
            # Constrain the classifier to this character's sheet: skills first, then any same-named
            # governing characteristic (skill_value falls back to those).
            skills = list(char.skills) + [c for c in char.characteristics if c not in char.skills]
            req = await self._rt._brain.classify_test(action=text, character=char.name, skills=skills)
            # Replay journal (ADR 046): the router's raw constrained-JSON verdict + parsed decision,
            # so dm-eval can re-run the classification offline. None (a failed call) records nothing.
            recorded = getattr(self._rt._brain, "last_router", None)
            if recorded is not None:
                self._rt.replay_note(channel, "router", {
                    "action": text, "character": char.name, "skills": skills, **recorded,
                })
            if req is not None:
                log.info("🎲 router: %s — '%s' → %s (%s)",
                         char.name, text[:50], req.skill, req.difficulty or "Standard")
                await self._post_dice_button(channel, req)

    async def _post_dice_button(self, channel, req: TestRequest) -> None:
        """Resolve a test request (skill value + difficulty → target, all in code) and post its button."""
        skill = req.skill or "Probe"
        resolved = resolve_target(
            self._rt._profile, self._rt._characters, skill=skill,
            target_name=req.target_name, difficulty=req.difficulty, modifier=req.modifier,
        )
        who = (resolved.character.name if resolved.character else req.target_name) or "Gruppe"
        if resolved.difficulty:
            diff = resolved.difficulty
        elif req.modifier is not None:
            diff = f"{req.modifier:+d}"
        else:
            diff = ""
        label = f"{who} würfelt: {skill}" + (f" ({diff})" if diff else "")
        note = "" if req.parsed else " (unklarer Marker — manuell prüfen)"
        await self._rt._send_with_retry(
            channel, f"🎲 Probe angefordert{note}:",
            view=DiceTestView(label, self._make_dice_roll(channel, req, resolved)),
        )

    def _make_dice_roll(self, channel, req: TestRequest, resolved):
        """Build the roll callback for a dice button: the engine rolls + resolves, the message is
        replaced with the result, and it's fed back so the DM narrates the consequence."""
        skill = req.skill or "Probe"
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            guild_id = channel.guild.id if channel.guild else None
            result = None
            if resolved.target is None:  # no character/skill value — roll, ask them to compare
                d = engine.roll(self._rt._profile.dice, self._rt._rng)
                line = f"🎲 {skill}: {d.total} — kein hinterlegter Wert, vergleicht mit eurem Bogen."
            else:
                result = engine.resolve_test(self._rt._profile, resolved.target, self._rt._rng)
                line = engine.describe_result_de(
                    result, skill=skill, character=who, difficulty=resolved.difficulty
                )
            log.info("%s", line)  # `line` already starts with 🎲 (describe_result_de)
            try:
                await interaction.message.edit(content=line, view=None)  # show result, drop button
            except discord.HTTPException:
                await self._rt._send_with_retry(channel, line)
            self._rt._brain.add_test_result(self._rt._brain_channel(channel), line)
            # Auto-combat (Phase 9): a successful attack rolls & applies weapon damage to a target
            # before the DM narrates, so the narration carries the consequence. Non-attacks, misses
            # and value-less rolls fall through to the normal immediate narration.
            if (
                result is not None
                and result.success
                and self._rt._profile is not None
                and self._rt._profile.combat_enabled()
                and self._rt._profile.is_attack_skill(skill)
            ):
                if await self._begin_attack_damage(channel, attacker=who, result=result):
                    return  # the damage flow narrates once a target is chosen/auto-applied
            await self._rt.run_and_deliver(channel, guild_id)

        return _roll

    async def _post_manifest_button(self, channel, req: ManifestRequest) -> None:
        """Resolve a Manifest request (power → Warp Rating + Difficulty + the psyker's Psi-Meisterschaft
        value, all in code) and post its button (ADR 022)."""
        resolved = resolve_manifest_request(
            self._rt._profile, self._rt._characters, power=req.power, target_name=req.target_name,
        )
        if resolved is None:  # no psyker block or the power isn't catalogued — note it, don't crash
            note = f"„{req.power}“" if req.power else "Kraft"
            await self._rt._send_with_retry(
                channel, f"🌀 Unbekannte psychische Kraft {note} — nicht im Regelprofil hinterlegt.",
            )
            return
        who = (resolved.character.name if resolved.character else req.target_name) or "Psioniker"
        diff = f" ({resolved.difficulty})" if resolved.difficulty else ""
        push = " · Push" if req.pushed else ""
        label = f"{who} manifestiert: {resolved.power}{diff}{push}"
        await self._rt._send_with_retry(
            channel, "🌀 Manifestation angefordert:",
            view=DiceTestView(label, self._make_manifest_roll(channel, req, resolved)),
        )

    def _make_manifest_roll(self, channel, req: ManifestRequest, resolved):
        """Build the roll callback for a Manifest button: the engine rolls the Psychic Mastery Test,
        bookkeeps Warp Charge against the Threshold, resolves Perils when triggered, persists the
        psyker's Warp Charge, and feeds every line back so the DM narrates the consequence."""
        power = resolved.power
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            guild_id = channel.guild.id if channel.guild else None
            cid = self._rt._brain_channel(channel)
            state = self._rt._state.get(cid)
            combatant = state.find(who) if (state and who) else None
            if resolved.target is None:  # no Psi-Meisterschaft value on the sheet — roll, ask to compare
                d = engine.roll(self._rt._profile.dice, self._rt._rng)
                lines = [f"🌀 {power}: {d.total} — kein Psi-Meisterschaft-Wert hinterlegt, "
                         "vergleicht mit eurem Bogen."]
            else:
                current = combatant.warp_charge if combatant is not None else 0
                result = engine.resolve_manifest(
                    self._rt._profile, test_target=resolved.target, power=power,
                    warp_rating=resolved.warp_rating, current_charge=current,
                    willpower_bonus=resolved.willpower_bonus, threshold=resolved.threshold,
                    pushed=req.pushed, rng=self._rt._rng,
                )
                lines = [engine.describe_manifest_de(result, character=who)]
                if state is not None and combatant is not None:
                    state.set_warp_charge(who, result.warp_charge)
                    if result.test.success and (resolved.stats or {}).get("duration", "") == "Anhaltend":
                        state.sustain_power(who, power)
                    lines += self._resolve_warp_consequences(state, who, resolved, result)
                    self._rt._persist_and_refresh(channel)
                elif state is not None and self._rt._characters and self._rt._characters.get(who):
                    # Known party psyker, but not seeded into this session's WorldState — Warp Charge
                    # would silently never accumulate (current_charge stays 0 each call) and Perils
                    # never fire. There is no safe single-character add on WorldState (seed_from_store
                    # rebuilds the whole state, add_npc would mistype a PC as an NPC), so warn the GM
                    # once instead of losing the resource silently (finding #2).
                    key = (cid, (who or "").lower())
                    if key not in self._warp_untracked_warned:
                        self._warp_untracked_warned.add(key)
                        log.warning("Warp charge not tracked: %s is not in the current encounter state", who)
                        lines.append(
                            f"⚠️ Warp-Aufladung wird nicht verfolgt — {who} ist nicht in der "
                            "aktuellen Szene/Encounter."
                        )
            line = "\n".join(lines)
            log.info("%s", lines[0])
            try:
                await interaction.message.edit(content=line, view=None)
            except discord.HTTPException:
                await self._rt._send_with_retry(channel, line)
            for ln in lines:
                self._rt._brain.add_test_result(cid, ln)
            await self._rt.run_and_deliver(channel, guild_id)

        return _roll

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

    async def _begin_attack_damage(self, channel, *, attacker: str | None, result) -> bool:
        """Start the auto-damage flow for a successful attack. Returns True if it took over (a target
        was auto-hit or a picker was posted — it will narrate); False if it couldn't (no weapon data
        or no target), so the caller narrates the hit plainly."""
        cid = self._rt._brain_channel(channel)
        state = self._rt._state.get(cid)
        if state is None:
            return False
        attacker_char = self._rt._characters.get(attacker) if self._rt._characters else None
        weapon, notation = self._choose_weapon(attacker_char)
        if not notation:
            return False  # no weapon damage data → can't auto-roll; narrate the hit plainly
        # Candidates: living NPCs (the usual enemy) first, then other party members (friendly fire).
        candidates = [n.name for n in state.npcs if n.wounds > 0]
        candidates += [
            c.name for c in state.characters if c.name.lower() != (attacker or "").lower()
        ]
        if not candidates:
            await self._rt._send_with_retry(
                channel,
                "💥 Treffer! Aber kein Ziel hinterlegt — `!npc add <Name> [Wunden]`, dann erneut würfeln.",
            )
            return False
        if len(candidates) == 1:
            await self._apply_attack_damage(
                channel, attacker=attacker, weapon=weapon, notation=notation,
                result=result, target_name=candidates[0],
            )
            return True

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
        """Roll the weapon's damage, subtract the target's soak (Toughness Bonus + armour), apply the
        rest to its wounds, persist, and feed the result back so the DM narrates the consequence."""
        cid = self._rt._brain_channel(channel)
        state = self._rt._state.get(cid)
        if state is None:
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
        state.apply_damage(target_name, outcome.damage.applied)
        updated = state.find(target_name)
        downed = updated is not None and updated.wounds <= 0
        line = engine.describe_damage_de(
            outcome.damage, attacker=attacker, target=target_name, weapon=weapon,
            new_wounds=updated.wounds if updated else 0,
            max_wounds=updated.max_wounds if updated else 0, downed=downed,
        )
        log.info("%s", line)
        await self._rt._send_with_retry(channel, line)
        self._rt._persist_and_refresh(channel)
        self._rt._brain.add_test_result(cid, line)
        await self._rt.run_and_deliver(channel, channel.guild.id if channel.guild else None)

    def _render_turn(self, key: int) -> str:
        order = self._rt._turn_order.get(key, [])
        if not order:
            return "Keine Teilnehmer erfasst — tretet dem Voice-Channel bei und nutzt `!turn`."
        i = self._rt._turn_index.get(key, 0) % len(order)
        seq = " → ".join(f"**{n}**" if j == i else n for j, n in enumerate(order))
        return f"🗡 Dran: **{order[i]}**\n{seq}"

    def _turn_step(self, key: int, step: int) -> None:
        order = self._rt._turn_order.get(key, [])
        if order:
            self._rt._turn_index[key] = (self._rt._turn_index.get(key, 0) + step) % len(order)

    async def _post_turn_order(self, channel) -> None:
        """(Re)post the turn-order panel, deleting the previous one so it doesn't duplicate."""
        key = self._rt._active_vc_id
        if key is None:
            await self._rt._send_with_retry(channel, "Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        await self._rt.clear_panel("_turn_message")

        async def advance() -> None:
            self._turn_step(key, +1)

        async def back() -> None:
            self._turn_step(key, -1)

        view = TurnOrderView(advance, back, lambda: self._render_turn(key))
        self._rt._turn_message = await self._rt._send_with_retry(channel, self._render_turn(key), view=view)

    @commands.command(name="roll")
    async def roll(self, ctx: commands.Context, *, dice: str = "1d100") -> None:
        """Roll raw dice through the engine: `!roll 1d100`, `!roll 2d10+3`. A smoke test."""
        try:
            result = engine.roll(dice, self._rt._rng)
        except engine.DiceError:
            await ctx.send(f"Unverständlicher Würfelausdruck `{dice}` — z. B. `1d100`, `2d10+3`.")
            return
        detail = ""
        if result.dice:
            parts = "+".join(str(d) for d in result.dice)
            if result.modifier:
                parts += f"{result.modifier:+d}"
            detail = f" ({parts})"
        await ctx.send(f"🎲 `{dice}` → **{result.total}**{detail}")

    @commands.command(name="test")
    async def test(self, ctx: commands.Context, *, spec: str = "") -> None:
        """Manually request a test: `!test Wahrnehmung Schwer für Tobi`. Posts a dice button."""
        if self._rt._profile is None:
            await ctx.send("Keine Würfel-Engine geladen (Systemprofil fehlt) — siehe Log.")
            return
        if not spec.strip():
            await ctx.send("Nutzung: `!test <Fertigkeit> [Schwierigkeit] [für <Name>]`.")
            return
        _, reqs = extract_tests(f"<<TEST {spec}>>", self._rt._profile)
        if not reqs:
            await ctx.send("Konnte daraus keine Probe lesen.")
            return
        await self._post_dice_button(ctx.channel, reqs[0])

    @commands.command(name="turn", aliases=["order"])
    async def turn(self, ctx: commands.Context) -> None:
        """Show / rotate the turn order ('whose turn'). Rebuilds it from the voice channel. Alias: !order"""
        if self._rt._active_vc_id is None:
            await ctx.send("Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        vc = ctx.voice_client
        if vc is not None and getattr(vc, "channel", None) is not None:
            self._rt._turn_order[self._rt._active_vc_id] = self._rt._build_turn_order(vc.channel)
            self._rt._turn_index.setdefault(self._rt._active_vc_id, 0)
        await self._post_turn_order(ctx.channel)

    @commands.command(name="rules", aliases=["regeln"])
    async def rules(self, ctx: commands.Context, *, question: str = "") -> None:
        """`!rules` blättert die Kurzregeln des aktiven Systems (◀/▶); `!rules <frage>` beantwortet
        eine Regelfrage aus dem Regelbuch (`!rules wie funktioniert ausweichen?`). Alias: !regeln"""
        if question.strip():
            await self._rules_question(ctx, question.strip())
            return
        if self._rt._profile is None:
            await ctx.send("Kein Systemprofil geladen — keine Regeln verfügbar (siehe Log).")
            return
        pages = rules_pages_de(self._rt._profile)
        if not pages:
            await ctx.send("Für dieses System sind keine Regeln hinterlegt.")
            return
        source = self._rt._profile.raw.get("_source", "") if isinstance(self._rt._profile.raw, dict) else ""
        view = RulesView(pages, self._rt._profile.display_name or self._rt._profile.name, source=source)
        await self._rt._send_with_retry(ctx.channel, view=view, embed=view.embed())

    async def _rules_question(self, ctx: commands.Context, question: str) -> None:
        """`!rules <frage>` — retrieve the matching rulebook chunks (English layout-soup) and let
        the LLM synthesise a short German rules answer from them (golden rule #7: grounded in the
        book, not the model's gut). Reading material, not a DM turn — never spoken."""
        if not self._rt._retriever.available():
            await ctx.send("Kein RAG-Store vorhanden — `!rules <frage>` braucht `data/vectordb/rag.db`.")
            return
        # Search the rules corpora that need LLM synthesis (English layout-soup): the Core Rulebook
        # plus the Inquisition Player's Guide (powers/talents) and the GM-Guide's safe reference
        # half (Radical Methods, philosophies). Curated German Weltwissen stays on `!lore`.
        hits = await self._rt._retriever.lookup(
            question, sources=("rulebook", "conditions", "player_guide", "gm_guide"),
            k=3, max_distance=0.55
        )
        if not hits:
            await ctx.send(
                f"Dazu finde ich nichts in den Regeltexten: *{question}*\n"
                f"(Ohne Frage zeigt `!rules` die Kurzregeln; Weltwissen: `!lore`.)"
            )
            return
        context = "\n\n".join(f"[{heading}]\n{text}" for _s, heading, text, _d in hits)
        for s, h, _t, d in hits:
            log.info("📖 !rules %r → %s:%r (d=%.2f)", question, s, h, d)
        system_name = (self._rt._profile.display_name or self._rt._profile.name) if self._rt._profile else "Imperium Maledictum"
        try:
            answer = await self._rt._brain.answer_rules(question, context, system_name=system_name)
        except Exception:
            log.exception("rules question LLM call failed")
            await ctx.send("Der Regel-Assistent ist gerade nicht erreichbar (läuft Ollama? siehe Log).")
            return
        if not answer:
            await ctx.send(f"Keine klare Regelauskunft möglich zu: *{question}*")
            return
        sources = ", ".join(dict.fromkeys(h for _s, h, _t, _d in hits))  # unique headings, in order
        embed = discord.Embed(
            title="📖 Regelauskunft", description=answer[:4000], color=discord.Color.blurple()
        )
        embed.add_field(name="Quelle (Regeltexte)", value=sources[:1000] or "Regelbuch", inline=False)
        embed.set_footer(text=f"Frage: {question[:200]}")
        await self._rt._send_with_retry(ctx.channel, embed=embed)

    @commands.command(name="damage", aliases=["schaden"])
    async def damage(self, ctx: commands.Context, name: str = "", amount: int = 0) -> None:
        """GM override: apply raw wounds. `!damage "<Name>" <Wunden>` (after soak — this is the
        final number); the name is matched exactly, so multi-word names need the quotes.
        Auto-combat does this for you on a hit; this is for adjudicated/out-of-band damage."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name or amount <= 0:
            await ctx.send("Nutzung: `!damage <Name> <Wunden>` (z. B. `!damage Kultist 5`).")
            return
        c = state.apply_damage(name, amount)
        if c is None:
            await ctx.send(f"Niemand namens **{name}** im Weltzustand (Charakter oder NSC).")
            return
        self._rt._persist_and_refresh(ctx.channel)
        downed = " — **kampfunfähig**" if c.wounds <= 0 else ""
        await ctx.send(f"💢 **{c.name}** −{amount} Wunden → {c.wounds}/{c.max_wounds}{downed}")

    @commands.command(name="heal", aliases=["heilung"])
    async def heal(self, ctx: commands.Context, name: str = "", amount: int = 0) -> None:
        """GM: restore wounds. `!heal "<Name>" <Wunden>` (clamps at max, clears 'kampfunfähig'
        above 0); exact name match, so multi-word names need the quotes."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name or amount <= 0:
            await ctx.send("Nutzung: `!heal <Name> <Wunden>`.")
            return
        c = state.heal(name, amount)
        if c is None:
            await ctx.send(f"Niemand namens **{name}** im Weltzustand.")
            return
        self._rt._persist_and_refresh(ctx.channel)
        await ctx.send(f"➕ **{c.name}** +{amount} Wunden → {c.wounds}/{c.max_wounds}")

    @commands.command(name="npc", aliases=["nsc"])
    async def npc(
        self, ctx: commands.Context, action: str = "", name: str = "",
        wounds: str = "", tb: str = "", armour: str = "",
    ) -> None:
        """Register an enemy the party can damage: `!npc add Kultist 10 3 2` (Wunden, ToughnessBonus,
        Rüstung). With a loaded adventure, `!npc add Alecto` fills the statblock from the
        compendium's npcs.json (Phase 10a) — explicit numbers still override. `!npc list` shows
        them. (NSC-Namen ohne Leerzeichen — z. B. `Raguel_der_Rote`.)

        Wounds/TB/armour are parsed tolerantly (str + manual ``int``) so a stray non-numeric token
        gives a clear usage hint instead of discord.py's raw ``BadArgument`` traceback — the error
        that blocked the Phase-9 live gate."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if action.lower() in ("", "list"):
            if not state.npcs:
                await ctx.send("Keine NSCs registriert. `!npc add <Name> [Wunden] [TB] [Rüstung]`.")
                return
            lines = "; ".join(
                f"{n.name} {n.wounds}/{n.max_wounds}" + (f" [{n.attitude}]" if n.attitude else "")
                for n in state.npcs
            )
            await ctx.send(f"**NSCs:** {lines}")
            return
        if action.lower() == "add":
            if not name:
                await ctx.send("Nutzung: `!npc add <Name> [Wunden] [ToughnessBonus] [Rüstung]`.")
                return
            # Compendium statblock (Phase 10a): a known adventure NPC brings its own values;
            # explicit numbers override field by field. No adventure → the old 10/0/0 defaults.
            block = self._rt._adventure.npc(name) if self._rt._adventure is not None else None
            try:
                w = int(wounds) if wounds else (block.wounds if block else 10)
                t = int(tb) if tb else (block.toughness_bonus if block else 0)
                a = int(armour) if armour else (block.armour if block else 0)
            except ValueError:
                await ctx.send(
                    "Wunden, ToughnessBonus und Rüstung müssen Zahlen sein. "
                    "Nutzung: `!npc add <Name> [Wunden] [TB] [Rüstung]` — z. B. `!npc add Kultist 10 3`. "
                    "(NSC-Namen ohne Leerzeichen, z. B. `Raguel_der_Rote`.)"
                )
                return
            display = block.name if block is not None else name  # canonical spelling from the sheet
            n = state.add_or_update_npc(
                display, wounds=w, max_wounds=w, toughness_bonus=t, armour=a,
                faction=block.faction if block is not None else "",
                goal=block.goal_de if block is not None else "",
            )
            self._rt._persist_and_refresh(ctx.channel)
            src = " *(Statblock aus dem Abenteuer)*" if block is not None and not wounds else ""
            await ctx.send(
                f"➕ NSC **{n.name}**: {n.wounds} Wunden, TB {n.toughness_bonus}, "
                f"Rüstung {n.armour}.{src}"
            )
            return
        await ctx.send("Nutzung: `!npc add <Name> [Wunden] [TB] [Rüstung]` oder `!npc list`.")

    @commands.command(name="npcmem")
    async def npcmem(self, ctx: commands.Context, name: str = "") -> None:
        """`!npcmem "<Name>"` — read-only debug view of an NPC's stored memories (ADR 044): gist,
        importance, source, believed flag. Editing stays out of scope (state is code-owned)."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name:
            with_mem = [n.name for n in state.npcs if n.memories]
            await ctx.send(
                'Nutzung: `!npcmem "<Name>"`. NSCs mit Erinnerungen: '
                + (", ".join(with_mem) if with_mem else "—")
            )
            return
        npc = next((n for n in state.npcs if n.name.lower() == name.strip().lower()), None)
        if npc is None:
            await ctx.send(f"Unbekannter NSC `{name}` — `!npc list` zeigt alle.")
            return
        if not npc.memories:
            await ctx.send(f"**{npc.name}** hat noch keine Erinnerungen.")
            return
        lines = [f"🧠 **{npc.name}** — Haltung: {npc.attitude or '—'}"
                 + (f", Fraktion: {npc.faction}" if npc.faction else "")]
        for i, m in enumerate(npc.memories):
            tags = [f"W{m.importance}", m.source]
            if not m.believed:
                tags.append("LÜGE aufgeflogen")
            quote = f" — Zitat: „{m.quote}“" if m.quote else ""
            lines.append(f"[{i}] ({', '.join(tags)}) {m.gist}{quote}")
        await self._rt._send_with_retry(ctx.channel, "\n".join(lines))

    @commands.command(name="agenda")
    async def agenda(self, ctx: commands.Context, name: str = "", *, goal: str = "") -> None:
        """`!agenda "<NSC>" <Ziel>` / `!agenda "<NSC>" weg` — set/change/remove an NPC's offscreen
        goal (ADR 049). Goals are human-set, never LLM output; the log survives removal."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        goal = goal.strip().strip('"„“').strip()
        if not name or not goal:
            await ctx.send(
                "Nutzung: `!agenda <NSC> \"<Ziel>\"` setzt/ändert ein Ziel, "
                "`!agenda <NSC> weg` entfernt es, `!agenden` listet alle."
            )
            return
        npc = next((n for n in state.npcs if n.name.lower() == name.strip().lower()), None)
        if npc is None:
            await ctx.send(f"Unbekannter NSC `{name}` — `!npc list` zeigt alle.")
            return
        if goal.lower() == "weg":
            if not npc.goal:
                await ctx.send(f"**{npc.name}** hat kein Ziel gesetzt.")
                return
            npc.goal = ""
            self._rt._persist_and_refresh(ctx.channel)
            await ctx.send(f"🎯 Ziel von **{npc.name}** entfernt (Verlauf bleibt erhalten).")
            return
        npc.goal = goal
        self._rt._persist_and_refresh(ctx.channel)
        note = ""
        agenda_count = sum(1 for n in state.npcs if n.goal)
        if agenda_count > 5:
            note = (
                f"\n⚠️ {agenda_count} Agenda-NSCs — mehr als ~5 fressen Kontext und "
                "Extraktions-Tokens (ADR 049)."
            )
        await ctx.send(f"🎯 **{npc.name}** verfolgt jetzt: {goal}{note}")

    @commands.command(name="agenden")
    async def agenden(self, ctx: commands.Context) -> None:
        """`!agenden` — list every agenda NPC's goal + its most recent offscreen steps."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        agenda_npcs = [n for n in state.npcs if n.goal]
        if not agenda_npcs:
            await ctx.send("Keine Agenda-NSCs. `!agenda <NSC> \"<Ziel>\"` setzt ein Ziel.")
            return
        lines: list[str] = []
        for npc in agenda_npcs:
            dead = " (tot)" if npc.wounds <= 0 else ""
            lines.append(f"🎯 **{npc.name}**{dead} — {npc.goal}")
            for step in npc.agenda_log[-3:]:
                ts = f" [{step.ts_ingame}]" if step.ts_ingame else ""
                lines.append(f"  •{ts} {step.text}")
        await self._rt._send_with_retry(ctx.channel, "\n".join(lines))
