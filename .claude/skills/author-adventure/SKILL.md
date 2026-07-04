---
name: author-adventure
description: Use when drafting a new adventure compendium (data/adventures/<id>/adventure.json + npcs.json) from a converted adventure markdown (pdf_to_md output), or when the user says "author-adventure" / "Abenteuer aufbereiten". Interactive, offline, human-curated — structure pass stops for scene-cut confirmation, then card/NPC/summary passes in profile-aligned German, spoiler-discipline self-check, loader validation, and a review checklist targeting the weak spots. Output stays untracked; never commits.
---

# Author an adventure compendium from a converted markdown

`/author-adventure <path-to-adventure-md> <adventure-id>`

Turns a converted adventure book (`data/pdfs/md/<book>.md`, produced by `/rag-ingest`'s
`pdf_to_md.py`) into a **draft** `data/adventures/<id>/adventure.json` + `npcs.json` in the
exact schema `dmbot/rag/adventure.py` parses. The human stays **Kurator**: the skill delivers
a draft plus a review checklist that points at its own weak spots — never a silently-finished
compendium. Goal: a 50-page adventure costs an afternoon of *redigieren*, not days of authoring.

**Read `dmbot/rag/adventure.py` before anything else** — it is the schema's source of truth
(`Scene`, `AdventureNpc`, `Adventure.load`), including the ADR 043 stateful-card extensions
(element ids, gated exits). ADR 019/020 (scene-tracker hybrid) and ADR 043 govern the design.

## Hard rules

1. **Everything player-facing is German** (docs/code English — CLAUDE.md language convention).
2. **Profile vocabulary, never invented terms.** Skill names and difficulties in
   `opportunities_de` must match the active profile (`data/systems/<DM_SYSTEM>.json`, default
   `imperium_maledictum`) and the party sheets — that's the roll router's vocabulary.
   Difficulties come **verbatim from `difficulty_ladder`** (IM: `Sehr leicht`, `Leicht`,
   `Routine`, `Herausfordernd`, `Schwierig`, `Schwer`, `Sehr schwer`). Skill names: collect the
   union of the party's `skills` keys (`data/sessions/_default/characters.json` +
   `data/party/*.json`) plus the profile's `combat.attack_skills` / `psyker.test_skill` /
   `psyker.purge_skill`. A skill the book demands but the vocabulary doesn't contain goes on
   the **checklist as a mismatch** — never coin a German name silently.
3. **Spoiler discipline is a schema property.** Reveals, twists, perpetrators, and anything
   the party must *earn* belongs in `secrets_de` of the scene where it surfaces — never in
   `description_de`, `guidance_de`, or `summary_de`. This is self-checked in pass 5.
4. **Nothing from the bought book lands in tracked files.** Before writing, run
   `git check-ignore -q data/adventures/<id>/adventure.json` — if that exits non-zero (path
   would be tracked), **abort loudly** and stop. Scratch notes go to the scratchpad, not the
   repo. This SKILL.md itself carries schema knowledge only, zero book content.
5. **Draft, don't decide.** Ambiguities (scene merges/splits, guessed difficulties, NPCs
   without statblocks, unclear gates) are flagged on the checklist, not resolved by fiat.

## Schema (what the loader parses)

```jsonc
// adventure.json
{
  "id": "<adventure-id>",
  "title": "<Book title>",
  "start_scene": "<scene-id>",
  "summary_de": "<~300-token German GM digest of the whole arc>",
  "scenes": [
    {
      "id": "kebab-case-stable-id",
      "title_de": "…",
      "part": 1,                          // chapter/act number, 1-based
      "description_de": "…",              // 2–4 dense sentences, GM-knowledge
      "npcs_here": ["Name", "…"],         // names; statblock join is by name, case-insensitive
      "opportunities_de": [               // plain string OR {"id": "...", "text_de": "..."}
        "Fertigkeit (Schwierigkeit): was ein Erfolg liefert.",
        {"id": "generator-fixed", "text_de": "…"}   // explicit id only when a gate needs it
      ],
      "secrets_de": ["…"],                // same two forms; derived ids are geh-1, geh-2, …
      "leads_to": [                       // plain scene-id OR gated {"ziel": "...", "requires": "<element-id of THIS scene>"}
        "next-scene", {"ziel": "finale", "requires": "generator-fixed"}
      ],
      "guidance_de": "…"                  // steering hint for off-script play (no spoilers)
    }
  ]
}
// npcs.json
{ "npcs": [ { "name": "…", "role_de": "…", "wounds": 10, "toughness_bonus": 3, "armour": 1,
              "roleplaying_de": "…", "attack_skill": "Nahkampf", "attack_value": 35,
              "weapon": "Kettenmesser", "damage": "1d10+3",
              "faction": "…",                 // optional: gossip group for NPC memory (ADR 044)
              "goal_de": "…" } ] }            // optional: agenda goal, one sentence (ADR 049)
```

Schema gotchas (from `adventure.py` / ADR 043):
- Plain `opportunities_de`/`secrets_de` strings get **positional ids** (`opp-1…`/`geh-1…`).
  Use the plain form by default; give an **explicit id** only to elements a gate `requires`
  (positional ids shift when the list is re-edited). Explicit ids must be unique within the
  scene **across both lists** and must **not end in `-` or `_`** (glued-marker strip).
- A `requires` must name an element of the **same scene** that owns the `leads_to` — the
  loader drops unknown gates with an `ERROR` log (fails open).
- Duplicate **scene ids** silently collapse in the loader's dict — the validation step
  catches this; keep ids unique and stable (they persist in `state.json`).
- `attack_*`/`weapon`/`damage` on NPCs are informational (NPC→PC damage is narrated);
  `wounds`/`toughness_bonus`/`armour` feed the engine via `!npc add`.
