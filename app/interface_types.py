"""Shared protocol/interface types for structural typing.

These protocols model capabilities exposed by dynamic PySNMP/runtime objects
without requiring inheritance.

Design rule:
- Keep protocols small and composable (method/attribute capability slices).
- Model richer, multi-field runtime data with adapter snapshots/dataclasses in
  ``app.mib_builder_adapters`` rather than growing monolithic protocols.
"""
# ruff: noqa: D102

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from pysnmp_type_wrapper.interfaces import ColumnMeta as _ColumnMeta
from pysnmp_type_wrapper.interfaces import EntryMeta as _EntryMeta
from pysnmp_type_wrapper.interfaces import MibJsonObject as _BoundaryMibJsonObject
from pysnmp_type_wrapper.interfaces import MutableScalarInstance as _MutableScalarInstance
from pysnmp_type_wrapper.interfaces import SnmpTypeFactory as _SnmpTypeFactory
from pysnmp_type_wrapper.interfaces import SupportsClone as _SupportsClone
from pysnmp_type_wrapper.interfaces import SupportsMibBuilder as _SupportsMibBuilder
from pysnmp_type_wrapper.interfaces import SupportsMibSymbolsAdapter as _SupportsMibSymbolsAdapter
from pysnmp_type_wrapper.interfaces import SupportsSnmpTypeResolver as _SupportsSnmpTypeResolver
from pysnmp_type_wrapper.interfaces import TableData as _TableData
from pysnmp_type_wrapper.interfaces import TableMeta as _TableMeta

# Pylint design rule, but Protocol slices are intentionally tiny.
# pylint: disable=too-few-public-methods

type InterfaceObject = object
type MibJsonObject = _BoundaryMibJsonObject
type MibJsonMap = dict[str, MibJsonObject]
type SnmpTypeFactory = _SnmpTypeFactory


@runtime_checkable
class SupportsMibBuilder(_SupportsMibBuilder, Protocol):
    """Compatibility shim for wrapper-owned MIB builder protocol."""


ColumnMeta = _ColumnMeta
EntryMeta = _EntryMeta
MutableScalarInstance = _MutableScalarInstance
SupportsClone = _SupportsClone
SupportsMibSymbolsAdapter = _SupportsMibSymbolsAdapter
SupportsSnmpTypeResolver = _SupportsSnmpTypeResolver
TableData = _TableData
TableMeta = _TableMeta


# Only keep runtime_checkable where you actually need isinstance() checks.
# If you never do runtime checks for these, remove the decorator and it will
# still work for static typing.


@runtime_checkable
class PrettyPrintable(Protocol):
    """Values that provide a display-friendly prettyPrint method."""

    def prettyPrint(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasName(Protocol):
    """Objects exposing getName for OID-like identity."""

    def getName(self) -> Iterable[int]:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasIndexNames(Protocol):
    """Objects exposing getIndexNames for table-index metadata."""

    def getIndexNames(self) -> Iterable[tuple[Any, Any, str]]:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasGetIndexNames(HasName, HasIndexNames, Protocol):
    """Composed protocol for MIB entries requiring both name and index metadata."""


@runtime_checkable
class HasSyntax(Protocol):
    """Objects exposing getSyntax for SNMP value metadata."""

    def getSyntax(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasGetMaxAccess(Protocol):
    """Objects exposing getMaxAccess for access metadata."""

    def getMaxAccess(self) -> object:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasGetDisplayHint(Protocol):
    """Objects exposing getDisplayHint textual metadata."""

    def getDisplayHint(self) -> str | None:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasDisplayHint(Protocol):
    """Objects exposing displayHint attribute metadata."""

    displayHint: str | None  # noqa: N815


@runtime_checkable
class HasNameAndSyntax(HasName, HasSyntax, Protocol):
    """Composed protocol for symbols exposing both OID name and syntax."""


@runtime_checkable
class HasDescription(Protocol):
    """Objects exposing getDescription textual metadata."""

    def getDescription(self) -> str:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasStatus(Protocol):
    """Objects exposing getStatus textual metadata."""

    def getStatus(self) -> str:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasObjects(Protocol):
    """Objects exposing varbind/object reference metadata."""

    def getObjects(self) -> Iterable[object]:  # noqa: N802  # pylint: disable=invalid-name
        ...


@runtime_checkable
class HasNamedValues(Protocol):
    """Objects exposing namedValues attribute for enum extraction."""

    namedValues: Mapping[object, object]  # noqa: N815


@runtime_checkable
class HasSubtypeSpec(Protocol):
    """Objects exposing subtypeSpec attribute for constraint extraction."""

    subtypeSpec: object  # noqa: N815


@runtime_checkable
class HasValues(Protocol):
    """Objects exposing values iterable for union-like constraints."""

    values: Iterable[object]
