# Two answers delivered sentence by sentence are spoken into each other

**What happened (2026-11-27, D152):** the streaming pipeline posts one WAV per sentence to the
bridge, and the bridge plays WAVs in arrival order. Whenever a second turn started while the
first still played — a roll pressed during playback (by design since D40), two mic releases a
second apart, two rolls of one turn — the sentences of both answers alternated. It had been so
since the streaming pipeline existed; with two players it was rare enough to be taken for
"background babble", with three it happened three times in twenty minutes.

**The correction:** concurrency of turns is three separate questions, each with its own guard:
who may call the narration model (one at a time), who may speak (whole answers, in generation
order), and when a turn with several dice buttons is narrated (once, after its last roll).
A blocking `/speak` call orders sentences of one answer, not answers.

**How to apply:** any new path that speaks an answer goes through the delivery pipeline's
speaking order; any new path that calls the narration model takes `DeliveryPipeline.narrating()`.
In a log, two `🪵 LLM roh` lines closer together than the first one's `⏱ LLM` duration, or a
`bridge_wait=` far above `wav=`, is this pattern.
