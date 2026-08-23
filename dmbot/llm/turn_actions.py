"""Per-speaker grouping of a turn's buffered player lines (D111) — pure, no I/O.

The roll-detection router (ADR 014) asks a constrained-JSON classifier whether a player's
declared action needs a test, and rolls for *that speaker's* character. Until D111 it was handed
only the last buffered line of the turn, so a turn in which two players declared something could
only ever produce a test for whoever happened to speak last — the other declaration was dropped
without a trace.

That mattered less than it looked on 2026-08-22 (the evening's three tests were all Timo's, and
all three correctly rolled Gellicus Schulz), which is exactly why it is worth fixing now: the
failure is invisible when one player dominates the turn and silent when they do not.

Grouping rules, in one place so the cog stays thin:

* one action per speaker, their lines joined in the order they arrived — a player who pauses
  mid-sentence produces several transcript lines but declared one action;
* first-appearance order, so the resulting buttons read like the table sounded;
* blank lines never become an action;
* a cap on distinct speakers, because every action costs one classifier call. When the cap bites,
  the *most recent* speakers survive: a declaration from the start of a long buffer is the least
  likely to still be the one the table wants rolled.
"""

from __future__ import annotations

# The party size this project designs for (D8: 2–5 players). One classifier call per speaker, so
# the cap is also the ceiling on how many extra calls a single turn can spawn.
MAX_ACTIONS_PER_TURN = 5


def group_by_speaker(
    lines: list[tuple[str, str]],
    *,
    cap: int = MAX_ACTIONS_PER_TURN,
) -> list[tuple[str, str]]:
    """Group ``(speaker, text)`` lines into one ``(speaker, action)`` per speaker.

    ``lines`` is the turn's buffer in arrival order. Returns at most ``cap`` actions, keeping the
    speakers who appear *latest* in the buffer but rendering them in first-appearance order.
    """
    actions: dict[str, list[str]] = {}
    for speaker, text in lines:
        text = (text or "").strip()
        if not text:
            continue
        actions.setdefault(speaker, []).append(text)
    if not actions:
        return []
    speakers = list(actions)
    if cap >= 0 and len(speakers) > cap:
        # Drop from the front: the oldest declarations are the stale ones. Order is preserved
        # among the survivors, so the buttons still read in the order the table spoke.
        speakers = speakers[len(speakers) - cap :]
    return [(name, " ".join(actions[name])) for name in speakers]
