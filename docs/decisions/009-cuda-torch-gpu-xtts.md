# ADR 009 — CUDA torch for GPU XTTS (per-machine GPU profiles)

- **Status:** Accepted (index corrected cu126→cu130 on 2026-06-05, see note below)
- **Date:** 2026-06-05
- **Refs:** decision log D21 in `progress.md` (TTS engine) + D16 (Windows runtime); ADR 008
  (Piper + XTTS); ADR 002 (local topology, VRAM, 4070 vs 5080); `architecture.md` §3 (TTS row)

> **Update 2026-06-05:** initially shipped on the **cu126** index (verified on the 4070). A
> colleague's **RTX 5080 (Blackwell, sm_120)** then failed — cu126 torch tops out at sm_90. Moved
> the index to **cu130** (CUDA 13.0), which carries the same torch 2.12.0 and supports **both** Ada
> (sm_89, 4070) and Blackwell (sm_120, 5080); re-verified on the 4070 (real CUDA matmul). cu128 was
> rejected — it only has torch up to 2.11.0 for Windows/cp312. Lesson: pick the CUDA index by the
> *newest* GPU that must run it, not the dev box.

## Context

ADR 008 wired XTTS v2 in-process and ran it on **CPU** (~1.5× realtime — a long DM answer took
30–120 s). The plan to speed it up was a GPU rebalance (whisper→CPU to free VRAM, XTTS→cuda). On
the first attempt XTTS **crashed at load** with `AssertionError: Torch not compiled with CUDA
enabled`: the venv's torch was the **CPU-only** build (`torch 2.12.0+cpu`, `torch.cuda.is_available()
== False`), because PyPI ships torch as CPU-only and `pyproject.toml` declared a plain
`torch>=2.12.0` with no CUDA index. The goal is one codebase that runs **halfway on the 12 GB
4070 (dev/debug)** and puts **everything on the GPU on a 16 GB box (e.g. RTX 5080)**.

## Decision

Pull `torch` / `torchaudio` / `torchcodec` from PyTorch's **CUDA `cu130` index** (CUDA 13.0,
carries torch 2.12.0 for Windows/cp312) via `[tool.uv.sources]` + `[[tool.uv.index]]`, so the
venv gets the `+cu130` builds. Device stays **env-driven** (`TTS_DEVICE`, `WHISPER_DEVICE`,
`WHISPER_COMPUTE`); the **same lock** serves both machines, switched only by `.env` profile. XTTS
**degrades to CPU** (never crashes) when CUDA is absent or the GPU OOMs (`dmbot/tts/xtts.py
_resolve_device` + a load-time fallback), mirroring the STT transcriber's policy.

## Alternatives

- **Stay on CPU XTTS:** no dependency change, but the multi-second/​multi-minute synth latency was
  the whole problem. Rejected.
- **XTTS as its own GPU service** (own venv with CUDA torch): the clean end-state — keeps the bot
  venv lean and isolates the heavy stack. More work; still in the backlog. CUDA torch in the main
  venv was the smaller step that meets the "one repo, both machines" goal now.
- **Switch to Piper for speed:** Piper is ~130 ms and needs no GPU torch, but its German voices
  were rejected in ADR 008 (the reason XTTS exists). Kept only as the fast fallback engine.

## Consequences

- **Positive:** XTTS runs on the GPU — verified live RTF **0.34** (≈3× faster than realtime) vs
  ~1.9 on CPU; `torch.cuda.is_available() == True` (cu130, RTX 4070, CC 8.9). The same `uv sync`
  brings up the 5080 box (Blackwell, CC 12.0).
- **Per-machine GPU profiles** (same code, only `.env` differs; documented in `.env.example`):
  4070 dev = whisper `cpu`/`int8` + XTTS `cuda` (whisper on CPU frees VRAM for XTTS next to nemo);
  5080 = whisper `cuda`/`float16` + XTTS `cuda` (all three on the 16 GB GPU).
- **Resolver constraints (the cost):** CUDA torch pins `nvidia-cudnn-cu12==9.10.2.21` *on linux*,
  which clashes with faster-whisper's `>=9.23.0.39`. Resolved by **locking win32-only**
  (`[tool.uv] environments = ["sys_platform == 'win32'"]`, legitimate per D16) and pinning
  `requires-python` to the 3.12 line. The cudnn/cublas wheels are now marked `sys_platform ==
  'win32'`. The lock is therefore **Windows-only** — fine for both target boxes, but a Linux host
  would need this revisited.
- **Heavy dep (golden rule #9):** the CUDA torch wheel is ~2.4 GB. `httpx` was found to be an
  **undeclared direct dependency** (used by `llm/client.py` + `bridge.py`, previously only
  transitive) and is now declared — the dep churn would otherwise have dropped it and broken boot.
- **Binding / follow-up:** bump the `cu130` index together with the torch version if torch moves;
  the separate-GPU-service refactor (ADR 008 follow-up) still stands as the lean end-state.
