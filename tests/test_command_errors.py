"""Mistyped arguments must ANSWER in the channel, not vanish into the log.

Before this, ``on_command_error`` logged and returned: ``!uhr neu Wachsamkeit des
Kettenbunds 6`` died converting "des" to the clock size, no clock was created, and the
table got no reply at all — indistinguishable from success until someone checked ``!uhren``.

Pinned here: the usage line is lifted from each command's own docstring, the quoting hint
appears only where quotes actually matter, unknown commands stay silent (Bot A shares the
``!`` prefix), and every real command in the bot yields a usable usage line.
"""

from __future__ import annotations

import asyncio

import pytest
from discord.ext import commands

from dmbot.__main__ import DMBot
from dmbot.voice.command_errors import argument_error_de, usage_de


# --- usage extraction -------------------------------------------------------------------

def test_usage_comes_from_the_docstrings_own_backticked_line() -> None:
    doc = ('`!uhr neu "<Name>" <4|6|8>` — create a clock. The id is derived from the name '
           'and echoed back — it\'s what `<<UHR id>>` and the other subcommands take.')
    # the FIRST backticked run wins; the trailing `<<UHR id>>` mention must not leak in
    assert usage_de("uhr neu", doc, '<name> [size=6]') == '!uhr neu "<Name>" <4|6|8>'


def test_usage_falls_back_to_the_generated_signature() -> None:
    assert usage_de("wrap", "Summarise the session.", "[rest]") == "!wrap [rest]"
    assert usage_de("wrap", None, "[rest]") == "!wrap [rest]"
    assert usage_de("mic", None, "") == "!mic"


def test_usage_ignores_backticks_that_are_not_a_command() -> None:
    doc = "Reads `data/sessions/<id>/state.json`. Usage: `!ort <szenen-id>` to move."
    assert usage_de("ort", doc, "[scene_id]") == "!ort <szenen-id>"


def test_usage_must_name_this_command_not_a_cross_reference() -> None:
    # !szenen's real docstring points at a DIFFERENT command; printing that as the usage
    # would send the player to !ort instead of telling them how to type !szenen.
    doc = "List the loaded adventure's scenes by part — the ids `!ort` accepts."
    assert usage_de("szenen", doc, "") == "!szenen"


def test_usage_name_match_stops_at_a_word_boundary() -> None:
    # a prefix match would let !ort steal !ortmodus's line
    doc = "Controls how far an automatic jump may go. `!ortmodus [verbunden|frei]`."
    assert usage_de("ort", doc, "[scene_id]") == "!ort [scene_id]"
    assert usage_de("ortmodus", doc, "[mode]") == "!ortmodus [verbunden|frei]"


# --- the reply --------------------------------------------------------------------------

def test_reply_names_the_command_and_its_usage() -> None:
    msg = argument_error_de("zeit", "`!zeit [+6h|tag]` — show or advance the clock.", "[arg]")
    assert msg.splitlines() == [
        "⚠ `!zeit` — die Angaben dahinter konnte ich nicht lesen.",
        "Nutzung: `!zeit [+6h|tag]`",
    ]


def test_quoting_hint_only_where_quotes_are_actually_needed() -> None:
    # the trap this whole guard exists for
    with_quotes = argument_error_de("uhr neu", '`!uhr neu "<Name>" <4|6|8>` — create a clock.')
    assert "Anführungszeichen" in with_quotes
    # …and nowhere else: !zeit +6h takes no quoted argument, a hint there is noise
    without = argument_error_de("zeit", "`!zeit [+6h|tag]` — show or advance the clock.")
    assert "Anführungszeichen" not in without


# --- the handler ------------------------------------------------------------------------

class _Ctx:
    """Only what on_command_error touches: a command and a send()."""

    def __init__(self, command) -> None:
        self.command = command
        self.sent: list[str] = []

    async def send(self, content: str = "", **kwargs):
        self.sent.append(content)


