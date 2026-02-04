"""
SNMPTypeInitializer: Helper to initialize SNMP values for table columns using type registry and MIB builder.
"""
from typing import Any, Dict, Optional, Callable
import logging

class SNMPTypeInitializer:
    _custom_initializers: Dict[str, Callable[[Dict[str, Any], 'SNMPTypeInitializer'], Any]] = {}

    @classmethod
    def register_initializer(cls, type_name: str, func: Callable[[Dict[str, Any], 'SNMPTypeInitializer'], Any]) -> None:
        cls._custom_initializers[type_name] = func

    def __init__(self, mib_builder: Any, type_registry: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
        self.mib_builder = mib_builder
        self.type_registry = type_registry
        self.logger = logger

    def get_type_class(self, type_name: str) -> Optional[Any]:
        if not type_name:
            return None
        try:
            return self.mib_builder.import_symbols('SNMPv2-SMI', type_name)[0]
        except Exception:
            try:
                return self.mib_builder.import_symbols('SNMPv2-TC', type_name)[0]
            except Exception:
                try:
                    from pysnmp.proto import rfc1902
                    return getattr(rfc1902, type_name, None)
                except Exception:
                    return None

    def get_default_value(self, type_name: str, type_info: Dict[str, Any]) -> Any:
        base_type = type_info.get('base_type') or type_name
        if type_info.get('enums'):
            enums = type_info.get('enums', [])
            if enums and isinstance(enums, list) and len(enums) > 0:
                return enums[0].get('value', 0)
            return 0
        if base_type in ('Integer32', 'Integer', 'Counter32', 'Gauge32', 'Unsigned32', 'TimeTicks'):
            return 0
        if base_type in ('OctetString', 'DisplayString'):
            return ''
        if base_type == 'ObjectIdentifier':
            return '0.0'
        return 0

    def initialize(self, col_info: Dict[str, Any]) -> Any:
        type_name = col_info.get('type', '')
        type_info = self.type_registry.get(type_name, {}) if type_name else {}
        # Check for custom initializer
        if type_name in self._custom_initializers:
            try:
                return self._custom_initializers[type_name](col_info, self)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Custom initializer for {type_name} failed: {e}")
                raise
        # Fallback to default logic
        type_class = self.get_type_class(type_name)
        if 'initial' in col_info:
            value = col_info['initial']
        else:
            value = self.get_default_value(type_name, type_info)
        if type_class is not None:
            try:
                return type_class(value)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to initialize {type_name} with value {value}: {e}")
                return value
        else:
            if self.logger:
                self.logger.error(f"No initializer for type '{type_name}' and no type class found. Please register a custom initializer.")
            raise RuntimeError(f"Missing initializer for type '{type_name}'")

# Example: Register a custom initializer for IpAddress
def _init_ipaddress(col_info: Dict[str, Any], initializer: SNMPTypeInitializer) -> Any:
    type_class = initializer.get_type_class('IpAddress')
    value = col_info.get('initial', '0.0.0.0')
    if type_class is not None:
        return type_class(value)
    return value

SNMPTypeInitializer.register_initializer('IpAddress', _init_ipaddress)
