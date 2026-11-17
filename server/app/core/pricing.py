"""Model pricing used to estimate span cost when the SDK does not send one.

Prices are USD per 1M tokens. Matching is prefix-based on the model name so
dated snapshots ("gpt-4o-2024-08-06") resolve to their family; the longest
prefix wins. Projects can override or extend the table (see ModelPrice).

Token convention: `input_tokens` is *uncached* input. Cache reads and cache
writes are counted separately and priced at their own rates.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float | None = None  # default: 0.1 x input
    cache_write: float | None = None  # default: 1.25 x input (5-minute TTL)

    @property
    def cache_read_rate(self) -> float:
        return self.cache_read if self.cache_read is not None else self.input * 0.1

    @property
    def cache_write_rate(self) -> float:
        return self.cache_write if self.cache_write is not None else self.input * 1.25


BUILTIN_PRICES: dict[str, Price] = {
    # Anthropic (first-party API rates)
    "claude-fable-5-2": Price(8.00, 40.00, cache_read=0.20),
    "claude-mythos-5-2": Price(8.00, 40.00, cache_read=0.20),
    "claude-fable-5-1": Price(10.00, 50.00, cache_read=0.25),
    "claude-mythos-5-1": Price(10.00, 50.00, cache_read=0.25),
    "claude-fable-5": Price(10.00, 50.00),
    "claude-mythos-5": Price(10.00, 50.00),
    "claude-opus-5-5": Price(4.00, 20.00, cache_read=0.20),
    "claude-opus-5": Price(5.00, 25.00),
    "claude-opus-4-8": Price(5.00, 25.00),
    "claude-opus-4-7": Price(5.00, 25.00),
    "claude-opus-4-6": Price(5.00, 25.00),
    "claude-sonnet-5-5": Price(2.00, 10.00, cache_read=0.10),
    "claude-sonnet-5": Price(2.00, 10.00),
    "claude-sonnet-4-6": Price(3.00, 15.00),
    "claude-sonnet-4-5": Price(3.00, 15.00),
    "claude-haiku-5-5": Price(0.10, 0.50),
    "claude-haiku-4-5": Price(1.00, 5.00),
    # OpenAI
    "gpt-4o-mini": Price(0.15, 0.60, cache_read=0.075, cache_write=0.15),
    "gpt-4o": Price(2.50, 10.00, cache_read=1.25, cache_write=2.50),
    "gpt-4.1-mini": Price(0.40, 1.60, cache_read=0.10, cache_write=0.40),
    "gpt-4.1": Price(2.00, 8.00, cache_read=0.50, cache_write=2.00),
    "o3-mini": Price(1.10, 4.40, cache_read=0.55, cache_write=1.10),
    "o3": Price(2.00, 8.00, cache_read=0.50, cache_write=2.00),
    # Meta (typical hosted pricing)
    "llama-3.3-70b": Price(0.60, 0.70),
    # Mistral
    "mistral-large": Price(2.00, 6.00),
    "mistral-small": Price(0.10, 0.30),
}

PriceTable = dict[str, Price]


def build_price_table(overrides: Iterable | None = None) -> PriceTable:
    """Built-in prices with per-project ModelPrice rows layered on top."""
    table = dict(BUILTIN_PRICES)
    for row in overrides or ():
        table[row.model_prefix.lower()] = Price(
            row.input_per_mtok,
            row.output_per_mtok,
            cache_read=row.cache_read_per_mtok,
            cache_write=row.cache_write_per_mtok,
        )
    return table


def resolve_price(model: str | None, table: PriceTable | None = None) -> Price | None:
    if not model:
        return None
    name = model.lower()
    best: Price | None = None
    best_len = -1
    for prefix, price in (table or BUILTIN_PRICES).items():
        if name.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best


def estimate_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
    table: PriceTable | None = None,
) -> float | None:
    price = resolve_price(model, table)
    if price is None:
        return None
    counts = (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
    if all(c is None for c in counts):
        return None
    cost = (
        (input_tokens or 0) * price.input
        + (output_tokens or 0) * price.output
        + (cache_read_tokens or 0) * price.cache_read_rate
        + (cache_creation_tokens or 0) * price.cache_write_rate
    ) / 1_000_000
    return round(cost, 8)
