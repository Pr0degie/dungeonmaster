"""Pure tests for the DM system-prompt assembler (no LLM, fixed strings).

``assemble_system_prompt`` owns the prompt slice order extracted out of
``orchestrator._build_request``. These tests pin the order, the recap header wrapping, the
truthy-only inclusion (``None`` and ``""`` both skipped), and the exactly-two-newline separator
between any two present slices.
"""

from __future__ import annotations

from dmbot.llm.prompt_assembly import assemble_system_prompt

# The exact German recap header, byte-for-byte as it appears in the assembler / old orchestrator.
_RECAP_HEADER = (
    "## Was bisher geschah "
    "(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)"
)


def test_persona_only_returns_just_persona() -> None:
    assert assemble_system_prompt("PERSONA") == "PERSONA"


def test_persona_only_with_all_slices_none_returns_just_persona() -> None:
    # Every optional slice defaults to None → identical to persona-only.
    assert (
        assemble_system_prompt(
            "PERSONA",
            recap=None,
            adventure=None,
            state_summary=None,
            rag=None,
            alias_hint=None,
        )
        == "PERSONA"
    )


def test_persona_plus_recap_wraps_header_and_blank_line_separator() -> None:
    result = assemble_system_prompt("PERSONA", recap="RECAP")
    # Fully-spelled-out expected string: persona, blank line, wrapped header, then the recap body
    # on its own line (single newline inside the wrap, two newlines between slices).
    expected = (
        "PERSONA\n\n"
        "## Was bisher geschah "
        "(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)\n"
        "RECAP"
    )
    assert result == expected
    # The header appears and is separated from the persona by exactly one blank line.
    assert _RECAP_HEADER in result
    assert "PERSONA\n\n## Was bisher geschah" in result


def test_all_six_slices_exact_order_and_string() -> None:
    result = assemble_system_prompt(
        "PERSONA",
        recap="RECAP",
        adventure="ADVENTURE",
        state_summary="STATE",
        rag="RAG",
        alias_hint="HINT",
    )
    expected = (
        "PERSONA\n\n"
        "## Was bisher geschah "
        "(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)\n"
        "RECAP\n\n"
        "ADVENTURE\n\n"
        "STATE\n\n"
        "RAG\n\n"
        "HINT"
    )
    assert result == expected


def test_none_slice_and_empty_string_slice_are_both_skipped() -> None:
    # adventure=None and rag="" must both be dropped, leaving no doubled blank line.
    result = assemble_system_prompt(
        "PERSONA",
        recap="RECAP",
        adventure=None,
        state_summary="STATE",
        rag="",
        alias_hint="HINT",
    )
    expected = (
        "PERSONA\n\n"
        "## Was bisher geschah "
        "(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)\n"
        "RECAP\n\n"
        "STATE\n\n"
        "HINT"
    )
    assert result == expected
    # No tripled newline anywhere (a doubled blank line would be "\n\n\n").
    assert "\n\n\n" not in result


def test_separator_between_two_present_slices_is_exactly_two_newlines() -> None:
    # state_summary + rag only: persona, then state, then rag — separators are exactly "\n\n".
    result = assemble_system_prompt("PERSONA", state_summary="STATE", rag="RAG")
    assert result == "PERSONA\n\nSTATE\n\nRAG"
    # Every join is exactly two newlines (no single \n between slices, no triple).
    assert "PERSONA\n\nSTATE" in result
    assert "STATE\n\nRAG" in result
    assert "\n\n\n" not in result
