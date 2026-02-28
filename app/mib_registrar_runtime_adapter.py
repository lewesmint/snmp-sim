"""Compatibility shim for runtime registrar adapter.

Prefer importing from ``pysnmp_type_wrapper.mib_registrar_runtime_adapter``.
"""

from pysnmp_type_wrapper.mib_registrar_runtime_adapter import (
    ADAPTER_EXCEPTIONS,
    RuntimeSnmpContextArgs,
    create_runtime_mib_registrar,
    decode_value_with_runtime_registrar,
)

__all__ = [
    "ADAPTER_EXCEPTIONS",
    "RuntimeSnmpContextArgs",
    "create_runtime_mib_registrar",
    "decode_value_with_runtime_registrar",
]
