# The Claude CLI caches our system prompt as one block

**Through the Agent SDK we cannot place cache breakpoints; the CLI puts one at the end of our
whole system prompt. One changed byte anywhere in it — a state line, a RAG chunk — and the turn
is a full miss that still pays the cache *write*. Keep the system prompt to what never changes
and put per-turn context in the prompt. And `cache=0` alone proves nothing: look at the writes.**

## What happened

- Live run 2026-11-14: `cache=0` on all 33 narration turns (14–21k prompt tokens), while the
  Haiku `[aux]` lines showed reads. The stat was suspected first; it was right (D142).
- The Haiku reads were a red herring: a schema call takes two requests (prose, then the tool
  call), and the second reads what the first wrote. Within one call, not across turns.
- Four short Opus calls through the client: the old layout wrote 12.9k tokens to the cache
  every turn and read none; with only persona + recap in the system prompt the second turn
  read 10.9k.

## The correction

- Diagnose what the CLI sends, not what we think it sends. Free and without a model call:
  set `ANTHROPIC_BASE_URL` to a local endpoint that records the JSON body and answers 400,
  then run one call through the client. It shows the `system` blocks, every `cache_control`,
  and what the CLI adds on its own. Never log the request headers (they carry the login).
- The split is explicit, not guessed: `assemble_system_prompt` marks its stable head
  (`SystemPrompt.stable`), and the Claude client alone moves the rest to the prompt, so the
  Ollama path is untouched. A new always-in-prompt block belongs after that head unless it is
  byte-stable across turns.
- Log the cache writes next to the reads (`cache_w=` in `[latency]`).

→ ADR 061, amendment 2026-11-14 (fifth).
