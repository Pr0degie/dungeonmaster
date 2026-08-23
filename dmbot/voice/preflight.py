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
- :func:`check_tts_speaker` — run once at startup, *before* XTTS loads. Same posture for the
  other silent-substitution surface on the voice stack: a ``TTS_SPEAKER`` value that is not an
  XTTS speaker used to degrade to a random voice behind one WARNING line (2026-08-22 run, B13:
  ``TTS_SPEAKER`` held the *device* value ``cuda``, so the whole evening was spoken by whatever
  the fallback happened to be). It is torch-free — it checks the configured name against the
  baked :data:`KNOWN_XTTS_SPEAKERS` set, so it runs at boot while the model is still loading.

**Bumping the stack:** change :data:`KNOWN_GOOD` here, re-run the offline smoke test
(``tests/test_voice_stack.py``) and a live session, then update the verified-stack table in
ADR 006. The three distributions are pinned ``==`` in ``pyproject.toml`` for the same reason.
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Sequence
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


# --- XTTS speaker configuration (B13) -------------------------------------------------
#
# The speaker the DM speaks with when TTS_SPEAKER is empty. Single source of truth: the XTTS
# wrapper imports it from here, so the preflight message and the wrapper's fallback can never
# name two different voices.
DEFAULT_XTTS_SPEAKER = "Dionisio Schuyler"

# The built-in speaker set of ``tts_models/multilingual/multi-dataset/xtts_v2`` (58 timbres).
# Baked so the check runs at boot without importing torch — the *authoritative* list is the
# loaded model's ``.speakers`` (that one is used at load time and by ``!voices``); this one only
# has to be good enough to catch a typo or a device value in TTS_SPEAKER before the table sits
# down. If the model ever ships a different set, the load-time check still has the last word.
# Verified 2026-08-22 against the installed model's own `speakers_xtts.pth` (58 keys, exact match).
KNOWN_XTTS_SPEAKERS: tuple[str, ...] = (
    "Aaron Dreschner", "Abrahan Mack", "Adde Michal", "Alexandra Hisakawa",
    "Alison Dietlinde", "Alma María", "Ana Florence", "Andrew Chipper",
    "Annmarie Nele", "Asya Anara", "Badr Odhiambo", "Baldur Sanjin",
    "Barbora MacLean", "Brenda Stern", "Camilla Holmström", "Chandra MacFarland",
    "Claribel Dervla", "Craig Gutsy", "Daisy Studious", "Damien Black",
    "Damjan Chapman", "Dionisio Schuyler", "Eugenio Mataracı", "Ferran Simen",
    "Filip Traverse", "Gilberto Mathias", "Gitta Nikolina", "Gracie Wise",
    "Henriette Usha", "Ige Behringer", "Ilkin Urbano", "Kazuhiko Atallah",
    "Kumar Dahl", "Lidiya Szekeres", "Lilya Stainthorpe", "Ludvig Milivoj",
    "Luis Moray", "Maja Ruoho", "Marcos Rudaski", "Narelle Moon",
    "Nova Hogarth", "Rosemary Okafor", "Royston Min", "Sofia Hellen",
    "Suad Qasim", "Szofi Granger", "Tammie Ema", "Tammy Grit",
    "Tanja Adelina", "Torcull Diarmuid", "Uta Obando", "Viktor Eka",
    "Viktor Menelaos", "Vjollca Johnnie", "Wulf Carlevaro", "Xavier Hayasaka",
    "Zacharie Aimilios", "Zofija Kendrick",
)

# Values that belong in TTS_DEVICE, not TTS_SPEAKER — the exact B13 mix-up. Naming it in the
# message turns "unknown speaker" into "your two .env keys are swapped".
_DEVICE_LIKE = frozenset({"cpu", "cuda", "cuda:0", "cuda:1", "gpu", "mps", "auto", "xpu"})


def speaker_problem(
    speaker: str, known: Sequence[str] = KNOWN_XTTS_SPEAKERS
) -> str | None:
    """One actionable line describing a bad ``TTS_SPEAKER``, or ``None`` when it is fine.

    Pure (no logging, no I/O) so both callers share one wording: the boot preflight against the
    baked list, and the XTTS wrapper against the loaded model's real speaker list. An empty
    value is *not* a problem — empty is the documented "use the default" setting.
    """
    name = speaker.strip()
    if not name or name in known:
        return None
    parts = [f"TTS_SPEAKER={speaker!r} is not an XTTS speaker"]
    if name.lower() in _DEVICE_LIKE:
        parts.append(
            f"— {name!r} is a TTS_DEVICE value; TTS_SPEAKER and TTS_DEVICE look swapped in .env"
        )
    close = difflib.get_close_matches(name, list(known), n=3, cutoff=0.6)
    if close:
        parts.append("— did you mean: " + " / ".join(close) + "?")
    parts.append(
        f"— XTTS would fall back to {DEFAULT_XTTS_SPEAKER!r}, so the DM voice would be an "
        f"accident. Set TTS_SPEAKER in .env to one of: {', '.join(known)} "
        f"(or leave it empty for {DEFAULT_XTTS_SPEAKER!r}; `!voices` lists the loaded model's set)."
    )
    return " ".join(parts)


def resolve_speaker(speaker: str, available: Sequence[str]) -> str:
    """The speaker XTTS will actually use, given the model's ``available`` names.

    Pure counterpart to :func:`speaker_problem` — the *reporting* is separate from the
    *choice* so the wrapper cannot report one thing and speak another. Order:
    the configured name if the model has it, else :data:`DEFAULT_XTTS_SPEAKER`, else the first
    name the model offers (model-side drift must not leave the DM mute), else ``""``.
    """
    name = speaker.strip()
    if name and name in available:
        return name
    if DEFAULT_XTTS_SPEAKER in available:
        return DEFAULT_XTTS_SPEAKER
    return available[0] if available else ""


def check_tts_speaker(
    speaker: str,
    *,
    engine: str = "xtts",
    known: Sequence[str] | None = None,
) -> list[str]:
    """Boot preflight for ``TTS_SPEAKER``. Returns problems found (empty = configured voice OK).

    Same posture as the other preflights in this repo: it never raises. XTTS loads in a
    background thread minutes before anyone speaks, and a hard abort at boot would take the
    table down for a config typo — so this is the *loud problem* kind of failure, logged at
    ERROR (a level the other checks reserve for "the feature will not work") and returned for
    the caller. ``engine`` is honoured because ``TTS_SPEAKER`` is an XTTS-only knob.
    """
    if engine.strip().lower() != "xtts":
        return []
    problem = speaker_problem(speaker, KNOWN_XTTS_SPEAKERS if known is None else known)
    if problem is None:
        log.info("XTTS speaker preflight OK — %s", speaker.strip() or f"default ({DEFAULT_XTTS_SPEAKER})")
        return []
    log.error("XTTS speaker preflight FAILED: %s", problem)
    return [problem]


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
