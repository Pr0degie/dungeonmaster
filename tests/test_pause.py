"""Unit tests for the pause UI's pure pieces — the status embed and the button label/style sync.
The Esc listener + rich animation + the cog wiring are live-tested (terminal + Discord)."""

import discord

from dmbot.discord_ui.pause import PauseToggleView, pause_embed


def test_pause_embed_states_differ():
    paused = pause_embed(True)
    running = pause_embed(False)
    assert "pausiert" in paused.title.lower()
    assert "läuft" in running.title.lower()
    assert paused.color != running.color  # orange vs green — visually distinct


async def _noop_toggle() -> bool:  # the cog passes a coroutine; unused here
    return True


def test_button_label_reflects_state():
    view = PauseToggleView(_noop_toggle, paused=False)
    assert "Pause" in view._button.label
    assert view._button.style == discord.ButtonStyle.secondary
    view._sync(True)
    assert "Fortsetzen" in view._button.label
    assert view._button.style == discord.ButtonStyle.success
