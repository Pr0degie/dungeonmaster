"""The per-channel and per-turn records of :class:`~dmbot.orchestrator.DMBrain`: what the
brain keeps for one voice channel (:class:`ChannelSession`), a turn's input (:class:`_Turn`) and
its answer for the table (:class:`TurnAnswer`), and the two carriers of the generation path
(:class:`_Sink`, :class:`_Attempt`).

Plain records. ``dmbot.orchestrator`` re-exports every name (ADR 034), so importers keep using
it; the mixins under ``dmbot/brain/`` import from here, because importing these names from
``orchestrator`` would be a cycle.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

from ..rules.marker import MARKER_SPECS, empty_markers


class TurnAnswer(str):
    """A DM turn's answer for the table that also carries the player line it answered
    (``user_msg``). The delivery pipeline journals the pair from this — never from the mutable
    ``last_turn``, which the next turn or a compaction can change before the autosave runs."""

    user_msg: str

    def __new__(cls, answer: str, user_msg: str) -> "TurnAnswer":
        obj = super().__new__(cls, answer)
        obj.user_msg = user_msg
        return obj


def turn_user_msg(answer: object) -> str | None:
    """The player line a turn's answer carries (:class:`TurnAnswer`), or None."""
    return getattr(answer, "user_msg", None)


@dataclass(eq=False)
class _Turn:
    """A turn's input, kept so ``!redo`` can re-generate it, plus the user message it stored in
    history (``stored``). Identity, not content, says whether that pair is still there: two
    identical player lines in a row are two different objects."""

    user_msg: str
    labels: list[str]
    stored: dict[str, str] | None = None
    # What _prepare_turn took out of the session for this turn, so a turn the paused backend
    # could not answer can put it back (:meth:`DMBrain._hold_turn`): the lines an earlier
    # unanswered turn had left (``held``, kept under ``held_seq``), the newly drained ones
    # (``fresh``), dice results, notes. ``seq`` orders the turns of a channel as they were prepared.
    seq: int = 0
    held_seq: int | None = None
    held: list[tuple[str, str]] = field(default_factory=list)
    fresh: list[tuple[str, str]] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    aside: bool = False  # put aside by _hold_turn: its input is back in the queues


def _markers_dict(markers: dict[str, list], *, queued: bool) -> dict:
    """The turn's parsed marker requests as plain dicts for the replay journal (ADR 046).
    ``queued=False`` (a results-only turn suppressed them) records empty lists for the
    suppressible kinds — the suppression itself is behaviour the replay must reproduce.
    Non-suppressible kinds (``uhr``/``zeit``, ADR 047/048: the post-roll consequence turn is
    the canonical tick/advance moment) record what was parsed regardless. Key order is the
    registry order (ADR 051) — the journal bytes must not move."""
    return {
        spec.kind: (
            [asdict(r) for r in markers[spec.kind]] if queued or not spec.suppressible else []
        )
        for spec in MARKER_SPECS
    }


