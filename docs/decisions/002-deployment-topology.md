# ADR 002 — Deployment topology: develop locally, offload the LLM later

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** decision log D6 in `progress.md`; `architecture.md` §2

## Context

Tobi (RTX 4070, 12 GB) and his colleague (RTX 5080, 16 GB) are **not on the same
network**. Originally the LLM was planned on the stronger 5080, with Bot B on Tobi's
machine — which would have forced a cross-network call. Two insights change the picture:
(1) Discord is the meeting point for the voice audio, not the home networks — where the
bots run is irrelevant to Discord. (2) The bridge passes a file path to the WAV, so it
only works with a shared filesystem → the two bots must sit together on one machine.

## Decision

For development and the MVP, **everything runs on Tobi's 4070** (both bots, STT, TTS, RAG
and Ollama locally, model Mistral Nemo 12B). Only when the model feels too weak does
**only Ollama** move to the 5080, reachable via Tailscale.

## Alternatives

- **Everything on the colleague's 5080.** Best hardware, could run a 24B model. But: Tobi
  (the developer) would develop on remote hardware and debug real-time audio there; the
  colleague's PC would have to be on for every session.
- **Bots on Tobi's, Ollama on the 5080 from the start (Tailscale).** Uses the better card
  immediately, but brings Tailscale setup and a cross-network hop into the MVP before
  anything even runs.

## Consequences

- **Positive:** local, fast iteration; the separate networks are irrelevant for the whole
  MVP; no Tailscale dependency to start. Nemo 12B fits alongside Whisper-small and Piper
  in 12 GB.
- **Binding / prerequisite:** `OLLAMA_HOST` stays strictly configurable (never hardcoded),
  so the later switch is a one-liner. Both bots stay co-located as long as the bridge works
  via a file path — if you ever split the bots, the bridge must transfer audio bytes instead.
- **Upgrade path:** Tailscale Personal plan (free, up to 6 users, unlimited devices; as of
  April 2026). P2P latency is negligible against token generation, so no noticeable
  difference in play feel.
