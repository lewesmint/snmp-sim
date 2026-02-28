"""Shared boundary interfaces for PySNMP integration.

These interfaces are intentionally framework-agnostic so other applications can
reuse the adapter layer without importing project-specific modules.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

type MibSymbolMap = Mapping[str, Mapping[str, object]]
type SnmpTypeFactory = Callable[..., object]


@runtime_checkable
class SupportsMibBuilder(Protocol):
    """Minimal builder API used by generic type-resolution flows."""

    def import_symbols(self, module: str, *symbols: str) -> tuple[object, ...]:
        """Import symbols from a MIB module."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def export_symbols(self, module: str, *symbols: str) -> object:
        """Export symbols into a MIB module."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class SupportsMibSymbolsBuilder(SupportsMibBuilder, Protocol):
    """Builder API that also exposes mutable ``mibSymbols`` maps."""

    mibSymbols: MibSymbolMap  # noqa: N815


@runtime_checkable
class SupportsSnmpTypeResolver(Protocol):
    """Adapter capability for resolving PySNMP type factories by type name."""

    def resolve_type_factory(
        self,
        base_type: str,
        mib_builder: SupportsMibBuilder | None,
    ) -> SnmpTypeFactory | None:
        """Resolve a type factory from loaded MIB symbols or runtime fallbacks."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class MutableScalarInstance(Protocol):
    """Mutable scalar-instance shape consumed by agent logic."""

    name: tuple[int, ...]
    syntax: object


@runtime_checkable
class SupportsClone(Protocol):
    """Values exposing PySNMP-style clone(value) behavior."""

    def clone(self, value: object) -> object:
        """Return cloned value preserving runtime constraints."""
        msg = "Protocol method"
        raise NotImplementedError(msg)


@runtime_checkable
class SupportsMibSymbolsAdapter(Protocol):
    """Adapter contract over dynamic ``mibSymbols`` state."""

    def load_symbol_class(self, module: str, symbol: str) -> type[object] | None:
        """Load a class-like symbol from MIB builder imports."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def find_scalar_instance_by_oid(
        self,
        oid: tuple[int, ...],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None:
        """Return scalar instance by exact OID when present."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def get_all_named_oids(self) -> dict[str, tuple[int, ...]]:
        """Return symbol-name to OID map for symbols exposing OID names."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def lookup_symbol_for_oid(self, oid: tuple[int, ...]) -> tuple[str | None, str | None]:
        """Return ``(module_name, symbol_name)`` for exact OID match."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def iter_scalar_instances(
        self,
        scalar_instance_cls: type[object],
    ) -> list[tuple[str, str, MutableScalarInstance]]:
        """Return ``(module_name, symbol_name, symbol_obj)`` scalar triplets."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def find_scalar_instance_by_candidate_oids(
        self,
        candidate_oids: list[tuple[int, ...]],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None:
        """Return first scalar instance whose OID matches any candidate."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def get_symbol_access(self, symbol_obj: object) -> str | None:
        """Return symbol max-access string when available."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def find_column_oid_for_entry(
        self,
        column_name: str,
        entry_oid: tuple[int, ...],
    ) -> tuple[int, ...] | None:
        """Return column OID when symbol belongs to entry subtree."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def find_template_instance_for_column(
        self,
        column_name: str,
        scalar_instance_cls: type[object],
    ) -> tuple[str, MutableScalarInstance, tuple[int, ...]] | None:
        """Return module/template/column_oid for creating sibling instances."""
        msg = "Protocol method"
        raise NotImplementedError(msg)

    def upsert_symbol(self, module_name: str, symbol_name: str, symbol_obj: object) -> bool:
        """Insert or replace a symbol in a target module map."""
        msg = "Protocol method"
        raise NotImplementedError(msg)
