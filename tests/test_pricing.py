import json

import pytest

from llmstat import pricing
from llmstat.pricing import cost_for, is_known


def test_exact_match_cost():
    # gpt-5.5-pro is 2.50 in / 15.00 out per 1M tokens.
    assert cost_for("gpt-5.5-pro", 1_000_000, 0) == pytest.approx(2.50)
    assert cost_for("gpt-5.5-pro", 0, 1_000_000) == pytest.approx(15.00)
    assert cost_for("gpt-5.5-pro", 1_000_000, 1_000_000) == pytest.approx(17.50)


def test_provider_prefix_is_stripped():
    # "openrouter/deepseek-v4-pro" should resolve like "deepseek-v4-pro".
    bare = cost_for("deepseek-v4-pro", 1000, 1000)
    assert cost_for("openrouter/deepseek-v4-pro", 1000, 1000) == bare


def test_longest_prefix_match_for_dated_variants():
    # A dated/versioned suffix should still resolve to the base model price.
    assert is_known("gpt-5.5-pro-2026-06-01")
    assert cost_for("gpt-5.5-pro-2026-06-01", 1_000_000, 0) == pytest.approx(2.50)


def test_unknown_model_is_free_not_an_error():
    assert cost_for("totally-made-up-model", 1000, 1000) == 0.0
    assert not is_known("totally-made-up-model")


def test_user_override_takes_precedence(tmp_path, monkeypatch):
    override = tmp_path / "pricing.json"
    override.write_text(json.dumps({"my-local-llama": [0.0, 0.0], "gpt-5.5-pro": [1.0, 1.0]}))
    monkeypatch.setattr(pricing, "_USER_PRICING_PATH", str(override))

    # Self-hosted model the user priced at zero.
    assert is_known("my-local-llama")
    assert cost_for("my-local-llama", 1_000_000, 1_000_000) == 0.0
    # User override beats the built-in default.
    assert cost_for("gpt-5.5-pro", 1_000_000, 0) == pytest.approx(1.0)


def test_malformed_override_is_ignored(tmp_path, monkeypatch):
    bad = tmp_path / "pricing.json"
    bad.write_text("{ this is not valid json")
    monkeypatch.setattr(pricing, "_USER_PRICING_PATH", str(bad))
    # Falls back to defaults without raising.
    assert cost_for("gpt-5.5-pro", 1_000_000, 0) == pytest.approx(2.50)
