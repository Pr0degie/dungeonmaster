# Rolling recap: fold expiring history into the recap before it's lost (Phase-9 follow-up)

Session ritual first (CLAUDE.md): read `progress.md` + the highest-numbered ADR, handshake.
**Run this only after the Phase-9 live gate is met** — it builds on the recap/state flow
(ADR 015) and must not muddy that validation.

## The problem

`DMBrain.summarize` builds the recap from `self._history`, which is capped at
`max_history_turns` (20). In a long session the early turns scroll out of the window
**before `!wrap up` ever runs** — the recap structurally cannot mention the session's
first hour. The narrative-thread half of memory (golden rule 3) silently loses its head.

## Design

**Fold before trim.** When history would drop turns, those turns are first folded into the
stored recap, then trimmed. Flag `DM_ROLLING_RECAP` (default `1`; `0` = today's behavior).

Specifics — these points are the design, deviate only with justification in the handshake:

1. **Batch with hysteresis, not per turn.** Let history grow to a high-water mark
   (e.g. cap + 6 turns), then fold the oldest batch (the overflow) in **one** LLM call —
   never one call per turn.
2. **Off the critical path.** The fold runs as a background `asyncio.Task` scheduled
   *after* the turn's answer is delivered — it must not delay what the DM speaks.
   History is **not trimmed until the fold has landed**; at most **one fold in flight per
   channel** (a new trigger while one runs is a no-op; the next turn re-checks).
3. **The fold prompt** (new builder in `dmbot/memory/recap.py`, German, game content):
   takes the existing recap + the expiring turns rendered like `build_recap_user`, and
   instructs: update the recap — keep established facts, integrate the new events, same
   rules as `RECAP_SYSTEM_DE` (4–8 Sätze … this may need to grow modestly over a long
   session; allow up to ~12 Sätze, dense), end with the current open thread.
4. **Persistence:** the folded recap is written into the channel's `WorldState` and saved
   atomically exactly like other state changes (ADR 015 — code-owned `state.json`), and
   re-injected via `set_context` so the *next* turn's prompt already carries it.
   Keep the ADR-019 prompt order intact (persona → recap → adventure summary + scene →
   …) — the fold changes the recap's content, never its slot.
5. **Token budget:** the prompt now also carries the adventure summary (~300 tokens), a
   scene card, and possibly a `## Regelwerk` block. The grown recap (up to ~12 Sätze)
   must stay within this budget — watch the `[ctx]` numbers (D36 logging) in the live
   test and report them; if turns approach the 85% warning, cap the recap harder rather
   than raising `num_ctx`.
6. **`!wrap up` unchanged in role:** it remains the explicit end-of-session polish — now
   summarizing "current recap + remaining history" instead of history alone (adjust
   `summarize` accordingly).
7. **Degrade, don't lose:** if the fold call fails, log loudly, keep the overflow turns
   (don't trim), retry on the next trigger. Add a hard ceiling (e.g. cap + 20) where, if
   folds keep failing, the oldest turns are dropped *with an ERROR log* — a stuck Ollama
   must not grow history unboundedly.
8. **`reset()` / `!leave`** clear any in-flight fold task cleanly.

Streaming (ADR 017) is merged: the fold is just another non-streaming `chat()` call;
Ollama serializes — no special handling, but verify the fold task doesn't hold any lock
the streaming path needs, and that `!leave` cancels an in-flight fold the same way it
already cleans up the stream/router tasks (ADR 018 fixed an autosave race — don't
introduce a sibling).

## Tests

Fake-client unit tests, no Discord/Ollama: trigger fires at high-water and folds exactly
the overflow batch; one-in-flight guard; recap content updated + state persisted + context
re-injected; fold failure → no trim, retry, hard-ceiling drop with error; `!wrapup` uses
recap + remaining history; flag off → today's behavior byte-identical. Suite green.

## Docs (per the repo's rules)

- **ADR** (next free number): fold-before-trim design, the hysteresis/off-critical-path
  trade-offs, refs ADR 015 + the D-entry. architecture.md **§7** updated in the same
  change (the recap is no longer wrap-up-only).
- `progress.md` per the ritual. `.env.example` documents `DM_ROLLING_RECAP`.

## Constraints

- **Never commit.**
- Final summary: changes per file + a live-test script (how I provoke a fold in a short
  test session without playing 20 real turns — e.g. a temporarily lowered cap via env or
  test hook, and what to watch in `debug.log`).
