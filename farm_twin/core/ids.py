"""
FILE: farm_twin/core/ids.py
PURPOSE: Stable identifiers. Use UUIDv7 (time-ordered) for all primary keys; `new_id(prefix) -> "plot_<uuid7>"`.
Content-hash helper `input_hash(obj) -> sha256 hex` over canonical JSON (sorted keys, floats repr'd with 12 sig digits)
used for simulation reproducibility records and caching.
TESTS: ids sortable by creation time; input_hash identical for logically identical dicts.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any


def _canonical(value: Any) -> Any:
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if hasattr(value, "model_dump"):
        return _canonical(value.model_dump(mode="json"))
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def input_hash(obj: Any) -> str:
    payload = json.dumps(_canonical(obj), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def new_id(prefix: str) -> str:
    """Generate a time-sortable UUIDv7-like identifier on Python 3.11."""
    milliseconds = int(time.time() * 1000) & ((1 << 48) - 1)
    random = uuid.uuid4().int
    value = (milliseconds << 80) | (0x7 << 76) | (random & ((1 << 76) - 1))
    # Variant bits RFC 4122.
    value = (value & ~(0b11 << 62)) | (0b10 << 62)
    return f"{prefix}_{uuid.UUID(int=value)}"
