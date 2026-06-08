"""Pre-download the STT + TTS model weights so the first live DM turn doesn't stall on a
multi-minute download. Reads the same env / ``.env`` the bot uses, but does **not** need the
Discord token (so it runs before the bot is fully configured).

Run: ``uv run python -m tools.prefetch_models`` — or via ``setup.ps1 -Prefetch``.

Both models are loaded on **CPU** here on purpose: the download (the slow part) is
device-independent, and a CPU load keeps the prefetch working on a box without a usable GPU.
The bot still loads them on the configured device at runtime — this only fills the on-disk
cache so that first load is instant.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("prefetch")


def prefetch_stt() -> None:
    """Download/cache the faster-whisper model named by ``WHISPER_MODEL`` (default medium)."""
    model = os.environ.get("WHISPER_MODEL", "medium").strip()
    log.info("STT: fetching faster-whisper %r (CPU load; downloads on first run) ...", model)
    # CPU int8 load needs no cuDNN/cuBLAS, so the download works even without a GPU.
    from faster_whisper import WhisperModel

    WhisperModel(model, device="cpu", compute_type="int8")
    log.info("STT: faster-whisper %r ready (cached).", model)


def prefetch_tts() -> None:
    """Download/cache the XTTS v2 model when ``TTS_ENGINE=xtts``. Piper ships locally."""
    engine = os.environ.get("TTS_ENGINE", "xtts").strip().lower()
    if engine != "xtts":
        log.info("TTS: engine=%s — Piper voice ships in voices/, nothing to download.", engine)
        return
    speaker = os.environ.get("TTS_SPEAKER", "").strip()
    log.info("TTS: fetching XTTS v2 (CPU load; first run ~1.8 GB) ...")
    # Importing the project wrapper sets COQUI_TOS_AGREED=1, so the model-licence prompt
    # never blocks an unattended prefetch (dmbot/tts/xtts.py).
    from dmbot.tts.xtts import XttsTTS

    XttsTTS(speaker, device="cpu")
    log.info("TTS: XTTS v2 ready (cached).")


def main() -> int:
    load_dotenv()  # honour WHISPER_MODEL / TTS_* from .env (the Discord token is not needed)
    ok = True
    for label, fn in (("STT", prefetch_stt), ("TTS", prefetch_tts)):
        try:
            fn()
        except Exception:
            ok = False
            log.exception(
                "%s prefetch FAILED — the bot will just download it on first use instead.",
                label,
            )
    if ok:
        log.info("Prefetch complete — the first DM turn won't wait on a model download.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
