"""German reply text for a mistyped command — pure, no discord objects.

Argument errors used to be swallowed: ``on_command_error`` logged them and the table saw
*nothing at all*. That is the worst possible failure at a live table, because the loudest
case looks identical to a working command — ``!uhr neu Wachsamkeit des Kettenbunds 6``
dies converting "des" to the clock size, so no clock is created, no reply is posted, and
the group plays on believing the clock exists (found while writing
``docs/testabend-ablauf.md``).

Every command in this repo opens its docstring with its own usage line in backticks
(``!uhr neu "<Name>" <4|6|8>` — create a clock.``), so the help text a player needs is
already written next to each command; :func:`usage_de` just lifts it out. The fallback is
discord.py's generated signature, which is always available.
"""

from __future__ import annotations

import re

# The leading usage span of a command docstring: the first backticked run that starts with "!".
_USAGE = re.compile(r"`(![^`]+)`")


def usage_de(qualified_name: str, docstring: str | None, signature: str = "") -> str:
    """The usage line for ``qualified_name`` — the docstring's own backticked usage when it
    has one, else discord.py's generated ``!name <arg> [arg]`` signature.

    The span must name THIS command: docstrings cross-reference each other (``!szenen``
    explains "the ids `!ort` accepts"), and printing a different command as the usage would
    send the player somewhere else entirely. A prefix match isn't enough either — ``!ort``
    must not claim ``!ortmodus``'s line — so the name has to end at a word boundary."""
    if docstring:
        for found in _USAGE.finditer(docstring):
            usage = found.group(1).strip()
            rest = usage[len(qualified_name) + 1:]
            if usage.startswith(f"!{qualified_name}") and (not rest or not rest[0].isalnum()):
                return usage
    return f"!{qualified_name} {signature}".strip()


def argument_error_de(qualified_name: str, docstring: str | None, signature: str = "") -> str:
    """The channel reply for a :class:`~discord.ext.commands.UserInputError`.

    Names the command, prints its usage, and adds the quoting hint only when the usage
    actually contains quotes — that is the one trap worth spending a line on, and it would
    be noise under ``!zeit +6h``."""
    usage = usage_de(qualified_name, docstring, signature)
    lines = [
        f"⚠ `!{qualified_name}` — die Angaben dahinter konnte ich nicht lesen.",
        f"Nutzung: `{usage}`",
    ]
    if '"' in usage:
        lines.append('Mehrwortige Angaben gehören in "Anführungszeichen".')
    return "\n".join(lines)
