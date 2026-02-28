"""Shared protocol/interface types for structural typing.

These protocols model *capabilities* exposed by dynamic PySNMP/runtime objects
without requiring inheritance.

Design rule:
- Keep protocols small and composable (method/attribute capability slices).
- Model richer, multi-field runtime data with adapter snapshots/dataclasses in
    ``app.mib_builder_adapters`` rather than growing monolithic protocols.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PrettyPrintable(Protocol):
    """Values that provide a display-friendly prettyPrint method."""

    def prettyPrint(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        """Return a display-friendly representation."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasName(Protocol):
    """Objects exposing getName for OID-like identity."""

    def getName(self) -> Iterable[int]:  # noqa: N802  # pylint: disable=invalid-name
        """Return the object's OID tuple/list."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasIndexNames(Protocol):
    """Objects exposing getIndexNames for table-index metadata."""

    def getIndexNames(self) -> Iterable[tuple[Any, Any, str]]:  # noqa: N802  # pylint: disable=invalid-name
        """Return index metadata tuples, where element 3 is the index symbol name."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasGetIndexNames(HasName, HasIndexNames, Protocol):
    """Composed protocol for MIB entries requiring both name and index metadata."""


@runtime_checkable
class HasSyntax(Protocol):
    """Objects exposing getSyntax for SNMP value metadata."""

    def getSyntax(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        """Return syntax/type object for this symbol."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasGetMaxAccess(Protocol):
    """Objects exposing getMaxAccess for access metadata."""

    def getMaxAccess(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        """Return max-access metadata for this symbol."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasNameAndSyntax(HasName, HasSyntax, Protocol):
    """Composed protocol for symbols exposing both OID name and syntax."""


@runtime_checkable
class HasDescription(Protocol):
    """Objects exposing getDescription textual metadata."""

    def getDescription(self) -> str:  # noqa: N802  # pylint: disable=invalid-name
        """Return a description payload for this symbol."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasStatus(Protocol):
    """Objects exposing getStatus textual metadata."""

    def getStatus(self) -> str:  # noqa: N802  # pylint: disable=invalid-name
        """Return status metadata for this symbol."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasObjects(Protocol):
    """Objects exposing varbind/object reference metadata."""

    def getObjects(self) -> Iterable[object]:  # noqa: N802  # pylint: disable=invalid-name
        """Return object references associated with a notification symbol."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class HasNamedValues(Protocol):
    """Objects exposing namedValues attribute for enum extraction."""

    namedValues: Mapping[object, object]


@runtime_checkable
class HasSubtypeSpec(Protocol):
    """Objects exposing subtypeSpec attribute for constraint extraction."""

    subtypeSpec: object


@runtime_checkable
class HasValues(Protocol):
    """Objects exposing values iterable for union-like constraints."""

    values: Iterable[object]