- **German quotes inside JSON strings:** close `„…“` with U+201C (`“`), never with an
  ASCII `"` — that terminates the JSON string (the smoke test broke on exactly this,
  30× in one file). After writing, `json.loads` the file before running the validator.

## Workflow

### 0. Setup
Read `dmbot/rag/adventure.py`. Load the profile's `difficulty_ladder` + build the skill
vocabulary (hard rule 2). Run the `git check-ignore` guard (hard rule 4). Then read the
adventure md **section by section** (grep-first for chapter headings — the file is large;
don't load 180 KB at once).

### 1. Structure pass — STOP for confirmation
Map the book's parts/chapters/locations to a proposed scene list. Deliver:
- a table: `id | title_de | part | leads_to | source section in the md`
- a text sketch of the location graph (who leads where, proposed gates)
- explicit notes where you **merged** locations (too thin to stand alone) or **split** one
  (two distinct beats in one chapter)

Conventions learned from the hand-built `chemical_burn` compendium (repo precedent —
deviate only with a reason on the checklist):
- **A dedicated opening/briefing scene as `start_scene`** (cf. `auftrag`): the patron's
  brief is its own beat — `!start`/`!intro` anchor to it before the party reaches the first
  location.
- **Graph style is forward-dramaturgical, not a physical mesh**: `leads_to` encodes where
  the *story* flows next (sparse, mostly no backtracking edges), because `verbunden` mode
  treats it as the legal-move list. Propose the sparse graph; offer the dense
  physical-adjacency mesh as the alternative and let the curator pick.
- **Keep the book's proper nouns** for locations/NPCs (Mud Gate, The Pit, Edifice of
  Tears) with a German gloss in `title_de` — players recognize them; don't translate names.
- Scene ids in the existing compendium style (`chemical_burn` uses `snake_case`).

**Stop and wait for the user's approval of the scene cut before writing any card** — the
scene cut is *the* design decision. Only proceed autonomously if the user explicitly asked
for a non-interactive dry-run.

### 2. Card pass
Per approved scene, draft the card:
- `description_de`: 2–4 dense sentences of **GM knowledge** (atmosphere + what is objectively
  here), never read-aloud prose, never secrets.
- `npcs_here`: names as they'll appear in `npcs.json`.
- `opportunities_de`: the format is `Fertigkeit (Schwierigkeit): Konsequenz` — what a test is
  for and what success yields (strong-success extras in parentheses). Non-roll opportunities
  are plain German sentences. Difficulties from the book where stated; where guessed, flag on
  the checklist.
- `secrets_de`: everything spoiler-bearing that surfaces *in this scene*.
- `leads_to`: the book's actual connectivity; add `requires` gates **only** where the book
  gates progress ("the door opens only after…"), naming an explicit-id element of this scene.
- `guidance_de`: how to steer back when the party goes off-script here (spoiler-free).

### 3. NPC pass
Book statblocks → `npcs.json` per the `AdventureNpc` fields; map the system's stat lines to
`wounds`/`toughness_bonus`/`armour` and pick the signature attack for `attack_*`.
`roleplaying_de` from the book's personality/mannerism notes (German, 1–2 sentences).
**Every name in any `npcs_here` gets a statblock** (repo precedent: `chemical_burn` covers
24/24, including talkers like clerks and priests — `!npc add` and the dead-NPC render join
by name and must never miss). Adventures often reference core-book NPC archetypes by page
instead of printing stats — draft plausible values and mark every such entry `GESCHÄTZT`
on the checklist. Statblock names must match `npcs_here` spelling exactly (singular, no
plural drift — the smoke test caught `Dregs` vs `Dreg`).
Optional fields: `faction` (ADR 044) groups NPCs for memory gossip — set it where the book
gives an affiliation (gang, cult, Ecclesiarchy). `goal_de` (ADR 049) makes the NPC an
**agenda NPC** that acts offscreen between scenes — reserve it for the 2–5 NPCs that drive
the plot (one German sentence, what they *want*), never for extras.

### 4. Summary pass
`summary_de`: the ~300-token German GM digest of the whole arc — premise, the party's hook,
the acts' shape, the ending's stakes. Repo precedent (`chemical_burn`): the summary **does**
contain the campaign's hidden truth — the DM needs it every turn to foreshadow correctly —
but wrapped in an explicit secrecy frame: `WAHRHEIT (streng geheim, nur schrittweise als
Andeutung enthüllen): …`. Scene-*level* reveals (who's in which room, what a search finds)
still belong only in that scene's `secrets_de`.

### 5. Self-check + validation + review checklist
1. **Spoiler self-check:** re-read every `description_de`, `guidance_de`, and `summary_de`
   and ask per sentence: "would the DM saying this out loud spoil something the party must
   earn?" If yes → move it to that scene's `secrets_de`.
2. **Vocabulary check:** every `Fertigkeit (Schwierigkeit)` token in `opportunities_de` must
   appear in the vocabulary/ladder from step 0; mismatches → checklist.
3. **Validation:** run
   `uv run python .claude/skills/author-adventure/validate.py <adventure-id>`
   (imports the real `Adventure.load`; checks loadability, scene-id collisions, start_scene,
   dangling `leads_to`, gate integrity, element-id duplicates, statblock coverage) and report
   its output. Fix structural errors; re-run until clean.
4. **Review checklist:** append to the draft output, per scene, what you were unsure about —
   guessed difficulties, merged/split locations, NPCs without statblocks, gates you inferred
   rather than read, vocabulary mismatches. The human review targets these spots instead of
   re-reading everything.

## Wrap-up

Report: file paths written, validation result, checklist. Update `progress.md` per the
session ritual. **Never commit** — `data/adventures/` is untracked by design (bought-book
derivative), and there is nothing to commit.
