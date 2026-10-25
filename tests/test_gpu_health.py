"""GPU fault latch + serialized XTTS synthesis (2026-10-25, fourth Opus run).

Live: two narrations streamed in parallel and two XTTS syntheses ran at once on the same CUDA
model — ``CUDA error: device-side assert triggered``. Such an error is sticky for the whole
process, so Whisper died with it: 80+ "transcription failed" tracebacks until the end, and the
table only noticed that the bot had gone deaf.
"""

from __future__ import annotations

import threading
import time

from dmbot.gpu_health import GpuHealth, is_cuda_fault


def test_cuda_faults_are_recognised_by_their_messages() -> None:
    assert is_cuda_fault(RuntimeError("CUDA error: device-side assert triggered"))
    assert is_cuda_fault(RuntimeError("CUDA failed with error device-side assert triggered"))
    assert is_cuda_fault(RuntimeError("CUDA error: an illegal memory access was encountered"))
    assert not is_cuda_fault(RuntimeError("connection refused"))
    assert not is_cuda_fault(ValueError("bad wav"))


def test_the_first_fault_trips_the_latch_and_notifies_once() -> None:
    calls: list[str] = []
    health = GpuHealth()
    health.set_listener(calls.append)

    assert not health.report(RuntimeError("timeout"), "Sprachausgabe")
    assert not health.broken and calls == []

    assert health.report(RuntimeError("CUDA error: device-side assert triggered"), "Sprachausgabe")
    assert health.report(RuntimeError("CUDA failed with error device-side assert"), "Spracherkennung")
    assert health.broken and health.source == "Sprachausgabe"
    assert calls == ["Sprachausgabe"]  # one notice, however many workers keep failing


def test_the_notice_names_the_fix() -> None:
    health = GpuHealth()
    health.report(RuntimeError("CUDA error: device-side assert triggered"), "Sprachausgabe")
    notice = health.notice_de()
    assert "GPU" in notice and "neu starten" in notice and "Sprachausgabe" in notice


def test_a_raising_listener_does_not_break_the_reporter() -> None:
    health = GpuHealth()

    def boom(source: str) -> None:
        raise RuntimeError("loop closed")

    health.set_listener(boom)
    assert health.report(RuntimeError("CUDA error: device-side assert triggered"), "x")


def test_xtts_synthesis_never_runs_twice_at_once() -> None:
    """The lock: two threads synthesising through one model must take turns."""
    from dmbot.tts.xtts import XttsTTS

    active = 0
    peak = 0
    guard = threading.Lock()

    class _Model:
        def tts_to_file(self, **kw) -> None:
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with guard:
                active -= 1
            open(kw["file_path"], "wb").close()

    tts = XttsTTS.__new__(XttsTTS)
    tts._tts = _Model()
    tts._speaker = "x"
    tts._language = "de"
    tts._lock = threading.Lock()

    threads = [threading.Thread(target=tts.synthesize, args=(f"Satz Nummer {i}.",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1


def test_the_cog_posts_one_notice_when_a_worker_thread_hits_a_cuda_fault(monkeypatch) -> None:
    """End to end on the async side: a fault reported from another thread reaches the channel."""
    import asyncio
    from types import SimpleNamespace

    import dmbot.voice.dmcog as dmcog_mod
    from dmbot.voice.dmcog import DMCog

    fresh = GpuHealth()
    monkeypatch.setattr(dmcog_mod, "gpu_health", fresh)
    sent: list[str] = []

    class _Channel:
        async def send(self, text):
            sent.append(text)

    async def scenario() -> None:
        cog = DMCog.__new__(DMCog)
        cog._rt = SimpleNamespace(_text_channel=_Channel())
        cog._gpu_watch = None
        cog._start_gpu_watch()
        worker = threading.Thread(target=fresh.report, args=(
            RuntimeError("CUDA error: device-side assert triggered"), "Sprachausgabe"))
        worker.start()
        worker.join()
        fresh.report(RuntimeError("CUDA failed with error device-side assert"), "Spracherkennung")
        await asyncio.wait_for(cog._gpu_watch, 2)

    asyncio.run(scenario())
    assert len(sent) == 1 and "GPU-Fehler" in sent[0] and "Sprachausgabe" in sent[0]


def test_log_failure_logs_the_first_traceback_then_short_lines(caplog) -> None:
    import logging

    health = GpuHealth()
    logger = logging.getLogger("test.gpu")
    with caplog.at_level(logging.ERROR, logger="test.gpu"):
        for _ in range(3):
            try:
                raise RuntimeError("CUDA error: device-side assert triggered")
            except RuntimeError as exc:
                health.log_failure(logger, exc, "Spracherkennung", "transcription failed for X")
    records = [r for r in caplog.records if r.name == "test.gpu"]
    assert len(records) == 3
    assert records[0].exc_info is not None
    assert records[1].exc_info is None and "neu starten" in records[1].getMessage()
