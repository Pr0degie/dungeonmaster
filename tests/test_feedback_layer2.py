"""Phase 7 — feedback protection layer 2 (ADR 003): the VadSink mute gate.

Layer 2 pauses segmentation while Bot A speaks, so the DM never transcribes its own voice
(belt-and-braces over the layer-1 user-ID filter) and table talk over the narration isn't
captured. The real-time audio path is verified by the live phase gate; here we pin the
deterministic part — the mute flag's effect on ``_on_pcm`` and the flush-on-mute boundary —
with fake segmenters, no audio inference needed.
"""

from __future__ import annotations

from dmbot.voice.recv import VadSink


class _FakeSeg:
    """Stands in for an UtteranceSegmenter so feed/flush calls are observable."""

    def __init__(self) -> None:
        self.fed = 0
        self.flushed = 0

    def feed(self, samples) -> None:
        self.fed += 1

    def flush(self) -> None:
        self.flushed += 1


def _sink() -> VadSink:
    # on_utterance is a no-op; we never complete a real utterance in these tests.
    return VadSink(bot_a_user_id=None, on_utterance=lambda *a: None)


# 20 ms of 48 kHz stereo s16le silence (960 frames * 2 ch * 2 bytes) — a valid _on_pcm input.
_PCM_20MS = b"\x00\x00" * 1920


def test_on_pcm_dropped_while_muted() -> None:
    """While muted, _on_pcm returns before touching the pipeline — no segmenter is even built."""
    sink = _sink()
    sink.mute()
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 not in sink._segmenters
    assert 7 not in sink._resamplers


def test_on_pcm_segments_when_unmuted() -> None:
    """The default (unmuted) path builds and feeds the per-user pipeline as before."""
    sink = _sink()
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 in sink._segmenters  # pipeline created when audio is allowed through


def test_mute_flushes_open_utterances() -> None:
    """Muting flushes in-progress utterances so pre-DM speech isn't glued across the gap."""
    sink = _sink()
    fake = _FakeSeg()
    sink._segmenters[42] = fake
    sink.mute()
    assert sink._muted is True
    assert fake.flushed == 1


def test_mute_is_idempotent() -> None:
    """A second mute (e.g. overlapping !say/!dm) must not re-flush already-reset segmenters."""
    sink = _sink()
    fake = _FakeSeg()
    sink._segmenters[42] = fake
    sink.mute()
    sink.mute()
    assert fake.flushed == 1


def test_unmute_resumes() -> None:
    """Unmute clears the flag so the next frame segments again (Bot A has gone quiet)."""
    sink = _sink()
    sink.mute()
    sink.unmute()
    assert sink._muted is False
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 in sink._segmenters


# --- push-to-talk listen gate (Phase 7) ------------------------------------------------------

def test_on_pcm_dropped_when_not_listening() -> None:
    """With the mic gate off, _on_pcm drops audio before building any pipeline (no backlog)."""
    sink = _sink()
    sink.set_listening(False)
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 not in sink._segmenters


def test_listening_defaults_on() -> None:
    """Default is continuous (legacy) — the cog flips it off at join when push-to-talk is set."""
    sink = _sink()
    assert sink.listening is True
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 in sink._segmenters


def test_set_listening_off_flushes_open_utterance() -> None:
    """Tapping the mic off captures the trailing utterance (flush) rather than dropping it."""
    sink = _sink()
    fake = _FakeSeg()
    sink._segmenters[42] = fake
    sink.set_listening(False)
    assert sink.listening is False
    assert fake.flushed == 1


def test_set_listening_is_idempotent() -> None:
    """Re-asserting the same state doesn't re-flush."""
    sink = _sink()
    fake = _FakeSeg()
    sink._segmenters[42] = fake
    sink.set_listening(False)
    sink.set_listening(False)
    assert fake.flushed == 1


def test_mute_overrides_listening() -> None:
    """Layer 2 wins: even mid push-to-talk, audio is dropped while Bot A speaks."""
    sink = _sink()
    sink.set_listening(True)
    sink.mute()
    sink._on_pcm(7, "Alice", _PCM_20MS)
    assert 7 not in sink._segmenters
