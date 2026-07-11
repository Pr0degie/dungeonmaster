# ADR 045 — Deterministic consistency guard before delivery (dead/absent NPC speaks)

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D92** in progress.md. Builds on **ADR 019/043** (the scene card is
  the ground truth for `npcs_here` and dead rendering), **ADR 018/041** (the retry-once-with-a-
  nudge pattern this mirrors: echo guard, intro guard) and **ADR 035** (the delivery pipeline it
  hooks into). Touches new `dmbot/llm/consistency.py`, `dmbot/orchestrator.py`,
  `dmbot/runtime.py`, `dmbot/voice/delivery.py`, `dmbot/voice/dmcog.py`, `dmbot/config.py`,
  `.env.example`.

## Context

The DM occasionally narrates things the world state forbids: a dead NPC speaks, or a named NPC
who isn't in the current scene chimes in. The scene card already *tells* the model (`(tot)`
markers, `npcs_here`), but a 12B model ignores that often enough to break immersion. We want a
check **before** the answer is spoken/posted — but golden rule #2's spirit applies in reverse:
judging consistency must not become another LLM call (latency, and a judge can be wrong too).

Constraints:

- **False positives cost real latency** (a full regeneration on local hardware), so heuristics
  must be conservative: *when in doubt, do not flag*. A missed violation costs immersion once;
  a false positive costs every player 10+ seconds of silence.
- **The guard must never block the session** — any internal error or a still-failing retry
  degrades to delivering the answer anyway (fail-open + warn log).
- The streaming path speaks sentences while generation runs; the full text exists only after
  the audio has (mostly) played.

## Decision

