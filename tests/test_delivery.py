"""The streaming delivery pipeline's puffer head-start state machine (ADR 033/035).

``DeliveryPipeline._deliver_streaming`` (dmbot/voice/delivery.py) is the largest extraction of the
ADR-035 split and grew NEW, stateful, concurrent logic that nothing exercised: the ``puffer``
head-start buffer (accumulate ``prebuffer`` synthesised WAVs before the first plays), the
per-sentence speech-transform skip (a sentence that strips to nothing is never synthesised/played),
and the early-abort cleanup (every still-buffered/queued temp WAV is removed when a turn fails
mid-stream, so a failed turn leaks no temp file).

These tests drive the real pipeline with a fake brain (yields a known sentence sequence) and a fake
bridge (records play order), bypassing only TTS synthesis — ``_synthesize`` is swapped for one that
writes a real temp file, so the cleanup path is exercised against the filesystem. The synth/play
timing race that the head-start cushions is real, so the head-start assertions key off guarantees
the play_worker provides by construction (it pulls exactly ``prebuffer`` WAVs before the first play),
not on wall-clock timing. Bot replies are German; logs/tests English (CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from types import SimpleNamespace

from dmbot.orchestrator import TurnAnswer
from dmbot.runtime import _TurnTiming
from dmbot.voice.delivery import DeliveryPipeline

from fakes import FakeBrain, make_runtime


class _Recorder:
    """Shared sink for the fake synth + bridge: what was synthesised, in what order it played, the
    temp paths created (to assert cleanup), and how many sentences were synthesised at the moment of
    the FIRST play (the head-start depth)."""

    def __init__(self) -> None:
        self.created: list[str] = []       # every temp path the fake synth produced
        self.synth_order: list[str] = []    # the (already speech-transformed) texts synthesised
        self.play_order: list[str] = []     # the texts played, via the bridge, in order
        self.wav_text: dict[str, str] = {}  # wav path -> the text it was synthesised from
        self.first_play_synth_count: int | None = None

    def synthesize(self, text: str) -> str:
        """Stand in for DeliveryPipeline._synthesize: write a real (tiny, non-WAV) temp file so the
        cleanup path has something to remove, and record the call. Runs on a daemon thread (list
        appends are GIL-atomic; the test reads them only after the turn finishes)."""
        fd, path = tempfile.mkstemp(prefix="dm_test_delivery_", suffix=".wav")
        os.write(fd, b"x")
        os.close(fd)
        self.created.append(path)
        self.synth_order.append(text)
        self.wav_text[path] = text
        return path


class _FakeBrain(FakeBrain):
    """Yields a fixed sentence sequence through on_sentence, then returns the full answer."""

    def __init__(self, sentences: list[str], user_msg: str | None = None) -> None:
        super().__init__()
        self.sentences = sentences
        self.answer = " ".join(sentences)
        if user_msg is not None:
            self.answer = TurnAnswer(self.answer, user_msg)

    async def respond_streaming(self, channel_id, *, extra_text=None, on_sentence=None,
                                should_abort=None) -> str:
        for s in self.sentences:
            await on_sentence(s)
        return self.answer

    def last_user_msg(self, channel_id):
        return None


class _FakeBridge:
    """Records play order. ``fail_first`` makes the first /speak raise, so a turn fails mid-stream."""

    def __init__(self, recorder: _Recorder, *, fail_first: bool = False) -> None:
        self.rec = recorder
        self.fail_first = fail_first
        self.calls = 0

    async def speak(self, wav: str, *, guild_id=None) -> bool:
        self.calls += 1
        if self.rec.first_play_synth_count is None:
            self.rec.first_play_synth_count = len(self.rec.synth_order)
        if self.fail_first and self.calls == 1:
            raise RuntimeError("bridge 5xx mid-stream")
        self.rec.play_order.append(self.rec.wav_text.get(wav))
        return True


def _stream_runtime(brain, bridge, *, prebuffer: int, transform):
    """The runtime _deliver_streaming runs against — the cog split (ADR 029) reaches all shared
    state through it. No adventure (the marker handlers return early), layer-2 mute off (no sink
    mute/unmute), a TTS backend counted as loaded; Discord sends are recorded."""
    sent: list[str] = []

    async def _send_with_retry(channel, content) -> None:
        sent.append(content)

    async def _handle_dice(channel) -> None:
        return None

    return make_runtime(
        _brain=brain, _bridge=bridge, _tts_enabled=True, sent=sent,
        _brain_channel=lambda channel: channel.id,
        speech_transform=lambda: transform,
        prebuffer_count=lambda: prebuffer,
        _send_with_retry=_send_with_retry,
        handle_dice=_handle_dice,
        # guard off (ADR 045) — the streamed log-only check is tested separately
        consistency_checker=lambda channel: None,
    )


def _run_streaming(*, sentences, prebuffer=1, transform=None, fail_first=False, user_msg=None):
    """Drive one real _deliver_streaming turn and return the recorder + the stored answer."""
    rec = _Recorder()
    brain = _FakeBrain(sentences, user_msg)
    bridge = _FakeBridge(rec, fail_first=fail_first)
    rt = _stream_runtime(brain, bridge, prebuffer=prebuffer, transform=transform)

    async def _post_deliver(channel, answer, timing, *, saved_user_msg=None, redo=False) -> None:
        rec.saved_user_msg = saved_user_msg  # the cog's tail itself is tested on the cog, not here

    pipe = DeliveryPipeline(rt, post_deliver=_post_deliver)
    pipe._synthesize = rec.synthesize  # bypass real TTS; produce a real temp file per sentence

    channel = SimpleNamespace(id=1)
    timing = _TurnTiming(turn=1, trigger=time.monotonic())
    answer = asyncio.run(pipe._deliver_streaming(channel, None, timing))
    return rec, answer


def test_puffer_mode_buffers_prebuffer_sentences_before_first_play():
    """puffer (prebuffer=N): the first N synthesised WAVs are accumulated before any audio plays, so
    the cushion is full when playback starts — then everything plays, in order."""
    rec, answer = _run_streaming(sentences=["Eins.", "Zwei.", "Drei.", "Vier."], prebuffer=3)
    assert rec.first_play_synth_count is not None and rec.first_play_synth_count >= 3
    assert rec.play_order == ["Eins.", "Zwei.", "Drei.", "Vier."]
    assert answer == "Eins. Zwei. Drei. Vier."


def test_plain_stream_plays_first_sentence_without_waiting_for_all():
    """prebuffer=1 (plain stream): the first sentence plays as soon as it is ready, NOT after the
    whole answer is synthesised — the head-start cushion is one sentence deep."""
    rec, answer = _run_streaming(sentences=["Eins.", "Zwei.", "Drei.", "Vier."], prebuffer=1)
    assert rec.first_play_synth_count is not None and rec.first_play_synth_count < 4
    assert rec.play_order == ["Eins.", "Zwei.", "Drei.", "Vier."]


def test_sentence_that_transforms_to_empty_is_skipped():
    """A sentence the speech-transform strips to nothing (e.g. punctuation-only under `flach`) is
    neither synthesised nor played — the other sentences are unaffected."""
    def transform(s: str) -> str:
        return "" if s == "[STILL]" else s

    rec, _ = _run_streaming(sentences=["Hallo.", "[STILL]", "Tschuess."], prebuffer=1,
                            transform=transform)
    assert "[STILL]" not in rec.synth_order and "" not in rec.synth_order  # never synthesised
    assert rec.play_order == ["Hallo.", "Tschuess."]                       # only speakable ones play


def test_aborted_turn_leaves_no_temp_wav_behind():
    """A bridge 5xx on the first play fails the turn mid-stream. Every synthesised WAV — the ones
    buffered for the head-start (removed in play_worker's finally) and any the synth worker queued
    ahead (drained after) — must be cleaned up, so a failed turn leaks no temp file."""
    rec, _ = _run_streaming(sentences=["Eins.", "Zwei.", "Drei."], prebuffer=3, fail_first=True)
    assert rec.created, "sanity: synthesis must have happened, else the cleanup check is vacuous"
    leftover = [p for p in rec.created if os.path.exists(p)]
    assert leftover == []


def test_streaming_delivery_journals_the_player_line_its_answer_carries():
    """The autosave gets the player line from the turn's own answer, not from the brain's
    mutable last turn — that one is None here, as after a compaction (review 2026-11-13)."""
    rec, _ = _run_streaming(sentences=["Die Tür springt auf."], user_msg="[Würfel] Timo: Erfolg")
    assert rec.saved_user_msg == "[Würfel] Timo: Erfolg"
