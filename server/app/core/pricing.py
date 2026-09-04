"""Model pricing table used to estimate span cost when the SDK does not send one.

Prices are USD per 1M tokens (input, output). Matching is prefix-based on the
model name so dated snapshots ("gpt-4o-2024-08-06") resolve to their family.
"""

# Longest-prefix match wins.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    # Meta (typical hosted pricing)
    "llama-3.3-70b": (0.60, 0.70),
    # Mistral
    "mistral-large": (2.00, 6.00),
    "mistral-small": (0.10, 0.30),
}


def resolve_price(model: str | None) -> tuple[float, float] | None:
    if not model:
        return None
    name = model.lower()
    best: tuple[float, float] | None = None
    best_len = -1
    for prefix, price in PRICES_PER_MTOK.items():
        if name.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best


def estimate_cost(
    model: str | None, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    price = resolve_price(model)
    if price is None:
        return None
    if input_tokens is None and output_tokens is None:
        return None
    in_price, out_price = price
    cost = ((input_tokens or 0) * in_price + (output_tokens or 0) * out_price) / 1_000_000
    return round(cost, 8)
