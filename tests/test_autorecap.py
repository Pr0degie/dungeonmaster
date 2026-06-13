"""Rolling auto-recap / context handoff (D56).

When a turn's prompt nears the num_ctx cap, Ollama silently truncates the prompt HEAD — the
persona + adventure summary — which broke the DM mid-session in the first live game. The fix is to
compact the running history into a *cumulative* recap (folding in the prior recap so nothing is
lost), persist it like ``!wrap up``, and clear the in-memory history so the next prompt is
persona + adventure + recap + state + empty history — safely under budget.

These tests pin the pure/decidable parts: the cumulative-recap builder folds the prior recap in,
the trigger predicate fires above threshold, and the cog's compaction empties the channel history
while persisting the new recap (state.json + recap.md + the brain's injected recap). The LLM and
the heavy cog __init__ are faked — Ollama prose quality and live audio are the manual gates.
"""

from __future__ import annotations

import asyncio

from dmbot.memory.recap import build_recap_user
from dmbot.memory.state import WorldState
from dmbot.orchestrator import DMBrain
from dmbot.runtime import _TurnTiming
from dmbot.voice.dmcog import DMCog


# ---- the cumulative recap builder (recap.py) -----------------------------------------------

def test_build_recap_user_folds_in_the_prior_recap() -> None:
    history = [
        {"role": "user", "content": "Timo: Wir steigen tiefer."},
        {"role": "assistant", "content": "Der Schacht endet in einer Halle."},
    ]
    out = build_recap_user(history, prior_recap="Die Gruppe betrat die Unterstadt.")
    # The earlier recap is carried in as the lead-in, and the fresh transcript follows it.
    assert "Die Gruppe betrat die Unterstadt." in out
    assert "Der Schacht endet in einer Halle." in out
    # And the instruction makes the new recap supersede-and-extend (nothing lost).
    assert "verloren" in out.lower()


def test_build_recap_user_without_prior_is_the_plain_form() -> None:
    history = [{"role": "assistant", "content": "Etwas geschah."}]
    out = build_recap_user(history)  # the plain !wrap up path
    assert "Etwas geschah." in out
    assert "Bisherige Zusammenfassung" not in out  # no cumulative lead-in


# ---- the trigger predicate (already covered in test_context_budget, pinned here too) -------

def test_ctx_over_budget_is_the_compaction_trigger() -> None:
    # 0.85 * 1000 = 850 → 900 trips it (compact), 800 doesn't.
    assert _TurnTiming(turn=1, trigger=0.0, prompt_eval=900, num_ctx=1000).ctx_over_budget()
    assert not _TurnTiming(turn=2, trigger=0.0, prompt_eval=800, num_ctx=1000).ctx_over_budget()


# ---- the orchestrator's compaction primitives ----------------------------------------------

class _CapClient:
    """Returns a canned recap; never hits Ollama."""

    def __init__(self, answer: str = "Eine aktualisierte Zusammenfassung.") -> None:
        self.answer = answer

    async def chat(self, system, messages, options=None, format=None) -> str:
        return self.answer

    async def aclose(self) -> None:
        pass


def test_summarize_passes_prior_recap_through_to_the_builder() -> None:
    # Capture the user message so we can prove the prior recap reached the summariser prompt.
    captured: dict = {}

    class _Cap(_CapClient):
        async def chat(self, system, messages, options=None, format=None) -> str:
            captured["user"] = messages[-1]["content"] if messages else None
            return await super().chat(system, messages, options=options, format=format)

    brain = DMBrain(_Cap())
    ch = 1
    brain.add_player_line(ch, "Timo", "Wir gehen weiter.")
    asyncio.run(brain.respond(ch))  # populate history
    recap = asyncio.run(brain.summarize(ch, prior_recap="FRÜHERER_RECAP_SENTINEL"))
    assert recap == "Eine aktualisierte Zusammenfassung."
    assert "FRÜHERER_RECAP_SENTINEL" in captured["user"]


