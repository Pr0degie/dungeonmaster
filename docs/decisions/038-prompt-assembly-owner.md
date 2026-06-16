# ADR 038 — Single owner for the DM system-prompt assembly (join-only extraction)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Refs:** decision log **D80** in progress.md; `/improve-architecture` candidate #5. Extends the
  **ADR 034** family (pure helpers extracted out of `orchestrator.py`). Owns the memory order set by
  **ADR 019** (3-stage hybrid prompt: persona → recap → state → adventure/RAG). Golden rule #2 is
  untouched (this is prose assembly, no dice).

## Context
To answer "what is in the DM system prompt, in what order, and where do I change slice X?", an agent
had to read `orchestrator._build_request`, where the order lived only as a docstring comment plus a
sequence of `if slice: system = f"{system}\n\n{slice}"` statements. The slice *contents* arrive through
**three different timing mechanisms** across five modules:

- **persona** — read from disk inline via `load_system_prompt()` on every call;
- **recap / state_summary / adventure** — pushed into caches by `set_context()` on mutation;
- **RAG** — pulled per turn by `_refresh_rag()` (query-dependent);
- **alias hint** — set once on `!join`.

The state slice is itself a mini-montage (`world_state_summary_de` + `_psyker_block` + `_augmetic_block`)
built in the runtime. So the "prompt" was spread across six modules with three timings, and its order
was an implementation detail buried in a method that also reads caches and builds the Ollama request.

## Decision
Extract **only the final string-join** into a pure, order-explicit, testable function
`assemble_system_prompt(persona, *, recap, adventure, state_summary, rag, alias_hint)` in a new module
**`dmbot/llm/prompt_assembly.py`**. It owns the order (persona → recap[wrapped] → adventure →
state_summary → rag → alias_hint), includes each optional slice **only when truthy** (so `None` and
`""` are both skipped, replicating the old `if recap:` chain), wraps the recap in its German "Was bisher
geschah" header, and joins with `"\n\n"`. `_build_request` keeps the six `.get()` cache reads **inline**
and calls the assembler; its `messages`/`options`/`return` lines are unchanged.

**The key restraint (the real trade-off): do NOT unify slice computation/caching into the owner.** The
cache-vs-pull timing is deliberate — RAG is query-dependent and must be re-pulled every turn;
recap/state/adventure change only on mutation and are cached; persona is a cheap disk read each call. A
"provider registry" owning both computation and assembly would either break that timing or re-pull RAG
on every cache push / recompute state every turn. So the owner is **join-only**; *when* each slice is
computed stays exactly where it was.

## Alternatives
- **Provider registry owning computation + caching + order** (the original candidate's tempting form):
  rejected — it would have to break or re-implement the deliberate cache-vs-pull timing, with a blast
  radius across six modules, for a navigation/testability win. High behaviour-drift risk.
- **Leave it inline:** rejected — the order was invisible (a comment), and there was no way to assert
  the assembled prompt without an LLM round-trip.
- **Move per-slice formatting into the owner too** (the state montage, the adventure/RAG block
  headers): rejected for everything except the recap wrapper. The recap wrapper was already applied at
  *build* time, so it moved in cleanly; adventure/state/rag/hint are pre-formatted at their **sources**
  (`set_context`/`_refresh_rag`), and moving their formatting would touch the caching paths and the
  timing.

## Consequences
- **+** The prompt order is now explicit and **unit-testable** — assert the assembled string from fixed
  slice inputs, no LLM needed (`tests/test_prompt_assembly.py`).
- **+** Behaviour provably unchanged: byte-identical output (recap header byte-for-byte, `"\n\n"` joins,
  truthy-skip semantics), full suite **359 green**, **0** existing-test edits, ruff clean,
  `set_context`/`_refresh_rag` not in the diff (timing preserved).
- **+** A future agent changing "where slice X goes" edits one named function.
- **−** The owner is join-only: it does **not** tell you where each slice is computed or cached — that
  still lives in `set_context`/`_refresh_rag`/`load_system_prompt`. The module docstring points there.
  This is the deliberate boundary that keeps the timing intact.

_Companion D80 moves this round (D-entries, no ADR): **#4** `runtime.seed_session` (bundles the `!join`
seed sequence — party/turn-order/state/scene-pointer/crash-recovery; voice-receive wiring +
announcements stay in the cog) and **#6** `runtime.clear_panel` (the delete-previous-pinned-panel block,
byte-identical in four places, into one helper; the pause panel's deliberate edit-in-place stays)._
