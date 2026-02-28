"""Compatibility shim for raw PySNMP boundary types.

Prefer importing from ``pysnmp_type_wrapper.raw_boundary_types``.
"""

from collections.abc import Mapping

from pysnmp_type_wrapper.raw_boundary_types import (
    SupportsBoundaryMibBuilder,
    SupportsBoundarySnmpEngine,
)

type MibSymbolMap = Mapping[str, Mapping[str, object]]

__all__ = [
    "MibSymbolMap",
    "SupportsBoundaryMibBuilder",
    "SupportsBoundarySnmpEngine",
]
