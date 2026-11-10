"""
FILE: farm_twin/core/ids.py
PURPOSE: Stable identifiers. Use UUIDv7 (time-ordered) for all primary keys; `new_id(prefix) -> "plot_<uuid7>"`.
Content-hash helper `input_hash(obj) -> sha256 hex` over canonical JSON (sorted keys, floats repr'd with 12 sig digits)
used for simulation reproducibility records and caching.
TESTS: ids sortable by creation time; input_hash identical for logically identical dicts.
"""