def test_clear_history_empties_history_but_keeps_recap_and_buffer() -> None:
    brain = DMBrain(_CapClient())
    ch = 2
    brain.set_context(ch, recap="Bleibt erhalten.")
    brain.add_player_line(ch, "Timo", "Eine Zeile.")  # in the buffer, not yet a turn
    asyncio.run(brain.respond(ch))  # makes one history turn (consumes the buffered line)
    brain.add_player_line(ch, "Timo", "Noch eine.")  # a fresh buffered line, must survive
    assert brain.history_len(ch) > 0
    brain.clear_history(ch)
    assert brain.history_len(ch) == 0           # the rolling history is gone
    assert brain.current_recap(ch) == "Bleibt erhalten."  # the recap is kept
    assert brain.pending_count(ch) == 1         # the buffer is untouched (not a fresh session)


# ---- the cog's compaction flow (off the hot path) ------------------------------------------

class _StubRuntime:
    """A minimal stand-in for SessionRuntime carrying only the shared state the auto-recap path
    touches. The cog split (ADR 029) moved these off the cog onto the runtime, so the bare cog now
    holds a stub runtime instead of flat attributes. ``_state_path`` / ``_persist_and_refresh`` are
    monkeypatched per-test (as before), now on the runtime."""

    def __init__(self, brain: DMBrain, *, autorecap: bool = True) -> None:
        self._brain = brain
        self._autorecap = autorecap
        self._compacting: set[int] = set()
        self._active_vc_id = None
        self._state: dict = {}
        self._text_channel = None  # no Discord note in the test

    def _brain_channel(self, channel) -> int:
        return self._active_vc_id if self._active_vc_id is not None else channel.id

    # These exist so the persistence test can monkeypatch them (as it did on the cog before the
    # split); they're always replaced before use (only _persist_recap reaches them, and the only
    # test that gets there patches both with a tmp_path body).
    def _state_path(self, channel_id):  # pragma: no cover - always monkeypatched
        raise NotImplementedError

    def _persist_and_refresh(self, channel):  # pragma: no cover - always monkeypatched
        raise NotImplementedError


def _bare_cog(brain: DMBrain, *, autorecap: bool = True) -> DMCog:
    """A DMCog without the heavy cog/runtime __init__ (no TTS thread / transcriber / profile load):
    a stub runtime wired with only the attributes _maybe_compact / _persist_recap touch.
    _persist_and_refresh is given a minimal real body (save + inject the recap) so the test
    exercises real persistence + injection."""
    cog = object.__new__(DMCog)
    cog._rt = _StubRuntime(brain, autorecap=autorecap)
    return cog


def test_maybe_compact_persists_recap_and_empties_history(tmp_path, monkeypatch) -> None:
    brain = DMBrain(_CapClient(answer="Neue, kumulative Zusammenfassung."))
    cog = _bare_cog(brain)

    class _Chan:
        id = 99

    cid = _Chan.id
    state = WorldState(session_id=str(cid), recap="Alter Recap.")
    cog._rt._state[cid] = state

    # Point the state path at tmp and give _persist_and_refresh a minimal real body (the production
    # one pulls in the profile/adventure machinery we don't need here): save + re-inject the recap,
    # exactly the parts the auto-recap relies on.
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(cog._rt, "_state_path", lambda c: state_path)

    def _refresh(channel) -> None:
        st = cog._rt._state[cog._rt._brain_channel(channel)]
        st.save(cog._rt._state_path(cog._rt._brain_channel(channel)))
        brain.set_context(cog._rt._brain_channel(channel), recap=st.recap)

    monkeypatch.setattr(cog._rt, "_persist_and_refresh", _refresh)

    # Seed a real history turn so there's something to compact, and inject the prior recap like join.
    brain.set_context(cid, recap="Alter Recap.")
    brain.add_player_line(cid, "Timo", "Wir kämpfen.")
    asyncio.run(brain.respond(cid))
    assert brain.history_len(cid) > 0

    timing = _TurnTiming(turn=1, trigger=0.0, prompt_eval=900, num_ctx=1000)  # over budget → compact
    asyncio.run(cog._maybe_compact(_Chan(), timing))

    # History is cleared; the new cumulative recap is set in the brain, the state, and recap.md.
    assert brain.history_len(cid) == 0
    assert brain.current_recap(cid) == "Neue, kumulative Zusammenfassung."
    assert state.recap == "Neue, kumulative Zusammenfassung."
    assert state_path.is_file()
    recap_md = tmp_path / "recap.md"
    assert recap_md.is_file()
    assert "Neue, kumulative Zusammenfassung." in recap_md.read_text(encoding="utf-8")
    assert cog._rt._compacting == set()  # the in-progress guard was released


