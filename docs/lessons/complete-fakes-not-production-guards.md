# Test doubles must be complete; production code never guards for them

**Build test runtimes and brains with `tests/fakes.py` (`make_runtime()`, `FakeBrain`,
`make_brain()`), never with `SessionRuntime.__new__` or a `SimpleNamespace` carrying a handful
of attributes. Production code reads its own attributes directly. A `getattr(self, "_x", default)`
or `self.__dict__.setdefault(...)` added "so the stub in the test doesn't crash" is the bug.**

## What happened

- Over many rounds, each new runtime attribute got read through `getattr(self, …, default)`
  because some test had built the runtime around `__init__` and lacked it. By 2026-11-12 there
  were about 60 such guards across `runtime.py`, `delivery.py`, the cogs and `orchestrator.py`,
  three lazy `__dict__.setdefault` attributes, plus fallback branches (a pre-D107 scene-move path,
  a log-only rejection path) that only stubs could ever reach.
- The guards could swallow real `AttributeError`s in production, and tests pinned the guards
  instead of behaviour ("a stub brain without `take_pending_uhr` is a no-op").
- Two guards turned out to hide real gaps: `SessionRuntime._loop` and `DMBrain.last_npcs` were
  never created in `__init__`, so direct access could actually raise. The fix was to create them
  in `__init__` (as `None`), not to keep the guard.
- One guard was classified wrongly at first (`getattr(self._client, "last_stats", None)`
  looked like an optional protocol member). The `LLMClient` protocol declares it, and its
  comment named a "test double". Read the protocol or class before calling a guard optional.
- A hand-built stub plus a broad `except` hides the same thing from the other side:
  `test_autorecap._StubRuntime` lacked `_npc_mem_marks` since ADR 044, `_maybe_compact` raised
  `AttributeError` after clearing the history in every test, and its `except Exception` logged
  and swallowed it — the tests stayed green. Found only when new code was added behind that
  line (2026-11-13).

## The correction

- `make_runtime()` runs the real `SessionRuntime.__init__` with only the heavy edges patched
  (preflight, STT, TTS thread, LLM client, RAG, bridge, party file). It is complete by
  construction and grows automatically with `__init__`. Overrides are set afterwards as
  attributes; a property (`clocks_enabled`, `is_debug_run`) is steered through its backing
  field (`_clocks`), not set directly.
- A scripted brain subclasses `FakeBrain` and calls `super().__init__()` first; a scripted
  LLM client carries `last_stats = None`.
- A new runtime attribute goes into `__init__`, even if only a test needs it today.
- A guard stays only for a real optional dependency: `_adventure is None`, XTTS vs. Piper, the
  failover client, discord.py internals, or a verdict that may be missing.

## Why it matters

A guard for a half-built object hides the next real `AttributeError` at the table, and it lets
test fakes stay incomplete. A complete fake removes both problems.
