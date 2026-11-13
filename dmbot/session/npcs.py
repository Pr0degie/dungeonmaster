"""NPC memory (ADR 044) for :class:`~dmbot.runtime.SessionRuntime`: which NPCs a scene holds,
and the extraction — at scene exit and wrap-up — of what they would remember.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..memory import chekhov as chekhov_mod
from ..memory import npc_memory as npc_memory_mod
from ..memory.gametime import render_time_de
from ..memory.state import Combatant, WorldState

log = logging.getLogger(__name__)


class NpcMemoryMixin:
    """Scene NPCs and their memories. Mixed into ``SessionRuntime``; holds no state of its own."""

    # ----- NPC memory (ADR 044) -------------------------------------------------------------

    def _scene_npcs(self, state: WorldState, scene_id: str | None = None) -> list[Combatant]:
        """The *living, registered* NPCs of a scene (default: the current one) — whose memories
        ride in the prompt. With an adventure loaded the card's ``npcs_here`` filters the
        registered list (case-insensitive, like ``WorldState.find``); without one, every living
        registered NPC counts (there is no scene notion to scope by)."""
        living = [n for n in state.npcs if n.wounds > 0]
        if self._adventure is None:
            return living
        sid = scene_id if scene_id is not None else state.scene_id
        scene = self._adventure.get_scene(sid)
        if scene is None:
            return living
        # The card's NPCs plus the ones seen here in person (ADR 062) — one definition of "here"
        # for the prompt, the NPC-memory block and the attack target picker.
        return state.present_npcs(sid, scene.npcs_here)

    def schedule_npc_memory_extraction(self, channel, scene_id: str) -> None:
        """Fire-and-forget NPC-memory extraction for the scene just left (ADR 044) — called by
        the scene-change seams (!ort, the confirmed <<ORT>> move) right after the pointer moved.
        Off the hot path by design: the scene change never waits for the LLM."""
        if not self._npc_memory:
            return
        try:
            asyncio.get_running_loop().create_task(
                self.extract_npc_memories(channel, scene_id)
            )
        except RuntimeError:  # no running loop (sync/test context) — extraction is best-effort
            log.debug("NPC-memory: no running event loop — extraction skipped")

    async def extract_npc_memories(self, channel, scene_id: str, *, include_chekhov: bool = False) -> int:
        """Mine the history since the last extraction for what ``scene_id``'s NPCs would remember
        and apply it (memories + clamped attitude drift + lie flips + faction gossip — all hard
        effects in code, golden rule #3). Best-effort end to end: any failure logs and returns 0,
        never blocks the caller. Returns the number of new direct memories.

        ``include_chekhov`` (the ``!wrap`` call, ADR 050): the same call additionally maintains
        the Chekhov list — its input gains the open threads + the session history *before* the
        scene window (threads are session-granularity; the window alone only covers the last
        scene), and the ``chekhov`` output section is applied code-side (cap/dedupe/status)."""
        if not self._npc_memory:
            return 0
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or cid in self._npc_mem_running:
            if cid in self._npc_mem_running:
                log.info("NPC-memory: extraction already running for channel %s — skipped", cid)
            return 0
        mark = min(self._npc_mem_marks.get(cid, 0), self._brain.history_len(cid))
        turns = self._brain.history_messages(cid, mark)
        chekhov_section = ""
        if include_chekhov:
            earlier = self._brain.history_messages(cid, 0)[:mark]
            if turns or earlier:  # anything at all this session the thread pass could mine
                chekhov_section = chekhov_mod.build_chekhov_section(
                    self.chekhov_list(cid).open_threads(), earlier
                )
        # Candidates: every living registered NPC (incl. off-card !npc add spawns of this scene)
        # plus the departed scene card's npcs_here — the latter may be unregistered talk-only
        # NPCs; a dummy carrier lets the extractor name them, apply registers on first memory.
        # The extractor prompt binds memories to what actually happened in the transcript.
        candidates = [n for n in state.npcs if n.wounds > 0]
        known = {n.name.lower() for n in candidates}
        if self._adventure is not None:
            scene = self._adventure.get_scene(scene_id)
            for name in scene.npcs_here if scene else []:
                if name.strip().lower() not in known:
                    candidates.append(Combatant(name=name.strip(), wounds=1, max_wounds=1, is_npc=True))
        if (not turns or not candidates) and not chekhov_section:
            self._npc_mem_marks[cid] = mark + len(turns)
            return 0
        self._npc_mem_running.add(cid)
        try:
            now_ingame = render_time_de(state.time_minutes)
            payload = await npc_memory_mod.request_extraction(
                self._brain.client, turns=turns, npcs=candidates, scene_id=scene_id,
                now_ingame=now_ingame, chekhov_section=chekhov_section,
            )
            # The window is consumed even when extraction failed (skip, don't re-mine it against
            # a different scene later); the gist-dedup in apply covers the overlap cases.
            self._npc_mem_marks[cid] = mark + len(turns)
            if payload is None:
                return 0
            new_entries = npc_memory_mod.apply_extraction(
                state, payload, scene_id=scene_id,
                now=datetime.now().isoformat(timespec="seconds"),
                now_ingame=now_ingame,
                statblock=self._adventure.npc if self._adventure is not None else None,
            )
            npc_memory_mod.propagate_gossip(state, new_entries)
            if chekhov_section:
                n_new, n_resolved = chekhov_mod.apply_chekhov(
                    self.chekhov_list(cid), payload.get("chekhov"),
                    origin_scene=scene_id,
                    created_session=datetime.now().date().isoformat(),
                )
                if n_new or n_resolved:
                    self.save_chekhov(cid)
                    log.info("🧵 Chekhov-Liste: %d neue Fäden, %d aufgelöst", n_new, n_resolved)
            self._persist_and_refresh(channel)
            log.info("🧠 NPC-Gedächtnis: %d neue Erinnerungen (Szene '%s')", len(new_entries), scene_id or "—")
            return len(new_entries)
        except Exception:
            log.exception("NPC-memory extraction failed for scene '%s' — skipped", scene_id)
            return 0
        finally:
            self._npc_mem_running.discard(cid)
