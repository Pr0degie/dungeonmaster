# ADR 064 — Throw GIFs stored once in Discord, clicks only point at them

- **Status:** Accepted (built 2026-10-30; live-unverified — the next table test is the check)
- **Date:** 2026-10-30
- **Refs:** decision rows **D128** (throw animation) and **D129** (this) in `docs/decision-log.md`;
  `architecture.md` §3 (dice thumbnails row). Presentation only — golden rule #2 untouched.

## Context

D128 shows a throw GIF between the 🎲 click and the result. At the table (2026-10-30) the wait
before the GIF appeared was the complaint. The bot's own log measured one roll:
`built 578 ms, in Discord 1843 ms after the click (297 KiB)`, so ~1.2 s of the wait was the
message edit that carries the GIF as an attachment (upload plus Discord's processing), more than
the rendering. Shrinking the GIF (604 → 304 KB) had already been done. Tobi offered `#botcommands`
as a place the bot may fill with files, once.

## Decision

1. **Store the flight once.** A flight-only GIF per (trajectory, palette) — 25 × red/gold/green
   = 75, ~21 MB — without the landing, ending on a blank die face, playing once (no loop). One GIF
   serves every result, so 75 files cover every roll (a GIF per result would be 7500).
2. **Storage channel `DM_DICE_ASSET_CHANNEL`** (name like `botcommands`, or an id). On `on_ready`
   the bot uploads what is missing, ten per message (~8 messages), and keeps the message ids in
   `data/dice/anim/assets.json`. Later starts **fetch** those messages instead of uploading.
   Discord's attachment links expire after ~24 h; fetching the messages again (every 6 h, lazily)
   gives fresh ones. A deleted storage message → its GIFs are uploaded again.
3. **Click:** edit 1 only points the embed image at the stored link (no attachment). The result
   picture is still **uploaded** in edit 2, so the message that stays in the history has a real
   attachment and never depends on an expiring link. Edit 2 starts early by the learnt upload time
   (moving average of the last edits, start 1.0 s, bounded 0.2–3 s) plus `CLIENT_START_S` (0.3 s,
   clients start the GIF a moment after the edit), so the result lands as the flight ends.
4. **Fail-open:** no channel configured or found, no permission, upload failed, or not stored yet
   → the D128 per-roll upload path, unchanged. The seed choice stays cosmetic (`_THROW_RNG`).

## Alternatives considered

- **Only shrink further** (16 colours, smaller frames): saves part of the upload, not Discord's
  fixed processing time for an attachment edit. Kept as the fallback path's state.
- **Store the result pictures too and point at them in edit 2:** the swap would be faster still,
  but the message left in the history would hold an expiring link — old rolls could lose their
  picture after a day. Rejected; the early-start upload keeps the history safe.
- **One GIF per result, stored:** 7500 files. Rejected.

## Consequences

- Expected: click → GIF ~0.5 s instead of ~1.8 s; the landing is now the swap to the result
  picture instead of frames inside the GIF. Whether that swap lines up well at the table, and
  whether Discord honours "play once", is the open live check.
- `#botcommands` gets ~8 bot messages with attachments; deleting them only costs a re-upload.
- Changing the frame plan bumps `FRAME_SET_VERSION`, which renames the stored files, so the next
  start uploads the new set (old messages can be deleted by hand).

## Amendment 2026-10-31 — at the table

- Edit 1 swaps **only the picture**: an earlier version also cleared the message text, so the box jumped
  a line while it reloaded. The box now holds only the picture; "Zielwert ≤37" and later the result line
  are the message text (still an embed, because only an embed can point at a stored link).
- Posting the throw as a new message and deleting the old one 1.5 s later (no blank picture while clients
  load the GIF) was built and compared side by side (`!wurfvergleich`); Tobi kept the in-place swap and
  the variant was removed again. The short load gap is accepted (lesson `discord-image-swaps-reload`).
- GIFs use 16 colours (~266 KB) and their names carry `gif_version()` (frame-set version + colours), so a
  change re-uploads the set once; the old messages in the channel are forgotten, not deleted.
- Live: the first start uploaded 75/75 in ~55 s; later starts only re-fetch (~6 s); a click had the GIF
  in Discord ~0.3 s after the click.
