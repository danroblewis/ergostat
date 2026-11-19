"""What Claude's tokens cost, by model: used only when a run's tokens are known and its dollars are not (an AI session
that reported its usage without ``total_cost_usd``), and the cost it gives is marked ``estimated``. Claude Code's own
``total_cost_usd`` is always preferred.

Dollars per million tokens, Anthropic's first-party API list prices (2026-11); cache writes at 1.25 times the input
price (the 5-minute cache) or twice it (those kept an hour, ``cache_write_1h``, which Claude Code uses), cache reads at
the price given or a tenth of the input price. A model is found by
its id or the family word in it (``claude-haiku-5-5``, ``haiku``); one not found is not priced (``None``)."""

from __future__ import annotations

# model id prefix → (input, output, cache read) dollars per million tokens; cache read None: a tenth of input
PRICES: dict[str, tuple[float, float, float | None]] = {
    "claude-fable-5-2": (8.0, 40.0, 0.20),
    "claude-mythos-5-2": (8.0, 40.0, 0.20),
    "claude-fable-5-1": (10.0, 50.0, None),
    "claude-mythos-5-1": (10.0, 50.0, None),
    "claude-fable-5": (10.0, 50.0, None),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, None),
    "claude-opus-4-8": (5.0, 25.0, None),
    "claude-opus-4-7": (5.0, 25.0, None),
    "claude-opus-4-6": (5.0, 25.0, None),
    "claude-opus-4-5": (5.0, 25.0, None),
    "claude-opus-4-1": (15.0, 75.0, None),
    "claude-opus-4": (15.0, 75.0, None),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10),
    "claude-sonnet-5": (2.0, 10.0, None),
    "claude-sonnet-4": (3.0, 15.0, None),           # 4, 4.5 and 4.6
    "claude-haiku-5-5": (0.10, 0.50, None),
    "claude-haiku-4-5": (1.0, 5.0, None),
    "claude-3-5-haiku": (0.80, 4.0, None),
}
# a bare family word (``--model haiku``) means the current model of that family
FAMILIES = {"fable": "claude-fable-5-2", "mythos": "claude-mythos-5-2", "opus": "claude-opus-5-5",
            "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
CACHE_WRITE = 1.25
CACHE_WRITE_1H = 2.0


def price_of(model: str | None) -> tuple[float, float, float] | None:
    """(input, output, cache read) dollars per million tokens for a model id or family word, or None."""
    if not model:
        return None
    m = model.strip().lower().removeprefix("anthropic.").split("@")[0].split("[")[0]
    m = FAMILIES.get(m, m)
    for key in sorted(PRICES, key=len, reverse=True):    # the longest prefix: claude-opus-5-5 before claude-opus-5
        if m.startswith(key):
            i, o, r = PRICES[key]
            return i, o, r if r is not None else i / 10
    return None


def estimate(model: str | None, tokens: dict) -> float | None:
    """Dollars for these tokens (``input``, ``output``, ``cache_read``, ``cache_write``, and of the writes those kept an
    hour, ``cache_write_1h``) on this model; None when the model is not priced."""
    p = price_of(model)
    if p is None:
        return None
    i, o, r = p
    w = float(tokens.get("cache_write") or 0)
    hour = min(w, float(tokens.get("cache_write_1h") or 0))
    return (float(tokens.get("input") or 0) * i + float(tokens.get("output") or 0) * o
            + float(tokens.get("cache_read") or 0) * r + (w - hour) * i * CACHE_WRITE + hour * i * CACHE_WRITE_1H) / 1e6
