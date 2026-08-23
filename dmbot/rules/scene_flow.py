"""Scene advancement — the pure decision core behind ADR 057.

The 2026-08-22 debug run never moved the scene pointer once in 22 turns, because the only
mechanism that could move it was an inline marker the model never emitted. ADR 057 replaces
that with three movers (a post-turn classifier, a model-free flag gate, the demoted marker),
and this module holds everything about them that can be decided without Discord, without the
LLM and without touching a file:

* :func:`resolve_exit` — is this proposed target a legal move? Permitted, or rejected with a
  machine-readable reason (:class:`MoveRejection`) plus the reachable exits, so the wiring can
  phrase the director note and the operator line in German (ADR 057 #5).
* :func:`is_scene_exhausted` / :func:`has_authored_opportunity_ids` — the flag gate (ADR 057 #2).
* :func:`next_scene_on_exhaustion` — where an exhausted scene leads, and an explicit *no guess*
  when more than one exit qualifies.
* :class:`SceneUndo` / :func:`capture_scene_undo` / :func:`apply_scene_undo` — the one-minute
  undo record (ADR 057 #4). The cog only builds the button around it.

Deterministic and side-effect free (golden rule #2/#3: code owns the pointer, the model only
proposes). The scene structure comes from :mod:`dmbot.rag.adventure`; ``rag`` imports nothing
from ``dmbot``, so this edge stays acyclic. State is written back through the narrow
:class:`SceneStateLike` protocol instead of importing ``memory.state`` — the same decoupling
:mod:`dmbot.memory.gametime` uses in the other direction.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from dmbot.rag.adventure import Scene

# The positional ids the loader backfills for a plain-string opportunity (``_parse_elements``).
_DERIVED_OPPORTUNITY_ID = "opp-{n}"


class MoveRejection(str, Enum):
    """Why a proposed scene change was refused — machine-readable on purpose.

    The German wording for the table, the channel and the director note is built by the
    wiring; this module never speaks (code/logs are English, ADR 057 #5)."""

    NO_TARGET = "no_target"            # empty/blank proposal
    NO_CURRENT_SCENE = "no_current_scene"  # pointer sits on an unknown/unloaded scene
    SAME_SCENE = "same_scene"          # already there — a no-op, not a move
    UNKNOWN_SCENE = "unknown_scene"    # not a scene of this adventure at all
    NOT_CONNECTED = "not_connected"    # a real scene, but not in the current scene's leads_to
    LOCKED = "locked"                  # a gated exit whose required element isn't resolved yet


class MoveTrigger(str, Enum):
    """Which of the three movers (ADR 057) caused a change — carried in the undo record so
    the announcement and the operator line can name it, and so a misfiring mover is
    attributable on the next run."""

    CLASSIFIER = "classifier"  # the post-turn constrained-JSON call (ADR 057 #1)
    FLAG_GATE = "flag_gate"    # every opportunity resolved (ADR 057 #2)
    MARKER = "marker"          # the demoted inline <<ORT>> fallback
    COMMAND = "command"        # the operator's !ort


@dataclass(frozen=True)
class MoveVerdict:
    """The answer of :func:`resolve_exit`.

    ``reason`` is None exactly when ``permitted`` is True. ``required_element_id`` is filled
    only for :attr:`MoveRejection.LOCKED` (it names the element of the *current* scene that
    unlocks the exit — operator-visible, never channel-visible: spoiler discipline).
    ``reachable_exits`` is always the currently open exits of the current scene, so a rejection
    can name the real alternatives without a second call."""

    permitted: bool
    target_id: str
    reason: MoveRejection | None = None
    required_element_id: str = ""
    reachable_exits: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExitChoice:
    """Where an exhausted scene leads. ``auto_target`` is set only when the scene has exactly
    one reachable exit — the unambiguous case code may take on its own. With zero or several
    candidates it stays None and ``candidates`` holds them: the wiring then asks the classifier
    or does nothing. Never guess (ADR 057)."""

    auto_target: str | None
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class SceneUndo:
    """Everything a scene change overwrites, captured before the change (ADR 057 #4).

    ``target_scene_id`` is what the change moved *to*; :func:`apply_scene_undo` refuses when the
    pointer has since moved elsewhere, which also makes a second press of the button a no-op."""

    scene_id: str
    time_minutes: int
    time_ingame: str
    target_scene_id: str
    trigger: MoveTrigger | None = None


@runtime_checkable
class SceneStateLike(Protocol):
    """The narrow slice of ``WorldState`` a scene change touches (structural — no import)."""

    scene_id: str
    time_minutes: int
    time_ingame: str


# -- exits ---------------------------------------------------------------------------------------

def reachable_exits(scene: Scene | None, resolved_ids: Collection[str] = ()) -> tuple[str, ...]:
    """The current scene's exits that are open right now, in card order.

    A gated exit (``exit_requires``, ADR 043) counts only once its required element id is in
    ``resolved_ids``. Ungated exits are always open. Missing scene → no exits."""
    if scene is None:
        return ()
    resolved = {str(r) for r in resolved_ids}
    return tuple(
        target for target in scene.leads_to
        if scene.exit_requires.get(target) is None or scene.exit_requires[target] in resolved
    )


def resolve_exit(
    scene: Scene | None,
    target_id: str | None,
    *,
    resolved_ids: Collection[str] = (),
    known_scene_ids: Collection[str] | None = None,
) -> MoveVerdict:
    """Judge a proposed move out of ``scene`` — permitted, or rejected with a reason.

    ``known_scene_ids`` (all scene ids of the adventure) only separates
    :attr:`MoveRejection.UNKNOWN_SCENE` from :attr:`MoveRejection.NOT_CONNECTED`; without it
    both collapse to NOT_CONNECTED. The move itself is never permitted for a non-neighbour —
    the operator's free-mode ``!ort`` bypass stays in ``Adventure.resolve_move``, not here."""
    target = (target_id or "").strip()
    exits = reachable_exits(scene, resolved_ids)

    def reject(reason: MoveRejection, *, required: str = "") -> MoveVerdict:
        return MoveVerdict(False, target, reason, required, exits)

    if not target:
        return reject(MoveRejection.NO_TARGET)
    if scene is None:
        return reject(MoveRejection.NO_CURRENT_SCENE)
    if target == (scene.id or "").strip():
        return reject(MoveRejection.SAME_SCENE)
    if target not in scene.leads_to:
        if known_scene_ids is not None and target not in {str(s) for s in known_scene_ids}:
            return reject(MoveRejection.UNKNOWN_SCENE)
        return reject(MoveRejection.NOT_CONNECTED)
    required = scene.exit_requires.get(target)
    if required and required not in {str(r) for r in resolved_ids}:
        return reject(MoveRejection.LOCKED, required=required)
    return MoveVerdict(True, target, None, "", exits)


# -- the flag gate -------------------------------------------------------------------------------

def has_authored_opportunity_ids(scene: Scene | None) -> bool:
    """Whether this scene's opportunities carry ids an author actually wrote.

    ``Scene.__post_init__`` backfills ``opp-1``, ``opp-2``, … for every plain-string
    opportunity, so an id-less card is indistinguishable by presence alone — it is
    distinguishable by *shape*. A scene whose ids are exactly the positional sequence is
    treated as id-less. False negative accepted: a campaign that literally names its ids
    ``opp-1`` loses the flag gate and keeps the classifier — it fails safe (no auto-advance)."""
    ids = [str(e) for e in (scene.opportunity_ids if scene else [])]
    if not ids:
        return False
    return any(eid != _DERIVED_OPPORTUNITY_ID.format(n=i) for i, eid in enumerate(ids, start=1))


def is_scene_exhausted(scene: Scene | None, resolved_ids: Collection[str] = ()) -> bool:
    """Is every opportunity of ``scene`` resolved? The model-free trigger of ADR 057 #2.

    Only opportunities count — secrets may stay buried and must not hold a scene open.
    Ids from other scenes in ``resolved_ids`` are ignored.

    **Deliberate deviation from ADR 057 #3.** The ADR makes opportunity ids mandatory campaign
    data enforced at load, i.e. an id-less compendium would fail to load. That is a hard error
    for a campaign nobody is playing right now: the unversioned ``chemical_burn`` carries no ids
    and would take the bot down instead of merely losing one trigger. Here the gate simply never
    fires for such a scene (see :func:`has_authored_opportunity_ids`) — and a scene with no
    opportunities at all is never exhausted either, since ``all(())`` would otherwise advance the
    pointer on the very first turn. Advancement then rests on the classifier, as before the gate."""
    if scene is None or not has_authored_opportunity_ids(scene):
        return False
    resolved = {str(r) for r in resolved_ids}
    return all(str(eid) in resolved for eid in scene.opportunity_ids)


def next_scene_on_exhaustion(
    scene: Scene | None, resolved_ids: Collection[str] = ()
) -> ExitChoice:
    """Where to go when the flag gate fires: the single reachable exit, or the candidates.

    Decides only the unambiguous case. Zero exits (a dead end / an end scene) and several open
    exits both return ``auto_target=None``; the wiring hands the candidates to the classifier or
    leaves the pointer alone."""
    candidates = reachable_exits(scene, resolved_ids)
    return ExitChoice(candidates[0] if len(candidates) == 1 else None, candidates)


# -- undo ----------------------------------------------------------------------------------------

def capture_scene_undo(
    state: SceneStateLike, target_scene_id: str, *, trigger: MoveTrigger | None = None
) -> SceneUndo:
    """Snapshot the pre-change state. Call this *before* writing the new pointer."""
    return SceneUndo(
        scene_id=state.scene_id,
        time_minutes=state.time_minutes,
        time_ingame=state.time_ingame,
        target_scene_id=(target_scene_id or "").strip(),
        trigger=trigger,
    )


def apply_scene_undo(undo: SceneUndo, state: SceneStateLike) -> bool:
    """Restore the snapshot; True when it was applied.

    False — and no write at all — when ``state.scene_id`` is no longer the scene this undo
    moved to: something else has moved the pointer since (another mover, the operator, or a
    second press of the same button), and clobbering that would be worse than not undoing."""
    if state.scene_id != undo.target_scene_id:
        return False
    state.scene_id = undo.scene_id
    state.time_minutes = undo.time_minutes
    state.time_ingame = undo.time_ingame
    return True
