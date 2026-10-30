# Time the Discord side before optimising the bot side

**A message edit that carries an attachment costs ~1 s at Discord no matter how fast the bot
renders — log a timestamp around the edit before tuning anything local.**

## What happened

The dice throw GIF (D128) felt slow after the click. Two rounds went into the bot side first:
pre-rendering the frame pool and preparing the throw at post time (render 3.3 s → 0.5 s), then
32 colours and fewer frames (604 → 304 KB). Only the log line added in the second round —
`🎲 throw gif: built 578 ms, in Discord 1843 ms after the click (297 KiB)` — showed that ~1.2 s
of the wait was the edit with the attachment itself. The fix for that part was structural:
upload the GIFs once and let the click only point at them (ADR 064).

## The correction

For anything that "takes long in Discord", first add one log line with the local time and the
time the Discord call returned (`time.monotonic()` around the `send`/`edit`). Then optimise the
larger share. Attachments are the expensive part; an edit that only points at an existing link
or changes text is cheap.
