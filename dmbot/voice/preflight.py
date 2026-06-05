"""Voice-stack preflight checks — future-proofing the project's most fragile surface.

The voice receive path is version-sensitive in two ways (CLAUDE.md, ADR 006):

1. The DAVE/E2EE decrypt reaches into a **discord.py internal**
   (``voice_client._connection.dave_session``). That attribute is undocumented and can be
   renamed or removed on any discord.py upgrade.
2. ``discord-ext-voice-recv`` is an **alpha** whose sink callback signature
   (``wants_opus`` / ``write`` / ``VoiceData`` fields) may change.

A break in either does NOT raise — it silently produces a *garbage transcript*. These
checks convert that into a loud, early signal:

- :func:`check_static` — run once at startup (no Discord connection needed). Verifies the
  installed versions against the known-good set and asserts the attribute paths the sink
  relies on still exist. Returns a list of human-readable problems (empty = all good) and
  logs each as a WARNING; it never raises, so a drift degrades to a warning, not a crash.
- :func:`check_dave_session` — run right after joining a channel. Confirms the
  ``dave_session`` handle is reachable on the live voice client.

**Bumping the stack:** change :data:`KNOWN_GOOD` here, re-run the offline smoke test
(``tests/test_voice_stack.py``) and a live session, then update the verified-stack table in
ADR 006. The three distributions are pinned ``==`` in ``pyproject.toml`` for the same reason.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

log = logging.getLogger(__name__)

# The exact distribution versions this voice code was verified against (live, 2026-06-04).
# Keys are PyPI distribution names (as in pyproject.toml / importlib.metadata), not import
# names. Keep in lockstep with the `==` pins in pyproject.toml and the table in ADR 006.
KNOWN_GOOD: dict[str, str] = {
    "discord.py": "2.7.1",
    "discord-ext-voice-recv": "0.5.2a179",
    "davey": "0.1.5",
}


def check_static() -> list[str]:
    """Verify the voice stack at startup (no Discord connection). Returns problems found.

    Two families of check, both non-fatal (logged as warnings, returned for the caller):
    version drift away from :data:`KNOWN_GOOD`, and missing attribute paths the sink relies
    on. An empty list means the stack matches what the code was written against.
    """
    problems: list[str] = []

    # 1) Version drift — a different version may still work, but it is *unverified*, and this
    #    is exactly where silent breakage lives. Warn so an upgrade is a conscious act.
    for dist, want in KNOWN_GOOD.items():
        try:
            have = version(dist)
        except PackageNotFoundError:
            problems.append(f"{dist} is not installed (expected {want})")
            continue
        if have != want:
            problems.append(
                f"{dist} {have} != verified {want} — voice receive is UNVERIFIED on this "
                f"version; re-check ADR 006 (dave_session) + the voice-recv sink signature"
            )

    # 2) Attribute paths the sink depends on. Import lazily so this module stays importable
    #    even if the libs are half-broken (we want to report, not crash on import).
    try:
        from discord.ext.voice_recv import AudioSink, SilenceGeneratorSink, VoiceData

        if not hasattr(AudioSink, "wants_opus"):
            problems.append("voice_recv.AudioSink lost .wants_opus — sink API changed")
        if not hasattr(AudioSink, "write"):
            problems.append("voice_recv.AudioSink lost .write — sink API changed")
        for field in ("opus", "pcm", "source"):
            if not hasattr(VoiceData, field):
                problems.append(
                    f"voice_recv.VoiceData lost .{field} — frame shape changed (ADR 006)"
                )
        _ = SilenceGeneratorSink  # presence asserted by the import above
    except Exception as exc:  # ImportError or worse — report, don't crash startup
        problems.append(f"could not import the voice-recv sink API: {exc!r}")

    try:
        import davey

        if not hasattr(davey, "MediaType") or not hasattr(davey.MediaType, "audio"):
            problems.append("davey.MediaType.audio missing — DAVE decrypt API changed")
    except Exception as exc:
        problems.append(f"could not import davey (DAVE/E2EE): {exc!r}")

    if problems:
        log.warning(
            "voice-stack preflight found %d issue(s) — receive may silently misbehave:",
            len(problems),
        )
        for p in problems:
            log.warning("  ⚠ %s", p)
    else:
        log.info("voice-stack preflight OK (versions + sink API match the verified set)")
    return problems


def check_dave_session(voice_client) -> bool:
    """After joining: is the ``_connection.dave_session`` path (ADR 006) still reachable?

    Returns True if the handle is present. A False here means the live decrypt path is broken
    even if :func:`check_static` passed (e.g. discord.py kept the version but moved the
    internal) — and since DAVE is effectively always on (Discord rejects opt-out, close 4017),
    that would mean garbage audio. The runtime decrypt in ``recv.py`` has its own loud
    fallback; this is the early, explicit check at join time.
    """
    conn = getattr(voice_client, "_connection", None)
    if conn is None:
        log.warning(
            "voice client has no `_connection` (discord.py internal moved?) — DAVE decrypt "
            "path unreachable; transcripts will be garbage if the call is E2EE (ADR 006)"
        )
        return False
    if not hasattr(conn, "dave_session"):
        log.warning(
            "`_connection.dave_session` is gone (discord.py internal renamed?) — DAVE "
            "decrypt path unreachable; E2EE audio will not decode (ADR 006)"
        )
        return False
    return True
