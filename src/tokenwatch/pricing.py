"""Model pricing table (USD per 1M tokens).

Prices are best-effort and easy to extend — edit this dict or override per-model
with a `~/.tokenwatch/pricing.json` file. We never hardcode anything we can't
let the user correct, because pricing changes constantly.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional, Tuple

# (input_per_1m, output_per_1m) in USD.
_DEFAULT_PRICING: Dict[str, Tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    # Open models (typical hosted pricing)
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "llama-3.3-70b": (0.59, 0.79),
    "qwen-2.5-72b": (0.40, 0.40),
}

_USER_PRICING_PATH = os.path.expanduser("~/.tokenwatch/pricing.json")


def _load_user_pricing() -> Dict[str, Tuple[float, float]]:
    if not os.path.exists(_USER_PRICING_PATH):
        return {}
    try:
        with open(_USER_PRICING_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: (float(v[0]), float(v[1])) for k, v in raw.items()}
    except (ValueError, KeyError, TypeError, OSError):
        return {}


def _match(model: str) -> Optional[Tuple[float, float]]:
    """Resolve a model name to a price, tolerating version suffixes/prefixes."""
    table = {**_DEFAULT_PRICING, **_load_user_pricing()}
    if model in table:
        return table[model]
    # Strip common provider prefixes like "openai/" or "anthropic/".
    bare = model.split("/")[-1]
    if bare in table:
        return table[bare]
    # Longest-prefix match handles dated variants, e.g. gpt-4o-2024-08-06.
    best = None
    for key in table:
        if bare.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return table[best] if best else None


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost for a call, or 0.0 if the model is unknown."""
    price = _match(model or "")
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate


def is_known(model: str) -> bool:
    return _match(model or "") is not None
