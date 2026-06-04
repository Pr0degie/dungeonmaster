"""Voice: discord-ext-voice-recv sink, resample (48k stereo -> 16k mono), VAD segmentation.
Phase 2-3. Keep the foreign voice-recv code isolated here."""

from .recv import PcmLogSink

__all__ = ["PcmLogSink"]
