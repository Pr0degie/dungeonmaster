"""Discord commands for the dice/rules surface: !roll/!test, dice+manifest buttons, auto-combat,
!turn/!order, !rules, !damage/!heal. Shared state lives on SessionRuntime (dmbot/runtime.py);
cross-cog flow goes through its hooks (ADR 029). Bot replies are German; logs English.

The NPC commands (!npc, !npcmem, !agenda, !agenden) live in the sub-cog ``npccog.py`` (ADR 039).
Method groups of ``DiceCog`` live as mixins in ``dmbot/voice/dice/`` (ADR 065): ``routing`` —
which roll a turn asks for.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import discord
from discord.ext import commands

from ..dice_assets import DiceAssetStore
from ..dice_images import (
    flight_seconds,
    get_dice_gif_async,
    get_dice_image_async,
    get_target_image_async,
    palette_for,
    prepare_throw_async,
    roll_image_value,
)
from ..llm.roll_router import (
    MarkerRepeats, OpenRolls, marker_decides,
    roll_button_source,
)
from ..discord_ui.dice import (
    DiceTestView, result_embed, result_picture, target_embed, target_text, throw_embed, throw_link_embed,
)
from ..discord_ui.fate import FateView
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
from .dice.routing import RollRoutingMixin

log = logging.getLogger(__name__)

# "für"/"fuer"/"for" as a word — the marker grammar's name separator (rules/marker.py).
_FUER_WORD_RE = re.compile(r"\b(?:für|fuer|for)\b", re.IGNORECASE)

# Seconds after the throw GIF has landed before the static result replaces it (D128).
REVEAL_GRACE_S = 1.0
# Stored flight GIF (ADR 064): clients start it a little after the edit lands (download).
CLIENT_START_S = 0.3


# The way out of the power target picker: the power hit a thing or someone the state does not know.
_NO_TARGET = "Niemand davon — nur erzählen"


class DiceCog(RollRoutingMixin, commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime
        runtime.handle_dice = self._handle_dice          # hook: DMCog delivery posts the dice button
        runtime.post_turn_order = self._post_turn_order  # hook: VoiceCog !join posts the turn panel
        runtime.cancel_roll_waits = self._cancel_all_roll_waits  # hook: VoiceCog !leave ends the session
        # (cid, name) pairs already warned about an untracked party psyker — keep it one-time so the
        # channel isn't spammed every Manifest Test.
        self._warp_untracked_warned: set[tuple[int, str]] = set()
        # The repeat safety net (D140): marker requests the previous turn left unrolled, per channel.
        self._repeats = MarkerRepeats()
        # One narration for all rolls of a turn (D152): the open buttons per channel, and the
        # task that ends the wait when somebody never rolls.
        self._open_rolls = OpenRolls()
        self._roll_waits: dict[int, asyncio.Task] = {}
        # Running throw animations (cosmetic message edits) — referenced so they aren't collected.
        self._presentations: set[asyncio.Task] = set()
        # Throw GIFs stored once in Discord (ADR 064); None = upload per roll.
        spec = str(runtime._dice_asset_channel or "")
        self._assets: DiceAssetStore | None = DiceAssetStore(spec) if spec else None
        # How long the result edit (an upload) takes — learnt per roll, so it starts early enough.
        self._upload_lead_s = 1.0

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Store the throw GIFs in each guild's storage channel (once; later starts only re-fetch)."""
        if self._assets is None or not self._dice_animation_on():
            return
        for guild in self.bot.guilds:
            self._spawn_presentation(self._assets.ensure(guild))

    async def _handle_dice(self, channel) -> None:
        """Post the turn's dice button. With the router on, who decides depends on who narrated
        (D140): on a Claude turn a valid inline ``<<TEST>>`` marker is rolled as written and the
        router only classifies when there is no (valid) marker; on an Ollama turn the router wins
        (D43) and the markers are discarded — except a marker repeated from the previous turn
        with no roll in between, which the safety net honours. Markers post alone when the router
        is off. Runs concurrently with playback (D40) so the button appears while the DM still speaks."""
        cid = self._rt._brain_channel(channel)
        markers = self._rt._brain.take_pending_tests(cid)
        spoken = self._spoken(cid)  # now: the next turn replaces the actions
        # This answer's buttons are one batch (D152). A roll that is finished but not narrated
        # yet keeps its wait — this answer was generated before it and did not take it along —
        # and the new buttons join that batch.
        if not (cid in self._roll_waits and self._rt._brain.waiting_turn(cid)):
            self._open_rolls.turn(cid)
            self._cancel_roll_wait(cid)
        # Psychic Manifest requests (ADR 022) are independent of the skill-roll router: each gets
        # a button so the engine rolls the Manifest Test + bookkeeps Warp Charge. Taken first so
        # a test for the same psyker (router or marker) can be dropped — no double roll.
        manifests = self._rt._brain.take_pending_manifests(cid)
        manifesting = self._manifesting(manifests)
        source = roll_button_source(self._rt._roll_router, len(markers))
        # The buttons appear one after another, a classifier call apart: until the last one is
        # decided, a roll already finished is not the turn's last.
        self._open_rolls.deciding(cid, True)
        try:
            if source == "router":
                # The narrator of the markers' own turn, recorded when they were queued — not
                # last_llm_stats, which the next prose call may already have overwritten.
                if markers and marker_decides({"backend": self._rt._brain.tests_narrator(cid)}):
                    await self._markers_decide(channel, cid, markers, manifesting=manifesting,
                                               spoken=spoken)
                else:
                    await self._router_decides(channel, cid, markers, manifesting=manifesting,
                                               spoken=spoken)
            elif source == "marker":
                for req in markers:
                    await self._post_dice_button(channel, req,
                                                 said=self._said(spoken, req.target_name))
            for m in manifests:
                await self._post_manifest_button(channel, m, said=self._said(spoken, m.target_name))
        finally:
            self._open_rolls.deciding(cid, False)
            if cid in self._roll_waits and self._open_rolls.open(cid) == 0:
                # a roll finished while the buttons were still being decided and no other came
                self._start_roll_wait(channel, channel.guild.id if channel.guild else None, cid, 0.0)

    async def _post_dice_button(self, channel, req: TestRequest, *, said: str = "") -> None:
        """Post a test's dice button and count it as an open roll of the turn (D152) — counted
        first, so it is never clickable uncounted. A button that could not be posted is taken
        off the count again: nobody can press it."""
        cid = self._rt._brain_channel(channel)
        self._open_rolls.posted(cid)
        try:
            await self._send_dice_button(channel, req, said=said)
        except BaseException:
            self._open_rolls.withdrawn(cid)
            raise

    async def _send_dice_button(self, channel, req: TestRequest, *, said: str = "") -> None:
        """Resolve a test request (skill value + difficulty → target, all in code) and post its button.
        ``said`` is the roller's own line that asked for it ("" for a typed ``!test``)."""
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
        text = f"🎲 Probe angefordert{note}:"
        # Pick the throw now and render its groundwork, so the click only renders the landing.
        # Cosmetic, in the background: the button does not wait for it.
        prep = (self._prepare_throw()
                if self._dice_animation_on() and resolved.target is not None else None)
        view = DiceTestView(label, self._make_dice_roll(channel, req, resolved, prep=prep, said=said))
        image = await get_target_image_async(resolved.target) if self._dice_images_on() else None
        if image is not None:  # the steel "≤target" die; a free !roll / no sheet value has none
            embed, file = target_embed(image)
            text = f"{text} {target_text(resolved.target)}"
            try:
                await self._rt._send_with_retry(channel, text, view=view, embed=embed, file=file)
                return
            except Exception:  # cosmetic — never lose the dice button over its picture
                log.warning("dice button with target die failed — posting it without", exc_info=True)
        await self._rt._send_with_retry(channel, text, view=view)

    def _make_dice_roll(self, channel, req: TestRequest, resolved, *, prep=None, said: str = ""):
        """Build the roll callback for a dice button: the engine rolls + resolves, the message is
        replaced with the result, and it's fed back so the DM narrates the consequence.

        A failed test by a character with Fate left (ADR 063) first gets the Fate choice; the
        narration waits for it, so each test is narrated exactly once."""
        skill = req.skill or "Probe"
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            guild_id = channel.guild.id if channel.guild else None
            self._repeats.rolled(self._rt._brain_channel(channel))  # a roll decides the moment (D140)
            result, line, face = self._roll_test_face(resolved, skill, who)
            log.info("%s", line)  # `line` already starts with 🎲 (describe_result_de)
            # The dice message can be replaced by the throw (a new message below it), so the
            # animation and the Fate choice share one handle to whichever is current.
            dice_msg = {"message": interaction.message}
            pc = self._fate_holder(channel, who) if result is not None and not result.success else None
            view = None
            if pc is not None:
                view = FateView(
                    pc.fate_available,
                    self._make_fate_decision(channel, guild_id, dice_msg, resolved,
                                             skill, who, result, line, said=said),
                    timeout=float(self._rt._fate_wait_seconds),
                )
            if self._dice_animation_on() and resolved.target is not None:
                # Cosmetic, in its own task: the throw GIF, then the result (+ Fate choice). The
                # engine has resolved already, and the DM is fed below without waiting for it.
                self._spawn_presentation(self._animate_result(
                    channel, dice_msg, target=resolved.target, line=line, face=face,
                    palette=palette_for(result), view=view, prep=prep,
                ))
            else:
                await self._show_result(channel, interaction.message, line, face,
                                        palette_for(result), view)  # result (+ Fate choice)
            if view is not None:
                return  # the Fate decision narrates
            await self._finish_roll(channel, guild_id, result, line, skill, who, said=said)

        return _roll

    def _roll_test(self, resolved, skill: str, who: str | None):
        """One roll through the engine → ``(TestResult | None, German line)``."""
        result, line, _ = self._roll_test_face(resolved, skill, who)
        return result, line

    def _roll_test_face(self, resolved, skill: str, who: str | None):
        """:meth:`_roll_test` plus the raw die face rolled (for the result thumbnail):
        ``(TestResult | None, German line, face)``."""
        if resolved.target is None:  # no character/skill value — roll, ask them to compare
            d = engine.roll(self._rt._profile.dice, self._rt._rng)
            return None, f"🎲 {skill}: {d.total} — kein hinterlegter Wert, vergleicht mit eurem Bogen.", d.total
        result = engine.scope_doubles(
            self._rt._profile,
            engine.resolve_test(self._rt._profile, resolved.target, self._rt._rng),
            skill,
        )
        return result, engine.describe_result_de(
            result, skill=skill, character=who, difficulty=resolved.difficulty
        ), result.roll

    def _dice_images_on(self) -> bool:
        """Dice result thumbnails on?"""
        return bool(self._rt._dice_images)

    def _dice_animation_on(self) -> bool:
        """Throw animation on? Needs dice images."""
        return self._dice_images_on() and bool(self._rt._dice_animation)

    async def _show_result(self, channel, message, line: str, face: int | None, palette: str,
                           view) -> None:
        """Edit the button message into the result (+ ``view``, the Fate choice); if it can't be
        edited, post the line (and the view) as a new message."""
        shown = await self._result_edit(line, face, palette, large=True)
        try:
            await message.edit(**shown, view=view)
        except discord.HTTPException:
            await self._rt._send_with_retry(channel, line, view=view)

    def _spawn_presentation(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._presentations.add(task)

        def _done(t: asyncio.Task) -> None:
            self._presentations.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("dice presentation failed", exc_info=t.exception())

        task.add_done_callback(_done)
        return task

    def _prepare_throw(self) -> asyncio.Task:
        """Pick the next throw and render its groundwork in the background, so a click only
        renders the landing (ADR 064). Every caller goes through here: the tests replace
        ``prepare_throw_async`` on this module's namespace, and only a function defined in this
        module sees that."""
        return self._spawn_presentation(prepare_throw_async())

    async def _animate_result(self, channel, dice_msg: dict, *, target: int, line: str, face: int | None,
                              palette: str, view, prep=None) -> None:
        """Presentation only, two edits of the dice message: the throw GIF in place of the target
        picture (the text stays — only the picture changes), then, once it has played, the static
        result (+ ``view``); edit in place, not a new message (ADR 064 amendment). No GIF (render failed, value outside 1–100) → straight to the result.
        A deleted message ends it quietly, unless a Fate choice still needs a home (it carries
        the narration, so it is posted anew)."""
        started = time.monotonic()
        seed = await prep if prep is not None else None  # the throw prepared at post time
        assets = self._assets
        link = (assets.url(getattr(channel, "guild", None), seed, palette)
                if assets is not None and seed is not None and face is not None else None)
        if link is not None:
            await self._animate_stored(channel, dice_msg, link=link, seed=seed, line=line, face=face,
                                       palette=palette, view=view, started=started, target=target)
            return
        anim = await get_dice_gif_async(target, face, palette, seed)
        if anim is not None:
            gif, landed = anim
            built = time.monotonic()
            embed, file = throw_embed(gif)
            try:
                await dice_msg["message"].edit(embed=embed, attachments=[file])  # only the picture
            except discord.NotFound:
                await self._message_gone(channel, line, view)
                return
            except discord.HTTPException:
                log.warning("dice throw edit failed — showing the result directly", exc_info=True)
            else:
                log.info("🎲 throw gif: built %d ms, in Discord %d ms after the click (%d KiB)",
                         (built - started) * 1000, (time.monotonic() - started) * 1000,
                         gif.stat().st_size // 1024)
                # Reveal once the die has landed, plus a grace second: clients start the GIF a
                # moment late (download), and the landing should be seen before it's swapped.
                await asyncio.sleep(landed + REVEAL_GRACE_S)
        shown = await self._result_edit(line, face, palette, large=True)
        try:
            await dice_msg["message"].edit(**shown, view=view)  # the result
        except discord.NotFound:
            await self._message_gone(channel, line, view)
        except discord.HTTPException:
            await self._rt._send_with_retry(channel, line, view=view)

    async def _animate_stored(self, channel, dice_msg: dict, *, link: str, seed: int, line: str,
                              face: int, palette: str, view, started: float, target: int) -> None:
        """:meth:`_animate_result` with a flight GIF stored in Discord (ADR 064): the throw only
        points at it (no upload), and the result picture — uploaded so it stays in the history —
        starts early by the learnt upload time, to land with the die."""
        try:
            await dice_msg["message"].edit(embed=throw_link_embed(link),  # only the picture
                                           attachments=[])
        except discord.NotFound:
            await self._message_gone(channel, line, view)
            return
        except discord.HTTPException:
            log.warning("dice throw edit failed — showing the result directly", exc_info=True)
            await self._show_result(channel, dice_msg["message"], line, face, palette, view)
            return
        shown_at = time.monotonic()
        shown = await self._result_edit(line, face, palette, large=True)  # ready before the wait
        lead = self._upload_lead_s
        await asyncio.sleep(max(0.0, flight_seconds(seed, palette) + CLIENT_START_S - lead))
        sent = time.monotonic()
        try:
            await dice_msg["message"].edit(**shown, view=view)  # the result
        except discord.NotFound:
            await self._message_gone(channel, line, view)
            return
        except discord.HTTPException:
            await self._rt._send_with_retry(channel, line, view=view)
            return
        took = time.monotonic() - sent
        self._upload_lead_s = min(3.0, max(0.2, 0.7 * lead + 0.3 * took))
        log.info("🎲 throw gif (stored): in Discord %d ms after the click; result upload %d ms "
                 "(lead %.1f → %.1f s)", (shown_at - started) * 1000, took * 1000, lead,
                 self._upload_lead_s)

    async def _message_gone(self, channel, line: str, view) -> None:
        if view is None:
            log.info("dice message deleted during the throw animation — result stays unshown there")
            return
        await self._rt._send_with_retry(channel, line, view=view)

    async def _result_edit(self, text: str, face: int | None, palette: str, *,
                           large: bool = False) -> dict:
        """The ``message.edit`` arguments that show a dice result: plain text as before, or (dice
        images on) an embed carrying the same line with the rolled die as a thumbnail — ``large``
        for a dice-button test, whose target and throw are big too. The palette comes from the
        engine's critical/fumble flags (:func:`palette_for`)."""
        if not self._dice_images_on():
            return {"content": text}
        image = await get_dice_image_async(face, palette)
        if large:  # a dice-button test: the line as message text, the die alone in its box
            if image is None:
                return {"content": text, "embed": None, "attachments": []}
            embed, file = result_picture(image)
            return {"content": text, "embed": embed, "attachments": [file]}
        embed, file = result_embed(text, image, palette)
        return {"content": None, "embed": embed, "attachments": [file] if file else []}

    def _fate_holder(self, channel, who: str | None):
        """The player character who may spend Fate on this failed test, or ``None`` (ADR 063)."""
        profile = self._rt._profile
        if profile is None or not profile.fate_enabled() or not who:
            return None
        state = self._rt._state.get(self._rt._brain_channel(channel))
        pc = state.find(who) if state is not None else None
        if pc is None or pc.is_npc or pc.fate_available <= 0:
            return None
        return pc

    def _make_fate_decision(self, channel, guild_id, dice_msg, resolved, skill, who, result, line,
                            *, said: str = ""):
        """The Fate choice's callback: spend → the state books the point, the engine rerolls and
        the second result stands (IM p.220); keep / timeout → the first result stands. Then the
        normal finish — narration, or the damage flow for a hit."""
        if not isinstance(dice_msg, dict):  # a bare message (callers without a throw)
            dice_msg = {"message": dice_msg}

        async def _decide(interaction, spend: bool) -> None:
            message = dice_msg["message"]  # the throw may have replaced the button message
            final_result, final_line = result, line
            content = line
            face = None
            cid = self._rt._brain_channel(channel)
            state = self._rt._state.get(cid)
            if spend and state is not None and state.spend_fate(who):
                left = state.find(who).fate_available
                final_result, reroll, face = self._roll_test_face(resolved, skill, who)
                final_line = (f"🙏 {who} gibt einen Schicksalspunkt aus (noch {left}) und würfelt "
                              f"neu — dieses Ergebnis gilt: {reroll}")
                content = f"{line}\n{final_line}"
                log.info("%s", final_line)
                self._rt._persist_and_refresh(channel)
            rerolled = content != line
            if rerolled and self._dice_animation_on() and resolved.target is not None:
                # The reroll is thrown like the first roll (cosmetic task); the DM is fed now.
                self._spawn_presentation(self._animate_result(
                    channel, dice_msg, target=resolved.target, line=content, face=face,
                    palette=palette_for(final_result), view=None,
                    prep=self._prepare_throw(),
                ))
                await self._finish_roll(channel, guild_id, final_result, final_line, skill, who, said=said)
                return
            if not self._dice_images_on():
                shown: dict = {"content": content}
            elif not rerolled:
                shown = {}  # kept: the embed with the first die stays, only the buttons go
            else:  # rerolled: both lines, and the die of the result that stands
                shown = await self._result_edit(content, face, palette_for(final_result), large=True)
            try:
                await message.edit(**shown, view=None)
            except discord.HTTPException:
                if rerolled:
                    await self._rt._send_with_retry(channel, final_line)
            await self._finish_roll(channel, guild_id, final_result, final_line, skill, who, said=said)
        return _decide

    async def _finish_roll(self, channel, guild_id, result, line: str, skill: str, who, *,
                           said: str = "") -> None:
        """Feed the final result to the DM and narrate it (or hand a hit to the damage flow).
        ``said`` is the roller's own line of the turn — a hit reads its target from it."""
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
            if await self._begin_attack_damage(channel, attacker=who, result=result, said=said):
                return  # the damage flow narrates once a target is chosen/auto-applied
        await self._narrate_rolls(channel, guild_id)

    def _cancel_roll_wait(self, cid: int) -> None:
        task = self._roll_waits.pop(cid, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _narrate_rolls(self, channel, guild_id) -> None:
        """A roll reached its final result and is fed to the DM: narrate it — unless other
        rolls of the same turn are still open (D152). Then the narration waits for them, so
        two players acting in one turn get one answer; a roll nobody makes holds it for at most
        ``DM_ROLL_BATCH_WAIT_SECONDS`` (0 = every roll narrated on its own)."""
        cid = self._rt._brain_channel(channel)
        wait = float(self._rt._roll_batch_wait_seconds)
        last = self._open_rolls.finished(cid)
        self._cancel_roll_wait(cid)
        if last or wait <= 0:
            await self._rt.run_and_deliver(channel, guild_id)
            return
        if self._open_rolls.open(cid):
            log.info("🎲 Erzählung wartet auf %d weitere Probe(n) dieses Zugs (höchstens %.0f s)",
                     self._open_rolls.open(cid), wait)
        else:
            log.info("🎲 Erzählung wartet, bis die Proben dieses Zugs vergeben sind")
        self._start_roll_wait(channel, guild_id, cid, wait)

    def _start_roll_wait(self, channel, guild_id, cid: int, wait: float) -> None:
        self._cancel_roll_wait(cid)
        task = asyncio.create_task(self._narrate_after_wait(channel, guild_id, cid, wait))
        task.add_done_callback(self._log_roll_wait)
        self._roll_waits[cid] = task

    def _cancel_all_roll_waits(self) -> None:
        """The session ends (``!leave``, shutdown): no narration may fire after it."""
        for cid in list(self._roll_waits):
            self._cancel_roll_wait(cid)
        self._open_rolls = OpenRolls()

    async def cog_unload(self) -> None:
        self._cancel_all_roll_waits()

    async def _narrate_after_wait(self, channel, guild_id, cid: int, wait: float) -> None:
        await asyncio.sleep(wait)
        self._roll_waits.pop(cid, None)
        still_open = self._open_rolls.open(cid)
        self._open_rolls.release(cid)
        if not self._rt._brain.waiting_turn(cid):
            return  # a player turn took the result along meanwhile — nothing left to tell
        if still_open:
            log.info("🎲 %d Probe(n) nach %.0f s nicht gewürfelt — die Erzählung geht ohne sie weiter",
                     still_open, wait)
        await self._rt.run_and_deliver(channel, guild_id)

    @staticmethod
    def _log_roll_wait(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            log.error("narration after the roll wait failed", exc_info=task.exception())

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
        text = f"🎲 `{dice}` → **{result.total}**{detail}"
        face = roll_image_value(result)  # the total, only if a die image exists for it (≤ 100)
        if not self._dice_images_on() or face is None:
            await ctx.send(text)
            return
        # A free roll has no test outcome → no critical/fumble → the default palette.
        image = await get_dice_image_async(face, palette_for(None))
        embed, file = result_embed(text, image, palette_for(None))
        if file is None:
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=embed, file=file)

    def _test_spec_with_name(self, spec: str, author) -> str:
        """``!test`` without "für" (D131): a character named at the end ("… Sezgin") becomes the
        roller, otherwise the caller's own character does. With "für" the spec stays as typed."""
        if _FUER_WORD_RE.search(spec):
            return spec
        store = self._rt._characters
        words = spec.split()
        if store is not None:
            for n in (2, 1):  # "Fridolin Feuchtgebietheld" before "Fridolin"
                if len(words) > n and store.get(" ".join(words[-n:])) is not None:
                    return f"{' '.join(words[:-n])} für {' '.join(words[-n:])}"
            own = self._rt.character_name_for(getattr(author, "id", None),
                                              getattr(author, "display_name", ""))
            if own and store.get(own) is not None:
                return f"{spec} für {own}"
        return spec

    @commands.command(name="test")
    async def test(self, ctx: commands.Context, *, spec: str = "") -> None:
        """Manually request a test: `!test Wahrnehmung Schwer` rolls for your own character,
        `!test Wahrnehmung Sezgin` (or `für Sezgin`) for someone else's. Posts a dice button."""
        if self._rt._profile is None:
            await ctx.send("Keine Würfel-Engine geladen (Systemprofil fehlt) — siehe Log.")
            return
        if not spec.strip():
            await ctx.send("Nutzung: `!test <Fertigkeit> [Schwierigkeit] [Name]` — ohne Name für deine Figur.")
            return
        spec = self._test_spec_with_name(spec, ctx.author)
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
            await ctx.send("Der Regel-Assistent ist gerade nicht erreichbar (das LLM antwortet nicht — `!backend` zeigt den Zustand, Details im Log).")
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
