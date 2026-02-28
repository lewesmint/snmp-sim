"""Compatibility shim for PySNMP mibSymbols adapter.

Prefer importing from ``pysnmp_type_wrapper.pysnmp_mib_symbols_adapter``.
"""

from pysnmp_type_wrapper.pysnmp_mib_symbols_adapter import (
    ADAPTER_EXCEPTIONS,
    PysnmpMibSymbolsAdapter,
)

__all__ = ["ADAPTER_EXCEPTIONS", "PysnmpMibSymbolsAdapter"]