@dataclass
class ChannelSession:
    """Everything :class:`DMBrain` keeps for one voice channel. One object per channel, created
    on first touch (:meth:`DMBrain._session`) and reset in place by :meth:`DMBrain.reset`."""

    # The running conversation, user/assistant pairs, capped at ``max_history_turns``.
    history: list[dict[str, str]] = field(default_factory=list)
    # Transcribed player lines waiting for the next turn. Written from the STT thread, read on
    # the event loop — touch it only under ``DMBrain._lock``.
    buffer: list[tuple[str, str]] = field(default_factory=list)
    # The very history messages the last finished :meth:`DMBrain.summarize` folded into the
    # recap. The auto-compaction clears history right after the (awaited) summarize, and a turn,
    # a redo or a cap trim can change the live list *during* that await —
    # :meth:`DMBrain.clear_history` removes exactly these objects, so whatever the recap never
    # saw stays. Cleared once consumed; None → clear_history does a full wipe.
    compact_consumed: list[dict[str, str]] | None = None
    # The pending-marker store (ADR 051): the requests parsed from the last DM turn, one list
    # per registry kind (``tests``, ``manifests``, ``scenes``, ``erledigt``, ``uhr``, ``zeit``).
    # Drained through :meth:`DMBrain.take_pending` — by dicecog (tests/manifests) and the
    # delivery pipeline (the rest); what each consumer does is on the ``take_pending_<kind>``
    # wrappers.
    pending: dict[str, list] = field(default_factory=empty_markers)
    # Who narrated the turn that queued the pending ``<<TEST>>`` markers (the failover's
    # ``backend`` stat, None on the Ollama-only bot) — recorded when they are queued, so the
    # marker-vs-router switch (D140) judges them by their own turn and not by whatever prose call
    # finished last (a dice-result turn, another channel, an echo-guard retry).
    tests_narrator: str | None = None
    # One-shot GM directives injected into the NEXT turn's user message as "[Regie] …" lines
    # (ADR 047: "clock X is full — the consequence hits now"). Code-queued only, drained by
    # _prepare_turn like dice results, exempt from the player-line cap.
    gm_notes: list[str] = field(default_factory=list)
    # Test results fed back in (engine roll → narrate consequence): prepended to the next turn,
    # exempt from the player-line cap.
    test_results: list[str] = field(default_factory=list)
    # The player lines of the turn the paused backend did not answer (ADR 061, amendment
    # 2026-11-13 fourth), as ``(turn seq, lines)``. They lead the next turn in the order they
    # were said and are exempt from the player-line cap; what is said after them goes through
    # ``buffer`` and the cap as always. More than one entry only when several turns were in
    # flight as the backend failed. ``turn_held`` says the channel's latest finished turn attempt
    # ended that way (the cog's "nothing to answer" is then wrong).
    held_parts: list[tuple[int, list[tuple[str, str]]]] = field(default_factory=list)
    turn_seq: int = 0
    turn_held: bool = False
    # A light "who plays whom" hint (display name → character) appended to the system prompt,
    # so the model stops confusing player and character names (open item F).
    alias_hint: str = ""
    # Every character + player name at the table (CharacterStore.speaker_labels). They join the
    # turn's own speakers as cut-labels + stop sequences, so a puppeted "Seskin: …"/"Pr0degie: …"
    # script the model tacks on is truncated — the deterministic guard behind the persona's
    # no-puppeting rule (the live fix; nemo ignores the soft rule). Survives :meth:`DMBrain.reset`.
    known_speakers: list[str] = field(default_factory=list)
    # Memory (Phase 9): the stored session recap + a compact world-state block, injected into the
    # system prompt after the persona (docs/conventions.md order: core → tone → recap → JSON state →
    # history). Set by the cog from the world state, refreshed when state changes.
    recap: str = ""
    state_summary: str = ""
    # The adventure block (stage 1+2 of the hybrid, ADR 019): always-on adventure summary +
    # the current scene card, selected by code from WorldState.scene_id. Set by the cog.
    adventure_block: str = ""
    # The NPC-memory block (ADR 044): what the current scene's NPCs remember, rendered by the
    # runtime from the world state (top-K per NPC). Set alongside the state summary.
    npc_memory_block: str = ""
    # The turn's ``## Regelwerk`` block (stage 3, ADR 019) — refreshed per turn, mostly empty.
    rag_block: str = ""
    # The last turn, so !redo can re-generate it when the DM misunderstood — same input, a fresh
    # answer that replaces the turn's own stored pair (if it has one) in history.
    last_turn: _Turn | None = None
    # The last player action (name, text) consumed — the roll-detection router (ADR 014)
    # classifies it after the narration turn. None when a turn had no player line (e.g. a
    # test-result feedback turn), so the router skips it.
    last_action: tuple[str, str] | None = None
    # Every speaker's action of that same turn, one entry each (D111). ``last_action`` is its
    # last element and stays for callers that only ask "was there an action?"; the router walks
    # this list so a turn with several declarations produces a test button per declaring
    # character instead of only for whoever spoke last.
    last_actions: list[tuple[str, str]] = field(default_factory=list)
    # Replay capture (ADR 046): the structured input of the turn in flight (player lines +
    # drained dice-result lines, set by _prepare_turn/_prepare_opening) and the generation side
    # (the kept answer's raw LLM text + the markers it queued). Drained into the history autosave
    # by take_replay_turn; the eval harness (dm-eval) replays them. Survive :meth:`DMBrain.reset`.
    replay_turn: dict | None = None
    replay_gen: dict | None = None


@dataclass
class _Sink:
    """Where a streamed turn speaks: ``on_sentence`` gets each complete sentence as it is
    ready, ``should_abort()`` (e.g. ``lambda: paused``) stops emission cleanly. A turn with a
    sink streams, a turn without one is a batch turn — the only difference between the paths."""

    on_sentence: Callable[[str], Awaitable[None]]
    should_abort: Callable[[], bool] | None = None


@dataclass
class _Attempt:
    """One LLM call's outcome, batch or streamed: the sanitised answer and its parsed markers.
    A streamed attempt also says what it still holds back (``remaining``, not spoken yet),
    whether it spoke anything and whether the stream broke mid-generation."""

    answer: str
    markers: dict[str, list]
    remaining: list[str] = field(default_factory=list)
    spoke_any: bool = False
    errored: bool = False
