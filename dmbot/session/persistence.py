"""Persistence and prompt context for :class:`~dmbot.runtime.SessionRuntime`: load or seed a
channel's world state, save it on every change and refresh what the brain is told about it
(state summary, scene card, psyker and augmetic blocks, scene guidance), plus the Chekhov list.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``. Where the session files live
(``session_file`` and the ``_*_path`` helpers) stays in runtime.py, next to ``_DATA_DIR``.
"""
from __future__ import annotations

import logging

from ..memory import chekhov as chekhov_mod
from ..memory import npc_memory as npc_memory_mod
from ..memory.state import WorldState, world_state_summary_de
from ..rules.characters import CharacterStore

log = logging.getLogger(__name__)


class PersistenceMixin:
    """World-state persistence and prompt refresh. Mixed into ``SessionRuntime``; holds no state
    of its own."""

    def chekhov_list(self, channel_id: int) -> chekhov_mod.ChekhovList:
        """This channel's Chekhov list, lazily loaded (a missing/broken file is an empty list)."""
        if channel_id not in self._chekhov_lists:
            self._chekhov_lists[channel_id] = chekhov_mod.ChekhovList.load(
                self._chekhov_path(channel_id)
            )
        return self._chekhov_lists[channel_id]

    def save_chekhov(self, channel_id: int) -> None:
        """Persist this channel's Chekhov list (atomic, like state.json); best-effort."""
        try:
            self.chekhov_list(channel_id).save(self._chekhov_path(channel_id))
        except OSError:
            log.exception("could not persist the chekhov list for channel %s", channel_id)

    def _load_or_seed_state(self, channel_id: int) -> WorldState:
        """Load the channel's saved state, or seed a fresh one from the sheet (ADR 004/015) on the
        first ever join. Either way it's the live mutable layer for this session."""
        existing = WorldState.load(self._state_path(channel_id))
        if existing is not None:
            log.info("loaded world state from %s", self._state_path(channel_id))
            return existing
        store = self._characters or CharacterStore()
        system = self._profile.name if self._profile else ""
        return WorldState.seed_from_store(store, system=system, session_id=str(channel_id))

    def _persist_and_refresh(self, channel) -> None:
        """Save the channel's world state to disk and re-inject recap + the compact state block into
        the brain's prompt, so the next DM turn sees current HP/conditions (and so the gate's 'HP
        survives a restart' holds — we save on every change)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return
        try:
            state.save(self._state_path(cid))
        except OSError:
            log.exception("could not persist world state for channel %s", cid)
        adventure_block = ""
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        if self._adventure is not None:
            adventure_block = self._adventure.adventure_block_de(
                state.scene_id,
                resolved_ids=state.resolved_ids(state.scene_id),
                dead_npcs=[n.name for n in state.npcs if n.wounds <= 0],
                include_guidance=self._guidance_due(cid),
            )
        # Which registered NPCs are actually HERE (D107). Once scene NPCs are registered on entry
        # the roster keeps growing, and an unscoped "NSCs in der Szene" line would hand the model
        # the seneschal from scene one as present in scene four (ADR 057). Since ADR 062 "here" also counts the people seen in this scene in person, so an
        # improvised thug is not listed as "anderswo" right after he walked in.
        summary = world_state_summary_de(
            state,
            present=([*scene.npcs_here, *(n.name for n in self._scene_npcs(state))]
                     if scene is not None else None),
            clocks=self.clocks_enabled,
        )
        chekhov_block = chekhov_mod.chekhov_block_de(self.chekhov_list(cid).top_open())
        sheet_block = self._characters.sheet_block_de() if self._characters is not None else ""
        for block in (sheet_block, self._psyker_block(state), self._augmetic_block(), chekhov_block):
            if block:
                summary = f"{summary}\n\n{block}" if summary else block
        npc_block = ""
        if self._npc_memory:
            npc_block = npc_memory_mod.npc_memory_block_de(
                self._scene_npcs(state), top_k=self._npc_memory_top_k
            )
        self._brain.set_context(
            cid, recap=state.recap, state_summary=summary, adventure_block=adventure_block,
            npc_memory_block=npc_block,
        )

    def _guidance_due(self, channel_id: int) -> bool:
        """Whether the current scene's standing GM guidance rides in the next prompt.

        Guidance in *every* turn's card is read as a standing order and parroted (ADR 059). The
        loader renders it as a one-off impulse and leaves the WHEN to the caller: first turn in a
        scene, then every ``DM_GUIDANCE_EVERY``-th turn. 1 = every turn, 0 = never."""
        if self._guidance_every <= 0:
            return False
        return self._scene_turns.get(channel_id, 0) % self._guidance_every == 0

    def _psyker_block(self, state: WorldState) -> str:
        """A compact German block listing each psyker's known powers, Psi-Meisterschaft value, Warp
        Threshold and current Warp Charge — so the DM knows what can be manifested and how close the
        psyker is to Perils (ADR 022). Empty if the profile has no psyker rules or nobody is a psyker.
        Powers are static (the sheet); Warp Charge is the live value from the world state."""
        if self._profile is None or not self._profile.psyker_enabled() or self._characters is None:
            return ""
        lines: list[str] = []
        for char in self._characters.characters():
            if not char.psyker:
                continue
            psi = self._characters.skill_value(char, self._profile.psyker_test_skill())
            wil = self._characters.skill_value(char, self._profile.threshold_characteristic())
            threshold = self._profile.warp_threshold(wil)
            combatant = state.find(char.name)
            warp = combatant.warp_charge if combatant is not None else 0
            stats = [f"Psi-Meisterschaft {psi}" if psi is not None else "Psi-Meisterschaft ?",
                     f"Warp-Schwelle {threshold}", f"aktuell Warp {warp}"]
            powers = ", ".join(char.known_powers) if char.known_powers else "—"
            lines.append(f"{char.name} ({', '.join(stats)}): {powers}")
        if not lines:
            return ""
        return (
            "## Psioniker (psychische Kräfte — wirke sie per `<<MANIFEST Kraft für Name>>`)\n"
            + "\n".join(lines)
        )

    def _augmetic_block(self) -> str:
        """A compact German block listing each character's augmetics + a short effect, so the DM
        narrates with them in mind (ADR 023). Augmetics are passive: the engine already applies
        their armour + characteristic bonuses to rolls; the listed effects remind the DM of the
        situational ones (Auspex, Mechadendrites, …). Static (from the sheet) — empty if the profile
        has no augmetics rules or nobody has an implant."""
        if self._profile is None or not self._profile.augmetics_enabled() or self._characters is None:
            return ""
        lines: list[str] = []
        for char in self._characters.characters():
            if not char.augmetics:
                continue
            parts: list[str] = []
            for name in char.augmetics:
                stats = self._profile.augmetic(name)
                text = (stats or {}).get("text", "")
                parts.append(f"{name} — {text}" if text else name)
            lines.append(f"{char.name}: " + "; ".join(parts))
        if not lines:
            return ""
        return (
            "## Augmetik/Implantate (dauerhaft, kein Wurf — Rüstung/Merkmals-Boni rechnet die "
            "Engine bereits dazu; situative Effekte erzählst du)\n" + "\n".join(lines)
        )
