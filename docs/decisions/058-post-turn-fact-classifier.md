# ADR 058 — Narrated commitments become hard facts via a post-turn classifier

- **Status:** Accepted (specified; the build and the next debug run are the verification)
- **Date:** 2026-08-23
- **Refs:** serves golden rule #3 (hard state advanced deterministically by code, never written
  from LLM free text); shares the turn boundary and the call pattern of **ADR 057**; gives
  **ADR 045** (consistency guard) and **ADR 044** (NPC memory) the data they never had; state
  schema from **ADR 015**. Lessons: `llm-requests-code-validates`,
  `mandatory-decisions-need-a-separate-classifier`. Plan: `docs/plans/coherent-campaign-run.md`.

## Context

On 2026-08-22 the group won a social test in turn 7 and the seneschal handed over a customs
warrant. In turn 16 the same NPC refused to give them a warrant, and a player asked out loud
whether they had not already been given one. They had. Nine turns later the fact had evaporated.

It evaporated because it was never a fact. The warrant existed only as prose inside the
conversation history, and the history is compacted, truncated and eventually summarised. Nothing
in the world state records that an item changed hands, that a promise was made, or that a quest
was accepted. The state schema carries hard facts for HP, inventory, NPCs and flags — but no
production code writes an item into it from play, and the mission itself is not a fact at all,
which is why the table could ask after 25 minutes what the Ossarium even was and get a tautology
back.

The consistency guard cannot help here twice over: it returns immediately when no NPCs are
registered in the world state (none ever are), and even with data it only checks whether speech
is attributed to a dead or absent NPC. A contradiction about an *object* falls through
structurally.

The dice-side answer to this class of problem already exists and works — the model requests, code
validates and records. Plot-side commitments have never had that seam.

## Decision

1. **A post-turn classifier extracts commitments.** After the turn is narrated, a stateless
   constrained-JSON call reports what the narration committed to: an item handed over or taken
   away, a quest accepted or completed, a promise or condition given by an NPC. It runs on the
   same turn boundary as the scene classifier (ADR 057), sharing one latency window.
2. **Code validates and writes; the model never writes state.** The verdict is a constrained
   enumeration checked against the world-state schema before anything is persisted. Free text is
   never parsed into state. A malformed, out-of-enum or empty verdict changes nothing and is
   logged — the guard fails open, as optional layers must.
3. **The mission is seeded as a hard fact at session start.** The adventure's objective becomes a
   quest in the world state rather than a line of narration, and it is what the player panel
   shows as the goal.
4. **Hard facts are prompt-resident.** Once recorded, an item, a quest or a standing promise
   appears in every subsequent prompt, so the model cannot contradict it without contradicting
   its own context.

## Alternatives

- **An inline `<<GIBT …>>` marker plus a confirmation button:** rejected. Cheaper, and it is the
  established marker pattern — but the same evening produced zero `<<ORT>>` markers in 22 turns.
  Betting a second mandatory decision on the mechanism that just failed is not a trade-off, it is
  a repeat.
- **Extend the consistency guard only — detect the contradiction, do not record the fact:**
  rejected as the primary mechanism. It catches the backwards case (refusing what was given) and
  nothing else: it cannot answer "what do we carry", cannot feed the panel, and cannot tell the
  model what is true. Worth having *in addition*, once NPCs are registered and the guard runs at
  all.
- **Parse the narration with regular expressions:** rejected. German narration about handing over
  an object has an unbounded surface, and a miss is invisible.
- **Ask the model to maintain a running state block in its answer:** rejected outright. It puts
  hard state into LLM free text, which golden rule #3 forbids, and it would be spoken aloud.
- **Only the quest, no items:** considered seriously as a smaller first step. Rejected because
  the observed failure at the table was an item, and the mission fact alone would have left it
  intact.

## Consequences

- **+** The evening's most jarring contradiction — a won test silently reversed — becomes
  impossible without the model contradicting its own prompt.
- **+** The party finally has an answer to "what is our mission", in the prompt and on the panel.
- **+** The consistency guard and NPC memory get real data instead of empty structures.
- **−** A second short LLM call per turn. Mitigated by sharing the turn boundary with ADR 057, and
  individually switchable.
- **−** A false positive writes a fact that never happened, and a prompt-resident wrong fact is
  worse than a forgotten right one. Mitigation: the enumeration is narrow, the write is logged
  and operator-visible, and there is a command to remove a fact at the table.
- **−** More state means more to migrate; the schema gains fields that older session files do not
  carry, so the loader must default them the way the in-game clock migration already does.
