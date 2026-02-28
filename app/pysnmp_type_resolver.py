"""Compatibility shim for PySNMP type resolution adapter.

Prefer importing from ``pysnmp_type_wrapper.pysnmp_type_resolver``.
"""

from pysnmp_type_wrapper.pysnmp_type_resolver import PysnmpTypeResolver

__all__ = ["PysnmpTypeResolver"]