1. **Pure code check, no LLM judge.** New `dmbot/llm/consistency.py` with
   `check(text, world_state, scene) -> list[Violation]` — no Discord, no I/O, no LLM,
   fixed-input testable like `rules/combat.py`. Two checks in the first cut:
   - **Dead NPC speaks:** an NPC with `wounds <= 0` (what makes the scene card render
     `(tot)`) has a *speech attribution* in the answer.
   - **Absent named NPC speaks:** a living *registered* NPC not listed in the active scene's
     `npcs_here` has a speech attribution. Only with an adventure + known scene; anonymous
     extras the DM invents are never flagged (they aren't registered NPCs).
2. **Conservative speech-attribution heuristics** (German prose, deliberately narrow):
   - *Name then verb:* `<Name> sagt/spricht/antwortet/ruft/flüstert/…` — up to two lowercase
     words may sit between name and verb („Grendel nickt und sagt"). Lowercase-only gap words
     mean no new capitalized subject can slip in (German nouns are capitalized), keeping the
     attribution unambiguous.
   - *Verb then name:* `„…", sagt <Name>` (optionally with a definite article).
   - *Script style:* `<Name>: „…"` at line start (colon **must** be followed by an opening
     quote — a bare `Name: …` list line never triggers).
   - **Present tense only.** Präteritum („Grendel sagte damals …") is how memories and
     recaps are narrated — exactly the allowed "mere mention" case (Erinnerungen,
     Leichenfund), so past forms never flag.
   - **Quoted spans are stripped first** (paired `„…“`, `»…«`, `"…"`), so an NPC *recounting*
     someone's words („‚Grendel sagt so was nie', grinst Janelle") doesn't flag. Attribution
     verbs sit outside the quotes and survive the strip.
   - **Indefinite/quantified references are skipped** („ein Kultist ruft", „mehrere Ganger
     schreien") — generic statblock names (Kultist, Ganger, Dreg) also serve as anonymous
     extras; only a definite reference can mean *the* registered NPC.
   - **Multi-word names match per token** (Vidame Gullar → „Gullar sagt" hits), but tokens
     that are common titles, articles, or shared with another NPC/party member are dropped
     as ambiguous. Names match case-sensitively (proper nouns).
3. **Max one regenerate, fail-open.** Wired in `DMBrain.respond`/`redo` (the batch turn path,
   before the answer is returned to the delivery pipeline → before TTS/post): on a violation,
   regenerate **once** with a concrete German correction appended to the user message
   („KORREKTUR: Grendel ist tot und darf nicht sprechen …" — same mechanism as the echo/intro
   nudges). If the retry still violates: deliver it anyway + warn log. If the retry comes back
   empty: keep the first answer. Any exception inside the guard → deliver unchecked. The
   checker is a callable built by the runtime (`consistency_checker(channel)` — closes over
   the channel's world state + active scene) and passed in by the callers; `check=None` (guard
   off / no state) short-circuits everything.
4. **Marker hygiene on regenerate.** `_generate` queues `<<TEST>>`/`<<MANIFEST>>`/`<<ORT>>`/
   `<<ERLEDIGT>>` markers as a side effect. A discarded first answer must not leave its
   markers behind: the guard snapshots + clears the pending queues before the retry and
   restores the snapshot only if the retry is discarded (mirrors `redo`'s marker hygiene).
5. **Streaming path: log-only.** In `_deliver_streaming` the full text is known only at
   generation end — the sentences are already synthesized and playing. Regenerating there
   would either desync spoken audio from posted text or require throwing away played audio.
   **Trade-off accepted:** on the streaming path the guard only logs the violation
   (`[consistency] …` warn line); the regenerate protection is batch-path only (`nahtlos`
   mode, `!dm`-batch, dice-consequence batch turns). The batch path is also where the intro
   guard lives — the validated-before-spoken paths stay consistent.
6. **Scope:** opening/director turns (`!start`/`!intro`) are not guarded — they run from a
   director brief, have their own intro guard, and routinely name-drop NPCs in framing that
   the heuristics weren't tuned for. Kill switch: `DM_CONSISTENCY_GUARD=1` (default on),
   documented in `.env.example` — house style, every subsystem has one. A regenerate emits a
   `[consistency]`-prefixed log line in the `[latency]` one-line style.

## Alternatives

- **LLM-as-judge consistency check:** rejected — an extra model call per turn on local
  hardware is the latency budget the pipeline fights for, and a judge hallucinating a
  violation would trigger regenerations deterministic code can be *proven* not to.
- **Broader checks in the first cut (location, inventory, time):** rejected — each needs its
  own carefully conservative heuristics; scope-creep here multiplies false positives.
  Follow-up rounds, guided by what live play actually produces.
- **Regenerate more than once / block until consistent:** rejected — the guard must never
  stall the table. One retry captures most of the value; after that the session goes on.
- **Fixing the text instead of regenerating (strip the offending sentence):** rejected —
  surgical deletion of LLM prose produces incoherent narration; a regeneration with a
  concrete correction keeps the answer whole.
- **Wiring the check into the streaming sentence pipeline (abort mid-stream):** rejected for
  the first cut — a violation detected at sentence N has already been spoken; aborting
  mid-answer is worse table experience than finishing it and logging.

## Consequences

- **+** Dead/absent NPCs speaking get caught **before** the table hears them on every batch
  turn — the failure that most visibly breaks the "the DM knows the world" illusion.
- **+** Pure-function core: patterns, tense rule, quote-stripping, ambiguity rules all tested
  without Discord or an LLM.
- **−** A true positive costs one extra generation (~a full LLM turn of latency). Accepted:
  it replaces a broken answer.
- **−** A false positive costs the same. Mitigated by the conservative rules above (present
  tense only, quote-strip, indefinite-article skip, ambiguity drop); if live play still shows
  them, the next dial is shrinking the verb list or requiring direct adjacency.
- **−** The streaming path (default `stream` mode) only logs — the guard's *protection* is
  live mainly in `nahtlos` mode and dice-consequence turns until/unless a stream-abort design
  is worth it. Recorded here so nobody mistakes a `[consistency]` warn log for a failed retry.
- **−** False negatives are deliberate and plentiful (unusual verbs, distant attribution,
  past-tense present speech). The guard is a net, not a wall.
- **Live-unverified:** whether nemo actually produces these violations at a catchable rate —
  gate: provoke a dead NPC into "speaking" live (kill an NPC, steer the conversation at them),
  watch the `[consistency]` regenerate fire and the retry come out clean.

## Addendum — detail preserved from decision log D92 (2026-07-11)

- Test evidence from the round: suite **516 green** (+30 new tests).
