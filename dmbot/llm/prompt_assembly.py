"""Single owner of the DM system-prompt assembly order (ADR 034 family — pure helpers).

``orchestrator._build_request`` reads the caches and builds the request; this module owns ONLY
the final join, so the prompt ORDER is one pure, order-explicit, testable function — it does not
read or compute any slice itself; the caller passes the already-resolved strings in.

Memory order per docs/conventions.md: persona (core+tone) → recap → JSON state →
who-plays-whom → history. (RAG hits sit between state and the alias hint here; history is added
by the caller, not by this function.)
"""

from __future__ import annotations


class SystemPrompt(str):
    """The assembled system prompt, a plain ``str`` everywhere, that also knows its stable head.

    ``stable`` is the leading part that stays byte-identical from turn to turn (persona, and the
    recap until the next auto-recap). Ollama and every other reader see the whole string, unchanged.
    The Claude client sends only ``stable`` as the system prompt and moves the rest, same text and
    same order, to the front of the user prompt: the CLI caches the system prompt as one block, so
    one changed state line used to make every turn a cache miss (D142, ADR 061 amendment
    2026-11-14). Any str operation (``+``, slicing) returns a plain ``str`` without the head.
    """

    stable: str

    def __new__(cls, text: str, stable: str = "") -> SystemPrompt:
        obj = super().__new__(cls, text)
        obj.stable = stable if text.startswith(stable) else ""
        return obj


def assemble_system_prompt(
    persona: str,
    *,
    recap: str | None = None,
    adventure: str | None = None,
    state_summary: str | None = None,
    npc_memory: str | None = None,
    rag: str | None = None,
    alias_hint: str | None = None,
) -> SystemPrompt:
    """Join the present prompt slices into one system prompt, in the fixed memory order
    ``persona → recap (wrapped) → adventure → state_summary → npc_memory → rag → alias_hint``.

    Each optional slice is included ONLY when truthy — both ``None`` and ``""`` are skipped.
    Slices are separated by exactly
    one blank line (``"\\n\\n"``). ``recap`` is wrapped in the German "Was bisher geschah" header;
    every other slice is appended verbatim. ``npc_memory`` (ADR 044) sits right after the hard
    state it colours, before the retrieved rulebook text.

    The result is a :class:`SystemPrompt` whose ``stable`` head is ``persona`` + recap: everything
    after it changes from turn to turn (the scene card with its guidance cadence, state, RAG).
    """
    parts = [persona]
    if recap:
        parts.append(
            "## Was bisher geschah "
            "(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)\n"
            f"{recap}"
        )
    stable = "\n\n".join(parts)
    if adventure:
        parts.append(adventure)
    if state_summary:
        parts.append(state_summary)
    if npc_memory:
        parts.append(npc_memory)
    if rag:
        parts.append(rag)
    if alias_hint:
        parts.append(alias_hint)
    return SystemPrompt("\n\n".join(parts), stable=stable)
