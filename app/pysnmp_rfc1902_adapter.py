"""Compatibility shim for RFC1902 boundary adapter.

Prefer importing from ``pysnmp_type_wrapper.pysnmp_rfc1902_adapter``.
"""

from pysnmp_type_wrapper.pysnmp_rfc1902_adapter import (
    ADAPTER_EXCEPTIONS,
    PysnmpRfc1902Adapter,
)

__all__ = ["ADAPTER_EXCEPTIONS", "PysnmpRfc1902Adapter"]
