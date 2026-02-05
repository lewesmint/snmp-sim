"""Basic type default value plugin."""

from typing import Any, Dict
from app.default_value_plugins import register_plugin

# Type alias for type information dictionaries
TypeInfo = Dict[str, Any]

@register_plugin('basic_types')
def get_default_value(type_info : TypeInfo, symbol_name : str) -> Any:
    """Provide default values for basic SNMP types."""
    base_type = type_info.get('base_type', '')

    # Handle specific symbols first
    if symbol_name == 'sysDescr':
        return 'Simple Python SNMP Agent'
    elif symbol_name == 'sysObjectID':
        return [1, 3, 6, 1, 4, 1, 99999]
    elif symbol_name == 'sysContact':
        return 'Admin <admin@example.com>'
    elif symbol_name == 'sysName':
        return 'snmp-agent'
    elif symbol_name == 'sysLocation':
        return 'Server Room'
    elif symbol_name == 'sysUpTime':
        return 0  # Will be dynamic
    elif symbol_name == 'sysServices':
        return 72  # Application + End-to-end

    # Type-based defaults
    # Note: base_type can be the underlying type (e.g., 'INTEGER' for Counter32)
    # so we need to handle both the base_type and common derived types
    if base_type in ('OctetString', 'DisplayString', 'SnmpAdminString', 'OCTET STRING'):
        return 'unset'
    elif base_type in ('ObjectIdentifier', 'AutonomousType', 'OBJECT IDENTIFIER'):
        return [0, 0]
    elif base_type in ('Integer32', 'Integer', 'Gauge32', 'Unsigned32', 'INTEGER'):
        # Check for enums
        if type_info.get('enums'):
            # Return first enum value
            enums = type_info['enums']
            if enums:
                return enums[0]['value']
        return 0
    elif base_type in ('Counter32', 'Counter64'):
        return 0
    elif base_type == 'IpAddress':
        return [0, 0, 0, 0]
    elif base_type == 'TimeTicks':
        return 0
    elif base_type == 'Bits':
        return []
    elif base_type == 'Opaque':
        return []
    elif base_type == 'PhysAddress':
        return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    elif base_type == 'MacAddress':
        return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    elif base_type == 'DateAndTime':
        return '2026-01-01,00:00:00.0'
    elif base_type == 'TruthValue':
        return 1  # true(1)
    elif base_type == 'RowStatus':
        return 1  # active(1)
    elif base_type == 'StorageType':
        return 3  # volatile(3)
    
    # Fallback for unknown types - return None to indicate no default
    # (caller should handle appropriately, e.g., skip or use type-specific logic)
    return None
