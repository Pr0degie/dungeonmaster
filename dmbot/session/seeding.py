"""Session seeding for :class:`~dmbot.runtime.SessionRuntime`: what ``!join`` sets up — the
channel's characters and world state, the adventure's start state, the turn order, the speaker
identities and the restored conversation history.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..memory import history as history_store

log = logging.getLogger(__name__)


class SeedingMixin:
    """The ``!join`` setup. Mixed into ``SessionRuntime``; holds no state of its own."""

    def _build_turn_order(self, voice_channel) -> list[str]:
        """Seed the turn order from a voice channel's human members (Bot A + bots filtered),
        preferring each player's character name via the alias map (open item F)."""
        names: list[str] = []
        for m in voice_channel.members:
            if m.bot or (self._bot_a_user_id and m.id == self._bot_a_user_id):
                continue
            char = self._characters.get(m.display_name) if self._characters else None
            names.append(char.name if char else m.display_name)
        return names

    def _seed_adventure_state(self, state) -> None:
        """Seed what the adventure ships into a fresh world state: start time, deadlines and
        consequence clocks (ADR 059 #1), the scene's NPCs as present (PRD block 3) and the
        campaign objective as the mission quest (ADR 058 #3).

        All three are idempotent — ``seed_time_from_adventure`` latches ``time_seeded``,
        ``set_mission`` replaces rather than appends and NPC registration keeps existing values —
        so a re-join or a restart mid-session neither resets the clock nor duplicates a deadline."""
        adv = self._adventure
        if adv is None:
            return
        start_time = adv.start_time_de
        deadlines = adv.deadlines
        # DM_CLOCKS=0: the adventure's clocks are not created at all (start time and deadlines are).
        clocks = adv.clocks if self.clocks_enabled else []
        if start_time or deadlines or clocks:
            state.seed_time_from_adventure(start_time=start_time or None, deadlines=deadlines,
                                           clocks=clocks)
        mission = adv.mission
        title = str(mission.get("title_de", "") or "").strip()
        if title:
            state.set_mission(title,
                              detail=str(mission.get("detail_de", "") or ""),
                              given_by=str(mission.get("given_by", "") or ""))
        if state.scene_id:
            self._register_scene_npcs(state, adv.get_scene(state.scene_id))

    def seed_session(self, voice_channel, text_channel) -> bool:
        """Seed all per-session state for a fresh !join in the right order: active + text
        channel, party (+ alias/speaker hints), turn order from the voice members, world
        state (seeded from the sheet on first join, else loaded), the start-scene pointer for
        a fresh state (a loaded state keeps its stored pointer), persist+refresh, and the D41
        crash-recovery history restore. Returns the example-party fallback flag."""
        cid = voice_channel.id
        self._active_vc_id = cid  # buffer transcripts + answer for this channel
        self._text_channel = text_channel  # where the pause panel (and other panels) are posted
        self._voice_channel = voice_channel  # live member list for the kick phrase (_maybe_kick)
        # The STT thread posts player lines through this loop (_echo_player_line).
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:  # seeded outside a loop (tests) — no echo
            self._loop = None
        # Phase 8: load this channel's party (else the example), wire the "who plays whom" alias
        # hint into the prompt (open item F), and seed the turn order from the voice members.
        self._characters, char_fallback = self._load_characters(cid)
        # Identity (PRD "Identity"): who is who, by Discord user id, before anything is buffered.
        self._seed_speaker_identities(voice_channel)
        # With the resolution real, the prompt no longer carries the display-name → character
        # mapping the model had to apply itself — every player line already arrives under its
        # character name. The party boundary half of the hint stays either way.
        self._brain.set_alias_hint(
            cid, self._characters.alias_hint_de(with_mapping=not self._char_by_user)
        )
        # All table names → cut-labels/stop sequences, so a puppeted "Seskin: …" script is truncated.
        self._brain.set_known_speakers(cid, self._characters.speaker_labels())
        self._turn_order[cid] = self._build_turn_order(voice_channel)
        self._turn_index[cid] = 0
        # Memory (Phase 9): load this channel's world state (or seed it from the sheet on first join),
        # then inject the stored recap + current state into the prompt so the DM picks up where it
        # left off — the "next session opens with a correct recap" half of the gate.
        self._state[cid] = self._load_or_seed_state(cid)
        # Fate (ADR 063, IM p.220): a !join starts a session — unset totals come from the profile,
        # Fate spent last time is recovered.
        profile = self._profile
        if profile is not None and profile.fate_enabled():
            self._state[cid].start_fate_session(default=profile.fate_start())
        # Adventure (Phase 10a): point a fresh session at the start scene; a loaded state keeps
        # its stored pointer (the plot position survives restarts like HP does) — unless that
        # pointer names a scene the loaded adventure doesn't have (a previous campaign's): every
        # get_scene() would return None, so no scene card and no 🧪 overlay all evening. A foreign
        # pointer re-seeds to the start scene, loudly (ADR 056 #4).
        if self._adventure is not None:
            stored = self._state[cid].scene_id
            if stored and self._adventure.get_scene(stored) is None:
                log.warning("scene pointer %r is unknown to adventure %r — re-seeding to the start "
                            "scene %r (stale pointer from another campaign?)",
                            stored, self._adventure.id, self._adventure.start_scene)
                self._state[cid].scene_id = ""
            if not self._state[cid].scene_id:
                self._state[cid].scene_id = self._adventure.start_scene
            # The campaign's own clock and its objective (ADR 059 #1 / ADR 058 #3), seeded from
            # the adventure file instead of typed at the table. Both are idempotent — a resumed
            # session keeps its time and its mission — so this may run on every !join.
            self._seed_adventure_state(self._state[cid])
        self._scene_turns[cid] = 0
        self._persist_and_refresh(voice_channel)
        # Crash recovery (D41): restore the conversation thread from the autosave if the in-memory
        # history is empty (a fresh process after a crash). A clean !leave rotates the file away, so
        # this only fires when the previous session didn't shut down cleanly.
        if self._autosave:
            try:
                turns = history_store.load_recent(
                    self._history_path(cid), self._brain.max_history_turns
                )
            except OSError:
                log.exception("could not read the history autosave for channel %s", cid)
                turns = []
            restored = self._brain.restore_history(cid, turns)
            if restored:
                log.info("restored %d conversation turns from the autosave (!redo unavailable for the last)", restored)
        # NPC memory (ADR 044): don't re-mine restored/pre-join history — extraction starts at
        # the join point (the previous session's tail was covered by its own wrap-up/scene exits).
        self._npc_mem_marks[cid] = self._brain.history_len(cid)
        # Replay journal header (ADR 046): the session context dm-eval needs to rebuild the
        # pipeline (profile, adventure, scene mode). One line per !join; load_recent skips it.
        if self._autosave:
            profile = self._profile
            adventure = self._adventure
            try:
                history_store.append_event(self._history_path(cid), {
                    "kind": "session",
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "profile": profile.name if profile else "",
                    "adventure": adventure.id if adventure else "",
                    "scene_mode": self._scene_mode,
                })
            except OSError:
                log.exception("could not write the session header for channel %s", cid)
            # Scene journal event (ADR 053): open every session's journal with the current scene
            # — the fresh start-scene seed above or a restored pointer — so the first chunk of a
            # session has a scene even before the first transition.
            if self._state[cid].scene_id:
                self._journal_scene_event(self._state[cid])
        return char_fallback
