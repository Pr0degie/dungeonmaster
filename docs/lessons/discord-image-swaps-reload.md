# Discord image swaps reload — change only the picture, and keep the layout still

**Editing a message's picture blanks it until every client has downloaded the new file; anything else
that changes in the same edit (text, a box that collapses) makes the jump visible. Change only the
picture, keep the files small, and accept the short gap — a "post new, delete old" workaround was
judged worse at the table.**

## What happened

The dice throw (D128) swaps the target picture for a GIF. Tobi saw "the picture goes away for a moment"
(2026-10-31). Rounds that followed:

- The edit also cleared `content` ("🎲 Probe angefordert:"), so the box moved up a line while reloading
  — removed; the throw edit now passes only `embed`/`attachments`.
- The embed carried text and a coloured side bar, re-rendered on every edit — now a picture-only box,
  the words are the message text.
- Posting the GIF as a new message and deleting the old one after 1.5 s kept a picture on screen, but the
  message jumped up on delete; compared side by side (`!wurfvergleich`), Tobi preferred the swap.
- Smaller files shorten the gap: PNG 600 px / 64 colours (~42 KB), GIF 16 colours (~266 KB), no visible
  change at Discord's ~400 px.

## The correction

For anything Discord displays and later edits: change exactly one thing per edit, never the text next to
a picture you swap; keep files as small as the displayed size allows; a plain attachment can't point at
a stored link (ADR 064 needs an embed). Before building a workaround for a visual effect, let Tobi
compare it live — he decides by eye, and the "cleaner" fix lost.
