"""Raw PySNMP boundary types.

These aliases model dynamic/internal PySNMP structures and should stay at the
integration boundary. Application-domain contracts should consume normalized,
strongly typed snapshots/adapters instead of these raw maps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


type MibSymbolMap = Mapping[str, Mapping[str, object]]


class SupportsBoundaryMibBuilder(Protocol):
    """Minimal MIB builder surface used at the PySNMP boundary."""

    mibSymbols: MibSymbolMap  # noqa: N815 (matches PySNMP interface)

    def add_mib_sources(self, *mib_sources: object) -> None:
        """Register MIB source locations."""
        raise NotImplementedError

    def import_symbols(self, module: str, *symbols: str) -> tuple[object, ...]:
        """Import symbols from a MIB module."""
        raise NotImplementedError

    def load_modules(self, *module_names: str) -> None:
        """Load named MIB modules."""
        raise NotImplementedError


class SupportsBoundarySnmpEngine(Protocol):
    """Minimal SNMP engine surface used at the PySNMP boundary."""

    def get_mib_builder(self) -> SupportsBoundaryMibBuilder:
        """Return the associated MIB builder."""
        raise NotImplementedError


__all__ = [
    "MibSymbolMap",
    "SupportsBoundaryMibBuilder",
    "SupportsBoundarySnmpEngine",
]
