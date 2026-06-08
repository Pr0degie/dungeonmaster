"""Unit test for the Ollama preflight's pure model-name matching (the network call itself is
ops glue, verified live). Mirrors the tag/no-tag reality of `ollama list`."""

from dmbot.llm.preflight import _model_available


def test_exact_match():
    assert _model_available("mistral-nemo:latest", {"mistral-nemo:latest"})


def test_config_default_matches_latest_tag():
    # The config default is the bare name; `ollama list` reports it with `:latest`.
    assert _model_available("mistral-nemo", {"mistral-nemo:latest", "nomic-embed-text:latest"})


def test_tagged_config_matches_bare():
    assert _model_available("gemma3:12b", {"gemma3:12b"})


def test_missing_model():
    assert not _model_available("mistral-nemo", {"gemma3:12b", "qwen3.5:9b"})


def test_empty():
    assert not _model_available("mistral-nemo", set())
