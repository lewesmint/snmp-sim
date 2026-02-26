"""Shared types and helpers for API modules."""

from __future__ import annotations

from typing import Any, cast

JsonScalar = str | int | float | bool | None
# Use Any for recursive type to avoid Pydantic v2 RecursionError during schema generation
type JsonValue = Any  # str | int | float | bool | None | list | dict (recursive)
JsonObject = dict[str, Any]
DecodedValue = Any | bytes | bytearray

MIN_LINK_ENDPOINTS = 2
MIN_PARENT_OID_LEN = 2

type ObjectType = Any


def as_oid_list(value: JsonValue) -> list[int] | None:
    """Return value as a list[int] when it is an integer OID list."""
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, int) for item in value):
        return None
    return cast("list[int]", value)
