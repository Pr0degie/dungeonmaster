---
name: character-build
description: Use when a player's Imperium Maledictum character JSON comes in and needs validating + deploying, when building a new IM character from scratch, or when backfilling backstory onto an existing sheet. Validates budgets/formulas/psyker powers/augmetics against the active profile, writes data/party/<player>.json, generates the PDF sheet, and proposes (confirm first) the merge into the session characters.json + aliases.
---

# Build / validate / deploy a character (SL side)

The player-facing self-service interview already exists in `docs/character-creation-prompt.md`
(point-buy + psyker + augmetics → one JSON). This skill is the **game-master side**: take a
character in, make it rules-correct against the active profile, and deploy it. Never trust the
numbers blind — recompute them.

Sources of truth (read, don't hardcode — they can drift):
- **Profile** `data/systems/imperium_maledictum.json` — point-buy budget, origin table, weapon
  list, psyker catalog (`psyker.powers`), augmetics catalog (`augmetics`).
- **Rules** `docs/character-creation-prompt.md` Teil 2 (the build rules) — kept in sync with
  `docs/how-to-create-a-character.html`.
- **Schema** `docs/character-template.json`; the code that actually consumes it is
  `Character.from_dict` in `dmbot/rules/characters.py` (mechanical fields read; everything else
  lands harmlessly in `raw`).

## Three entry modes (all converge on Validate → Deploy)

- **(A) Incoming JSON** — the player ran the self-service prompt and sent a JSON. *Main case.*
- **(B) From scratch** — no JSON: run the interview (Teil 1 of `character-creation-prompt.md`,
  small batches, German, grimdark), then build the JSON yourself.
- **(C) Backstory backfill** — stats already exist, only narrative fields (goals/connections/
  age/...) missing → fill just those; skip the budget rebuild.

## Validate (the core — recompute every number)

Fix on failure, or flag it back to the player; summarize the result in the JSON's `_note`.

- **Characteristics:** exactly **90** points distributed over the 9 stats, each **+4…+18**
  *before* origin (start 20 → 24–38); then origin **+5 fixed / +5 chosen** added correctly per
  the origin table. Bonus = tens digit.
- **Skills:** ≤ **6** increases total, **max 2** per skill; endwert = ruling characteristic +
  increases×5. (Psyker package skills below are separate from these 6.)
- **Wounds:** `StrB + 2×TghB + WilB`; set `wounds == max_wounds`.
- **Psyker (if `psyker: true`):** `Psi-Meisterschaft = Wil+10`, `Disziplin (Psi) = Wil+5`;
  **exactly 5** `known_powers`, each an **exact key** in the profile psyker catalog (English
  names), **Smite mandatory**; a `talents` entry `Psioniker` present.
- **Augmetics:** each name an exact key in the profile augmetics catalog; count ≤ **Toughness
  Bonus** (soft limit).
- **Weapons:** `damage`/`test` match the profile weapon list (test = Nahkampf for melee,
  Fernkampf for ranged).

## Deploy

1. **Write** `data/party/<player>.json` (committed — `.gitignore` allowlist; one JSON per
   player). Keep German text, grimdark tone.
2. **Generate the sheet:**
   `uv run python tools/fill_character_sheet.py data/party/<player>.json --out <dir>`
   → the PDF is a bought-sheet derivative, stays **local / git-ignored**. Send it to the player.
3. **Session merge — confirm before touching the live file.** The session
   `data/sessions/<id>/characters.json` is what the bot actually loads, so do NOT write it
   silently. Show the planned change first:
   - target channel id (default circlejerk `1343673766487654464`; **a different channel needs
     the file copied into its own `<id>/` folder**),
   - the `characters[]` entry and the new **alias** (Discord/display name → character name),
   - whether `state.json` / `recap.md` must be cleared (yes when replacing the party, so the
     first `!join` seeds fresh from the new sheet).
   Apply only after the user's OK.
4. **Sanity + commit:** `uv run --with pytest python -m pytest` (schema loads via
   `Character.from_dict`); commit per repo norm (scoped, imperative).

## Gotchas

- Catalog names must match the profile **exactly** — a typo'd power/augmetic key silently drops
  it from the `<<MANIFEST>>` flow / effect resolution. This is the #1 failure.
- German skill/characteristic names must match the German edition; flag any you can't confirm.
- `player` becomes the alias — without it the DM can't map a Discord speaker to their character.
