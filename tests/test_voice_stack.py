"""Offline smoke test for the fragile voice-receive stack (no Discord needed).

This is the **canary** the voice stack lacked: after any `uv sync` / dependency upgrade, run
it to confirm in ~1 s that the version-sensitive receive path still stands, *before* a live
session turns a silent break into a garbage transcript (CLAUDE.md, ADR 006).

It checks three things:
  1. the three pinned voice distributions match the verified set (preflight.KNOWN_GOOD);
  2. the sink / DAVE attribute paths the code reaches into still exist;
  3. the resample → silero-VAD pipeline actually runs a synthetic frame end to end
     (catches an onnxruntime / soxr / model-file break).

Runs under pytest (functions named ``test_*``) and as a plain script
(``uv run python tests/test_voice_stack.py``) so it works even before pytest is added.
"""

from __future__ import annotations

import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np

# Make the repo root importable when run as a bare script (pytest handles this itself).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dmbot.voice import preflight  # noqa: E402
from dmbot.voice.resample import StereoResampler  # noqa: E402
from dmbot.voice.vad import SileroVad, UtteranceSegmenter  # noqa: E402


def test_pinned_versions_match_known_good() -> None:
    """The installed voice distributions equal preflight.KNOWN_GOOD (and the == pins)."""
    for dist, want in preflight.KNOWN_GOOD.items():
        have = version(dist)
        assert have == want, (
            f"{dist} is {have}, verified is {want}. If this is a deliberate upgrade, "
            f"re-verify a live session and bump preflight.KNOWN_GOOD + the ADR 006 table."
        )


def test_check_static_reports_no_problems() -> None:
    """The full static preflight (versions + sink/DAVE attribute paths) is clean."""
    problems = preflight.check_static()
    assert problems == [], f"voice-stack preflight found issues: {problems}"


def test_resample_downmixes_and_targets_16k() -> None:
    """48 kHz stereo s16le → ~16 kHz mono float32 (the rate STT/VAD require)."""
    # One second of 48 kHz stereo: a quiet 220 Hz tone, interleaved L,R as int16.
    t = np.arange(48_000, dtype=np.float32) / 48_000
    tone = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    stereo = np.empty(tone.size * 2, dtype=np.int16)
    stereo[0::2] = tone  # L
    stereo[1::2] = tone  # R

    out = StereoResampler().feed(stereo.tobytes())
    assert out.dtype == np.float32 and out.ndim == 1, "resampler must yield mono float32"
    # soxr buffers across chunk boundaries, so allow a small priming shortfall on one chunk.
    assert 15_000 <= out.size <= 16_500, f"expected ~16k samples for 1 s, got {out.size}"


def test_silero_vad_loads_and_runs_a_window() -> None:
    """The vendored silero onnx still loads under this onnxruntime and scores a window."""
    vad = SileroVad()  # raises FileNotFoundError if the vendored model went missing
    state, context = vad.new_state(), vad.new_context()
    prob, state, context = vad(np.zeros(512, dtype=np.float32), state, context)
    assert 0.0 <= prob <= 1.0, f"VAD probability out of range: {prob}"
    assert context.shape == (64,), "v5 context carry must be 64 samples"


def test_segmenter_pipeline_runs_without_raising() -> None:
    """resample → UtteranceSegmenter wiring: feeding real samples must not raise.

    Uses a scripted fake VAD (no model dependency) so this stays a pure wiring check; the VAD
    model itself is covered above. We only assert the pipeline runs and the callback contract
    (bytes, float) holds — not the exact segmentation, which is unit-tested elsewhere.
    """
    emitted: list[tuple[bytes, float]] = []

    class _FakeVad:
        # Duck-types SileroVad: 20 windows of speech, then silence to close the utterance.
        def __init__(self) -> None:
            self._n = 0

        @staticmethod
        def new_state() -> np.ndarray:
            return np.zeros((2, 1, 128), dtype=np.float32)

        @staticmethod
        def new_context() -> np.ndarray:
            return np.zeros(64, dtype=np.float32)

        def __call__(self, window, state, context):
            self._n += 1
            prob = 0.9 if self._n <= 20 else 0.0
            return prob, state, window[-64:].copy()

    seg = UtteranceSegmenter(_FakeVad(), lambda pcm, dur: emitted.append((pcm, dur)))
    samples = np.zeros(512 * 60, dtype=np.float32)  # ~2 s of 16 kHz frames
    seg.feed(samples)
    seg.flush()
    for pcm, dur in emitted:
        assert isinstance(pcm, (bytes, bytearray)) and isinstance(dur, float)


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception as exc:  # report and keep going — show every failure in one run
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
