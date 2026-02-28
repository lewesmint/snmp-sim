"""Typed adapters for interacting with dynamic PySNMP MIB builder symbols."""

from __future__ import annotations

from dataclasses import dataclass

from app.interface_types import (
    HasDescription,
    HasGetMaxAccess,
    HasName,
    HasNameAndSyntax,
    HasSyntax,
)

ADAPTER_EXCEPTIONS = (
    AttributeError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
    RuntimeError,
)


@dataclass(frozen=True)
class MibSymbolSnapshot:
    """Typed snapshot extracted from a dynamic MIB symbol object."""

    oid: tuple[int, ...]
    syntax_obj: object
    access: str
    class_name: str


@dataclass(frozen=True)
class MibOptionalMetadata:
    """Optional metadata extracted from a dynamic MIB symbol."""

    oid: tuple[int, ...]
    access: str | None
    type_name: str | None
    description: str | None


def extract_symbol_snapshot(symbol_obj: object) -> MibSymbolSnapshot | None:
    """Extract typed symbol metadata from a dynamic PySNMP object.

    Returns `None` when the object does not provide the required symbol methods
    or when extraction fails.
    """
    if not isinstance(symbol_obj, HasNameAndSyntax):
        return None

    try:
        oid = tuple(int(x) for x in symbol_obj.getName())
        syntax_obj = symbol_obj.getSyntax()
    except ADAPTER_EXCEPTIONS:
        return None

    access = "unknown"
    if isinstance(symbol_obj, HasGetMaxAccess):
        try:
            access = str(symbol_obj.getMaxAccess())
        except ADAPTER_EXCEPTIONS:
            access = "unknown"

    return MibSymbolSnapshot(
        oid=oid,
        syntax_obj=syntax_obj,
        access=access,
        class_name=symbol_obj.__class__.__name__,
    )


def extract_symbol_oid(symbol_obj: object) -> tuple[int, ...] | None:
    """Extract a symbol OID tuple from dynamic object, if available."""
    if not isinstance(symbol_obj, HasName):
        return None
    try:
        return tuple(int(x) for x in symbol_obj.getName())
    except ADAPTER_EXCEPTIONS:
        return None


def extract_optional_metadata(symbol_obj: object) -> MibOptionalMetadata | None:
    """Extract optional UI-friendly metadata from a dynamic symbol object."""
    oid = extract_symbol_oid(symbol_obj)
    if oid is None:
        return None

    access: str | None = None
    if isinstance(symbol_obj, HasGetMaxAccess):
        try:
            access = str(symbol_obj.getMaxAccess())
        except ADAPTER_EXCEPTIONS:
            access = None

    type_name: str | None = None
    if isinstance(symbol_obj, HasSyntax):
        try:
            type_name = type(symbol_obj.getSyntax()).__name__
        except ADAPTER_EXCEPTIONS:
            type_name = None

    description: str | None = None
    if isinstance(symbol_obj, HasDescription):
        try:
            description = str(symbol_obj.getDescription())
        except ADAPTER_EXCEPTIONS:
            description = None

    return MibOptionalMetadata(
        oid=oid,
        access=access,
        type_name=type_name,
        description=description,
    )
