"""W3C Trace Context style identifiers (same format OpenTelemetry uses)."""

from __future__ import annotations

import secrets


def new_trace_id() -> str:
    """128-bit lowercase hex trace id."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """64-bit lowercase hex span id."""
    return secrets.token_hex(8)
