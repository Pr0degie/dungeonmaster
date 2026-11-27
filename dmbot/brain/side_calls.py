"""Every model call of :class:`~dmbot.orchestrator.DMBrain` that is not a narrated turn: the
roll router (ADR 014), the three post-turn classifiers — scene move (ADR 057), commitment
(ADR 058), present NPCs (ADR 062) —, the recap (``!wrap up`` and the auto-compaction, D57) and
the rules answer (``!rules``).

A mixin (ADR 065): its methods are methods of the one ``DMBrain`` object — ``self`` is the
brain, all state is created in ``DMBrain.__init__`` and kept per channel in a
``ChannelSession``.

``_log_classifier`` (the ``[classifier]`` line) stays in orchestrator.py:
``test_classifier_latency`` captures that line on the logger ``dmbot.orchestrator``. The
classifiers here call it through ``self``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict

from ..llm.fact_router import FactVerdict, classify_commitment
from ..llm.npc_router import NpcVerdict, classify_present_npcs
from ..llm.roll_router import classifier_schema, classifier_system, to_test_request
from ..llm.sanitize import _ROLE_LABEL
from ..llm.scene_router import SceneVerdict, classify_scene_move
from ..memory.recap import RECAP_MAX_CHARS, RECAP_NUM_PREDICT, RECAP_SYSTEM_DE, build_recap_user
from ..rules.marker import TestRequest

log = logging.getLogger(__name__)


class SideCallsMixin:
    """The stateless side calls: classifiers, recap, rules answer. Mixed into ``DMBrain``; holds
    no state of its own."""

    async def classify_test(
        self, *, action: str, character: str | None, skills: list[str]
    ) -> TestRequest | None:
        """Roll-detection router (ADR 014): a separate, stateless, constrained-JSON LLM call that
        decides whether ``action`` needs a test and which skill/difficulty — instead of trusting the
        narration model's inline marker. ``skills`` constrains the choice to the acting character's
        sheet. Returns a TestRequest (target_name = ``character``) or None. Never raises."""
        self.last_router = None  # replay capture (ADR 046): reset; set only on a clean verdict
        if self._profile is None or not action.strip():
            return None
        difficulties = list(self._profile.difficulty_ladder)
        schema = classifier_schema(skills, difficulties)
        system = classifier_system(
            skills, difficulties, self._profile.display_name or self._profile.name
        )
        started = time.monotonic()
        try:
            raw = await self._client.chat(
                system,
                [{"role": "user", "content": f"Spieler-Handlung: {action}"}],
                # Anti-repetition OFF for the constrained verdict (overrides the client's narration
                # default, B1): the classifier_system prompt lists every skill + difficulty in the
                # repeat_last_n window, so a repeat_penalty would penalise the very enum value the
                # router must pick — corrupting a deterministic, reliability-critical path (golden
                # rule #2 / ADR 014). Per-call options win over the instance default.
                options={"temperature": 0, "num_predict": 80, "repeat_penalty": 1.0, "repeat_last_n": 0},
                format=schema,
            )
            data = json.loads(raw)
        except Exception:
            log.exception("roll-router classification failed")
            self._log_classifier("roll", started, "failed")
            return None
        req = to_test_request(data, character=character)
        self._log_classifier(
            "roll", started,
            f"{req.skill} ({req.difficulty or 'Standard'})" if req is not None else "no test",
        )
        self.last_router = {"raw": raw, "decision": asdict(req) if req is not None else None}
        return req

    async def classify_scene_move(
        self, *, turn_text: str, exits, current_title: str = "", context: str = ""
    ) -> SceneVerdict:
        """Scene-move classifier (ADR 057 #1) — the same shape as :meth:`classify_test`: a
        separate, stateless, constrained-JSON call whose answer space is exactly the current
        scene's reachable exits plus "nein". The brain only lends its client and records the
        verdict for the replay journal; validation and the pointer write live outside
        (``llm/scene_router.py`` and ``rules/scene_flow.py``). Never raises."""
        started = time.monotonic()
        verdict = await classify_scene_move(
            self._client.chat, turn_text=turn_text, exits=exits, current_title=current_title,
            context=context,
        )
        self._log_classifier("scene", started, self._scene_outcome(verdict))
        self._note_scene(verdict)
        return verdict

    @staticmethod
    def _scene_outcome(verdict: SceneVerdict) -> str:
        return verdict.failure.value if verdict.failure else (verdict.target_id or "stay")

    @staticmethod
    def _fact_outcome(verdict: FactVerdict) -> str:
        return (verdict.failure.value if verdict.failure
                else (verdict.commitment.kind if verdict.commitment is not None else "none"))

    @staticmethod
    def _npc_outcome(verdict: NpcVerdict) -> str:
        return (verdict.failure.value if verdict.failure
                else (", ".join(s.label for s in verdict.sightings) or "none"))

    def _note_scene(self, verdict: SceneVerdict) -> None:
        self.last_scene_router = {
            "raw": verdict.raw,
            "verdict": verdict.target_id,
            "failure": verdict.failure.value if verdict.failure else None,
        }

    def _note_fact(self, verdict: FactVerdict) -> None:
        self.last_facts = {
            "raw": verdict.raw,
            "verdict": asdict(verdict.commitment) if verdict.commitment is not None else None,
            "failure": verdict.failure.value if verdict.failure else None,
        }

    def _note_npc(self, verdict: NpcVerdict) -> None:
        self.last_npcs = {
            "raw": verdict.raw,
            "verdict": [asdict(s) for s in verdict.sightings],
            "failure": verdict.failure.value if verdict.failure else None,
        }

    async def classify_commitment(
        self, *, answer_text: str, recipients=(), givers=()
    ) -> FactVerdict:
        """Fact classifier (ADR 058 #1) — the second post-turn call, run on the same turn
        boundary as :meth:`classify_scene_move` so the two share one latency window. Reports what
        the narration committed to; the world-state write is the caller's, through
        ``WorldState.record_commitment``. Never raises."""
        started = time.monotonic()
        verdict = await classify_commitment(
            self._client.chat, answer_text=answer_text, recipients=recipients, givers=givers
        )
        self._log_classifier("fact", started, self._fact_outcome(verdict))
        self._note_fact(verdict)
        return verdict

    async def classify_present_npcs(
        self, *, answer_text: str, party=(), roster=(), present=(), candidates=()
    ) -> NpcVerdict:
        """Presence classifier (ADR 062) — the third post-turn call on the same boundary. Reports
        who newly appears in person; registering them is the caller's. Never raises."""
        started = time.monotonic()
        verdict = await classify_present_npcs(
            self._client.chat, answer_text=answer_text, party=party, roster=roster,
            present=present, candidates=candidates,
        )
        self._log_classifier("npcs", started, self._npc_outcome(verdict))
        self._note_npc(verdict)
        return verdict

    async def summarize(self, channel_id: int, *, prior_recap: str = "") -> str | None:
        """Produce a German "Was bisher geschah" recap from this channel's history (the `wrap up`
        trigger, D14). Code stores the returned string in the world state; this only generates it.
        ``None`` if there's no history to summarise.

        ``prior_recap`` folds an earlier recap into the transcript so the new recap is **cumulative**:
        when the running history is cleared, the older recap still covers what scrolled out of it, and
        the new recap supersedes-and-extends it. Both the rolling auto-compaction (D57) AND ``!wrap up``
        pass the current recap so neither loses the part an earlier (auto-)recap already folded away;
        "" gives a plain summary of the visible history (e.g. a session's very first recap)."""
        session = self._session(channel_id)
        history = session.history
        if not history:
            return None
        # The messages this recap folds in, as objects, taken with the transcript *before* the await:
        # a turn, redo or cap trim during the await changes the live list, not this snapshot.
        consumed = list(history)
        user = build_recap_user(history, prior_recap)
        cap = self._recap_num_predict() if self._recap_num_predict is not None else None
        raw = await self._client.chat(
            RECAP_SYSTEM_DE,
            [{"role": "user", "content": user}],
            options={"temperature": 0.3, "num_predict": cap or RECAP_NUM_PREDICT},
        )
        # Light cleanup only (no marker/test stripping — a recap has none): drop markdown + a leading
        # role label the model might prepend.
        text = _ROLE_LABEL.sub("", raw.replace("*", "").strip()).strip()
        if len(text) > RECAP_MAX_CHARS * 1.5:
            # The length is only prompted — code cannot shorten a recap without losing facts. Say
            # so, because a recap that keeps growing ends at the output cap again.
            log.warning("recap is %d characters, the prompt asks for at most %d — it is kept as it is",
                        len(text), RECAP_MAX_CHARS)
        # Recorded only now, after the await: the compaction calls clear_history right after this
        # returns, with no await in between, so a concurrent summarize (``!wrap up``) that finished
        # earlier can't widen what it deletes. An empty recap records nothing.
        session.compact_consumed = consumed if text else None
        return text or None

    async def answer_rules(self, question: str, context: str, *, system_name: str) -> str | None:
        """Answer a player's rules question (``!rules <frage>``) in German, grounded ONLY in the
        retrieved rulebook excerpts ``context``. The rulebook is English layout-soup, so the model
        translates + condenses it — but must not invent rules (golden rule #7): if the excerpts
        don't cover it, it says so. Stateless (no channel history). ``None`` on an empty reply."""
        system = (
            f"Du bist ein Regel-Assistent für das Tabletop-Rollenspiel {system_name}. Beantworte "
            "die Regelfrage des Spielers kurz, klar und auf Deutsch — ausschließlich auf Grundlage "
            "der folgenden Auszüge aus dem (englischen) Regelbuch. Übersetze sinngemäß. Erfinde "
            "keine Regeln und keine Zahlen: Deckt der Text die Frage nicht ab, sag offen, dass das "
            "Regelbuch hier dazu nichts hergibt. Höchstens etwa fünf Sätze."
        )
        user = f"Regelbuch-Auszüge:\n{context}\n\nRegelfrage: {question}"
        raw = await self._client.chat(
            system,
            [{"role": "user", "content": user}],
            options={"temperature": 0.2, "num_predict": 320},
        )
        text = raw.replace("*", "").strip()
        return _ROLE_LABEL.sub("", text).strip() or None
