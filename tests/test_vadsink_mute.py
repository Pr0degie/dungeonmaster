"""FINDING #8 — VadSink layer-2 mute is a reentrant DEPTH COUNTER, not a plain bool.

Two independent owners drive the mute: the DM-speaking paths in dmcog (``_speak`` /
``_deliver_streaming``, balanced ``mute()``/``unmute()`` around the blocking ``/speak``) and the
operator pause/resume in ``voicecog.set_paused``. With a plain bool, an operator *resume*
mid-playback would unconditionally clear the flag and reopen the VAD while Bot A is still talking —
the DM would transcribe its own voice (feedback protection layer 2 defeated, golden rule #4).

These tests pin the counter's nesting semantics deterministically; no audio inference is needed.
The complementary flush-on-mute-boundary and ``_on_pcm`` gating behaviour lives in
``test_feedback_layer2.py``.
"""

from __future__ import annotations

from dmbot.voice.recv import VadSink


def _sink() -> VadSink:
    # on_utterance is a no-op; these tests only exercise the mute depth counter.
    return VadSink(bot_a_user_id=None, on_utterance=lambda *a: None)


def test_balanced_single_owner_leaves_unmuted() -> None:
    """One owner: a balanced mute→unmute pair returns to the unmuted state."""
    sink = _sink()
    assert sink._muted is False  # fresh sink starts unmuted
    sink.mute()
    assert sink._muted is True
    sink.unmute()
    assert sink._muted is False


def test_overlapping_owners_stay_muted_until_last_unmute() -> None:
    """The FINDING #8 case: while owner A still holds the mute, owner B's unmute must NOT reopen.

    mute(A); mute(B); unmute(B) -> STILL muted (B released, A still speaking);
    then unmute(A) -> unmuted (the last owner has released).
    """
    sink = _sink()
    sink.mute()  # owner A (e.g. the DM speaking path) takes the mute
    assert sink._muted is True
    sink.mute()  # owner B (e.g. operator pause) nests on top
    assert sink._muted is True
    sink.unmute()  # owner B releases — A is still speaking, so the VAD must stay shut
    assert sink._muted is True  # the bug case: a plain bool would be False here
    sink.unmute()  # owner A releases — now the last owner is done
    assert sink._muted is False


def test_extra_unmute_does_not_underflow() -> None:
    """A stray unmute (more unmutes than mutes) is clamped at depth 0, never going negative.

    Otherwise the depth would go negative and the next mute()/unmute() pair would leave the VAD
    wedged shut (a stuck mute is exactly the failure mode the fix must not introduce).
    """
    sink = _sink()
    sink.unmute()  # nobody muted — must be a no-op, not depth -1
    assert sink._muted is False
    assert sink._mute_depth == 0
    # And the counter still behaves normally afterwards: one mute mutes, one unmute unmutes.
    sink.mute()
    assert sink._muted is True
    sink.unmute()
    assert sink._muted is False
