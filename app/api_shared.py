"""Shared types and helpers for API modules."""

from __future__ import annotations

from typing import Any, TypeAlias, cast

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
DecodedValue = JsonValue | bytes | bytearray

MIN_LINK_ENDPOINTS = 2
MIN_PARENT_OID_LEN = 2

ObjectType: TypeAlias = Any


def as_oid_list(value: JsonValue) -> list[int] | None:
    """Return value as a list[int] when it is an integer OID list."""
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, int) for item in value):
        return None
    return cast("list[int]", value)
