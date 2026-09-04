
from __future__ import annotations

import json
from typing import Any

MAX_VALUE_BYTES = 64 * 1024


def safe_json(value: Any) -> Any:
    """Return a JSON-serializable version of `value`, truncated if oversized."""
    if value is None:
        return None
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return {"_repr": repr(value)[:2000]}
    if len(encoded) > MAX_VALUE_BYTES:
        return {"_truncated": True, "preview": encoded[:MAX_VALUE_BYTES]}
    # Round-trip so downstream always gets plain JSON types.
    return json.loads(encoded)
