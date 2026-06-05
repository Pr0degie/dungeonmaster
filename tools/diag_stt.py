"""One-shot STT/CUDA diagnostic — run on the machine where GPU whisper fails.

    uv run python tools/diag_stt.py

Prints, step by step: which commit is checked out, whether the CUDA-12 wheel DLLs are present,
whether the explicit preload (the 2026-06-05 fix) loads them, whether torch sees the GPU, and
whether a real faster-whisper CUDA transcription runs. ASCII-only output (no emoji) so it prints
on any Windows console. Each step is isolated in try/except so the script always reaches the end
and shows the full picture instead of dying on the first error.
"""

from __future__ import annotations

import glob
import importlib.util
import os
import subprocess
import sys
import traceback

# Running as `python tools/diag_stt.py` puts tools/ on sys.path, not the repo root — add the
# repo root so `import dmbot` resolves regardless of where it's launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def line(title: str) -> None:
    print("\n" + "=" * 4, title)


def ok(msg: str) -> None:
    print("  [OK]  ", msg)


def fail(msg: str) -> None:
    print("  [FAIL]", msg)


line("0. environment")
print("  python :", sys.version.split()[0], "|", sys.executable)
print("  cwd    :", os.getcwd())
try:
    head = subprocess.run(
        ["git", "log", "--oneline", "-1"], capture_output=True, text=True
    ).stdout.strip()
    print("  git    :", head or "(not a git checkout?)")
    print("           ^ must be at least 37a8bb6 (the DLL-preload fix)")
except Exception as exc:  # noqa: BLE001
    fail(f"git check failed: {exc}")

line("1. does transcriber.py have the preload fix?")
try:
    src = importlib.util.find_spec("dmbot.stt.transcriber")
    path = src.origin if src else None
    text = open(path, encoding="utf-8").read() if path else ""
    print("  file   :", path)
    if "_CUDA_PRELOAD" in text and "ctypes.WinDLL" in text:
        ok("preload code present (_CUDA_PRELOAD + ctypes.WinDLL)")
    else:
        fail("preload code MISSING — the pull didn't land. Run: git pull")
except Exception as exc:  # noqa: BLE001
    fail(f"could not inspect transcriber.py: {exc}")

line("2. CUDA-12 wheels + DLLs present?")
for pkg in ("nvidia.cuda_runtime", "nvidia.cublas", "nvidia.cudnn"):
    try:
        spec = importlib.util.find_spec(pkg)
    except Exception:  # noqa: BLE001
        spec = None
    if not spec or not spec.submodule_search_locations:
        fail(f"{pkg}: NOT INSTALLED")
        continue
    bin_dir = os.path.join(spec.submodule_search_locations[0], "bin")
    dlls = [os.path.basename(p) for p in glob.glob(os.path.join(bin_dir, "*.dll"))]
    key = [d for d in dlls if d.startswith(("cudart64_", "cublas64_", "cudnn64_"))]
    (ok if key else fail)(f"{pkg}: {key or 'no key DLL found'}  ({len(dlls)} dlls in {bin_dir})")

line("3. is a system CUDA toolkit on PATH? (informational)")
print("  CUDA_PATH:", os.environ.get("CUDA_PATH", "(unset)"))
sys_cublas = [
    p
    for d in os.environ.get("PATH", "").split(os.pathsep)
    if d
    for p in glob.glob(os.path.join(d, "cublas64_*.dll"))
]
print("  cublas on PATH:", sys_cublas or "(none — relying purely on the wheel preload, good test)")

line("4. explicit preload (ctypes.WinDLL by full path)")
try:
    import ctypes

    preload = (
        ("nvidia.cuda_runtime", "cudart64_*.dll"),
        ("nvidia.cublas", "cublasLt64_*.dll"),
        ("nvidia.cublas", "cublas64_*.dll"),
        ("nvidia.cudnn", "cudnn64_*.dll"),
    )
    for pkg, pat in preload:
        spec = importlib.util.find_spec(pkg)
        if not spec or not spec.submodule_search_locations:
            fail(f"{pkg}: not installed, skipping")
            continue
        bin_dir = os.path.join(spec.submodule_search_locations[0], "bin")
        for dll in glob.glob(os.path.join(bin_dir, pat)):
            try:
                ctypes.WinDLL(dll)
                ok(f"loaded {os.path.basename(dll)}")
            except OSError as exc:
                fail(f"{os.path.basename(dll)} -> {exc}")
except Exception:  # noqa: BLE001
    fail("preload step crashed:\n" + traceback.format_exc())

line("5. torch / GPU")
try:
    import torch

    print("  torch  :", torch.__version__, "| cuda build:", torch.version.cuda)
    avail = torch.cuda.is_available()
    (ok if avail else fail)(f"cuda available: {avail}")
    if avail:
        print("  gpu    :", torch.cuda.get_device_name(0), "| capability:", torch.cuda.get_device_capability(0))
        x = torch.randn(64, 64, device="cuda")
        _ = (x @ x).sum().item()
        ok("torch CUDA matmul ran")
except Exception:  # noqa: BLE001
    fail("torch step crashed:\n" + traceback.format_exc())

line("6. real faster-whisper CUDA transcription (the actual failing path)")
try:
    import dmbot.stt.transcriber  # noqa: F401  -> runs _register_cuda_dll_dirs()

    import numpy as np
    from faster_whisper import WhisperModel

    model = os.environ.get("WHISPER_MODEL", "medium")
    m = WhisperModel(model, device="cuda", compute_type="float16")
    ok(f"WhisperModel '{model}' loaded on cuda")
    audio = (np.random.randn(16000 * 2).astype("float32")) * 0.01
    segs, info = m.transcribe(audio, language="de")
    n = sum(1 for _ in segs)  # forces encode() — the line that throws cublas64_12.dll
    ok(f"transcription ran (encode+decode), {n} segment(s) — GPU STT WORKS")
except Exception:  # noqa: BLE001
    fail("transcription FAILED:\n" + traceback.format_exc())

print("\n==== done. copy everything above and send it back ====")