def test_maybe_compact_noop_below_threshold() -> None:
    brain = DMBrain(_CapClient())
    cog = _bare_cog(brain)

    class _Chan:
        id = 7

    cog._rt._state[_Chan.id] = WorldState(session_id="7")
    brain.add_player_line(_Chan.id, "Timo", "Hallo.")
    asyncio.run(brain.respond(_Chan.id))
    before = brain.history_len(_Chan.id)
    timing = _TurnTiming(turn=1, trigger=0.0, prompt_eval=100, num_ctx=1000)  # under budget
    asyncio.run(cog._maybe_compact(_Chan(), timing))
    assert brain.history_len(_Chan.id) == before  # untouched — no compaction


def test_maybe_compact_disabled_by_flag() -> None:
    brain = DMBrain(_CapClient())
    cog = _bare_cog(brain, autorecap=False)  # DM_AUTORECAP=0

    class _Chan:
        id = 8

    cog._rt._state[_Chan.id] = WorldState(session_id="8")
    brain.add_player_line(_Chan.id, "Timo", "Hallo.")
    asyncio.run(brain.respond(_Chan.id))
    before = brain.history_len(_Chan.id)
    timing = _TurnTiming(turn=1, trigger=0.0, prompt_eval=999, num_ctx=1000)  # would trip, but off
    asyncio.run(cog._maybe_compact(_Chan(), timing))
    assert brain.history_len(_Chan.id) == before  # flag off → never compacts


def test_maybe_compact_guards_against_double_trigger() -> None:
    brain = DMBrain(_CapClient())
    cog = _bare_cog(brain)

    class _Chan:
        id = 9

    cog._rt._state[_Chan.id] = WorldState(session_id="9")
    brain.add_player_line(_Chan.id, "Timo", "Hallo.")
    asyncio.run(brain.respond(_Chan.id))
    before = brain.history_len(_Chan.id)
    cog._rt._compacting.add(_Chan.id)  # a compaction already in flight for this channel
    timing = _TurnTiming(turn=1, trigger=0.0, prompt_eval=999, num_ctx=1000)
    asyncio.run(cog._maybe_compact(_Chan(), timing))
    assert brain.history_len(_Chan.id) == before  # the guard blocked the second compaction


# ---- !wrap up must stay cumulative once the auto-recap can clear history ------------------

def test_wrapup_folds_in_the_current_recap() -> None:
    """`!wrap up` must fold the recap already in the prompt into the new one. Once the rolling
    auto-recap can clear the running history mid-session, summarising the visible history alone
    would overwrite the stored recap and lose the earlier part — this guards that regression."""
    captured: dict = {}

    class _Cap(_CapClient):
        async def chat(self, system, messages, options=None, format=None) -> str:
            captured["user"] = messages[-1]["content"] if messages else None
            return await super().chat(system, messages, options=options, format=format)

    brain = DMBrain(_Cap(answer="Kumulativer Recap."))
    cog = _bare_cog(brain)
    cog._persist_recap = lambda *a, **k: None  # bypass state.json/recap.md — not under test here

    class _Chan:
        id = 55

    cid = _Chan.id
    brain.set_context(cid, recap="FRÜHERER_RECAP_SENTINEL")  # the recap currently in the prompt
    brain.add_player_line(cid, "Timo", "Wir kämpfen weiter.")
    asyncio.run(brain.respond(cid))  # a fresh turn to summarise

    class _Ctx:
        channel = _Chan()

        async def send(self, _msg) -> None:
            pass

    asyncio.run(DMCog.wrap.callback(cog, _Ctx()))

    # The prior recap reached the summariser prompt → the wrap-up is cumulative, not plain.
    assert captured["user"] is not None and "FRÜHERER_RECAP_SENTINEL" in captured["user"]
