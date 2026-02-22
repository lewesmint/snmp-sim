"""Tests for JSON formatting helpers."""

from __future__ import annotations

from app.json_format import dumps_with_horizontal_oid_lists


def test_dumps_with_horizontal_oid_lists_compacts_oid_only() -> None:
    """Compacts oid lists while leaving other lists in normal pretty format."""
    payload = {
        "oid": [1, 3, 6, 1],
        "nested": {"oid": [1, 2, 3]},
        "values": [1, 2, 3],
    }

    rendered = dumps_with_horizontal_oid_lists(payload, indent=2)

    assert '"oid": [1, 3, 6, 1]' in rendered
    assert '"oid": [1, 2, 3]' in rendered
    assert '"values": [\n' in rendered