def _real(cog, path: str):
    """The real registered command behind e.g. "uhr neu" — a hand-rolled stub would carry the
    wrong ``qualified_name`` and quietly test something else than what runs at the table."""
    head, _, sub = path.partition(" ")
    cmd = next(c for c in cog.__cog_commands__ if c.name == head)
    return next(c for c in cmd.commands if c.name == sub) if sub else cmd


def _handle(ctx, error) -> None:
    """Call the handler unbound — DMBot.__init__ would build a real Bot we don't need."""
    asyncio.run(DMBot.on_command_error(object(), ctx, error))


def test_bad_argument_answers_in_the_channel() -> None:
    # The exact live case: `!uhr neu Wachsamkeit des Kettenbunds 6` fails converting "des"
    # to the clock size, so the body never runs — before this, nothing was posted at all.
    from dmbot.voice.clockcog import ClockCog
    ctx = _Ctx(_real(ClockCog, "uhr neu"))

    _handle(ctx, commands.BadArgument('Converting to "int" failed for parameter "size".'))

    assert len(ctx.sent) == 1
    assert 'Nutzung: `!uhr neu "<Name>" <4|6|8>`' in ctx.sent[0]
    assert "Anführungszeichen" in ctx.sent[0]


@pytest.mark.parametrize("error", [
    commands.BadArgument("nope"),
    commands.TooManyArguments(),
    commands.ExpectedClosingQuoteError('"'),
])
def test_every_user_input_error_shape_answers(error) -> None:
    from dmbot.voice.timecog import TimeCog
    ctx = _Ctx(_real(TimeCog, "frist neu"))
    _handle(ctx, error)
    assert len(ctx.sent) == 1


def test_unknown_command_stays_silent() -> None:
    # Bot A shares the "!" prefix — answering !play would be cross-bot noise (golden rule #5)
    ctx = _Ctx(None)
    _handle(ctx, commands.CommandNotFound())
    assert ctx.sent == []


def test_non_argument_errors_are_logged_not_answered() -> None:
    # An internal failure must not print a usage line that suggests the player typed wrong
    from dmbot.voice.dmcog import DMCog
    ctx = _Ctx(_real(DMCog, "wrap"))
    _handle(ctx, commands.CommandInvokeError(RuntimeError("boom")))
    assert ctx.sent == []


# --- every real command in the bot ------------------------------------------------------

def test_all_registered_commands_yield_a_usable_usage_line() -> None:
    """No command may fall through to an empty or bare hint — walked over the real cogs."""
    from dmbot.voice import (chekhovcog, clockcog, dicecog, dmcog, lorecog, scenecog,
                             timecog, voicecog)

    seen = 0
    for module in (voicecog, dicecog, dmcog, scenecog, lorecog, clockcog, timecog, chekhovcog):
        for obj in vars(module).values():
            cog = getattr(obj, "__cog_commands__", None)
            if cog is None:
                continue
            for cmd in cog:
                for c in [cmd, *getattr(cmd, "commands", [])]:
                    usage = usage_de(c.qualified_name, c.help, c.signature)
                    assert usage.startswith(f"!{c.qualified_name}"), c.qualified_name
                    seen += 1
    assert seen > 30, f"expected the full command surface, walked only {seen}"


def test_the_name_taking_commands_document_the_quoted_form() -> None:
    """The trap that cost the 2026-08-15 evening: !npcmem/!agenda/!damage/!heal match the
    stored name EXACTLY, so a multi-word NSC needs quotes. Their usage lines must show it —
    that is also what makes the error reply print the quoting hint."""
    from dmbot.voice.dicecog import DiceCog

    by_name = {c.name: c for c in DiceCog.__cog_commands__}
    for name in ("npcmem", "agenda", "damage", "heal"):
        cmd = by_name[name]
        assert '"' in usage_de(cmd.qualified_name, cmd.help, cmd.signature), name
        assert "Anführungszeichen" in argument_error_de(
            cmd.qualified_name, cmd.help, cmd.signature
        ), name
