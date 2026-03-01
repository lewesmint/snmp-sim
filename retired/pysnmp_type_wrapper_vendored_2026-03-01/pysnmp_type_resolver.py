"""PySNMP type resolution adapter."""

from __future__ import annotations

from pysnmp.proto import rfc1902

from .interfaces import SnmpTypeFactory, SupportsMibBuilder


class PysnmpTypeResolver:  # pylint: disable=too-few-public-methods
    """Resolve SNMP type factories from MIB modules and runtime fallback."""

    def resolve_type_factory(
        self,
        base_type: str,
        mib_builder: SupportsMibBuilder | None,
    ) -> SnmpTypeFactory | None:
        """Resolve a type class/factory for ``base_type``."""
        if not base_type or mib_builder is None:
            return None

        for module_name in ("SNMPv2-SMI", "SNMPv2-TC"):
            try:
                symbols = mib_builder.import_symbols(module_name, base_type)
                if symbols:
                    symbol = symbols[0]
                    if callable(symbol):
                        return symbol
            except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                continue

        try:
            symbol = getattr(rfc1902, base_type, None)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            return None
        return symbol if callable(symbol) else None
