"""Basic type default value plugin."""

from typing import Any
from app.default_value_plugins import register_plugin
from app.types import TypeInfo


def _get_first_enum_value(enums: Any) -> Any:
    """Extract the first valid enum value from enums.
    
    Handles both dict format {'name': value, ...} and list format [{'value': v, 'name': n}, ...].
    
    Args:
        enums: Either a dict mapping names to values, or a list of dicts with 'value' keys
        
    Returns:
        The first valid enum value, or None if no valid enums found
    """
    if not enums:
        return None
        
    # Handle dict format (from generator._extract_type_info)
    if isinstance(enums, dict):
        # Sort by value to get the first (lowest) enum value
        if enums:
            values = list(enums.values())
            values.sort()
            return values[0]
    
    # Handle list format (from type registry)
    elif isinstance(enums, list):
        if enums:
            # List of dicts with 'value' key
            first_enum = enums[0]
            if isinstance(first_enum, dict):
                return first_enum.get('value')
            # Or list of values
            return enums[0]
    
    return None


@register_plugin("basic_types")
def get_default_value(type_info: TypeInfo, symbol_name: str) -> Any:
    """Provide default values for basic SNMP types."""
    base_type = type_info.get("base_type", "")

    # Handle specific symbols first
    if symbol_name == "sysDescr":
        return "Simple Python SNMP Agent"
    elif symbol_name == "sysObjectID":
        return [1, 3, 6, 1, 4, 1, 99999]
    elif symbol_name == "sysContact":
        return "Admin <admin@example.com>"
    elif symbol_name == "sysName":
        return "snmp-agent"
    elif symbol_name == "sysLocation":
        return "Server Room"
    elif symbol_name == "sysUpTime":
        return 0  # Will be dynamic
    elif symbol_name == "sysServices":
        return 72  # Application + End-to-end
    # MAC address fields should have proper null MAC
    elif "PhysAddress" in symbol_name or "MacAddress" in symbol_name or symbol_name in (
        "ifPhysAddress", "ipNetMediaPhysAddress", "atPhysAddress"
    ):
        return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    # Type-based defaults
    # Note: base_type can be the underlying type (e.g., 'INTEGER' for Counter32)
    # so we need to handle both the base_type and common derived types
    if base_type in ("OctetString", "DisplayString", "SnmpAdminString", "OCTET STRING"):
        # For MAC/physical addresses, use proper null MAC instead of "unset"
        if "PhysAddress" in symbol_name or "MacAddress" in symbol_name or symbol_name in (
            "ifPhysAddress", "ipNetMediaPhysAddress", "atPhysAddress"
        ):
            return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        return "unset"
    elif base_type in ("ObjectIdentifier", "AutonomousType", "OBJECT IDENTIFIER"):
        return [0, 0]
    elif base_type in ("Integer32", "Integer", "Gauge32", "Unsigned32", "INTEGER"):
        # Check for enums first - CRITICAL: must check before returning 0
        enums = type_info.get("enums")
        if enums:
            first_value = _get_first_enum_value(enums)
            if first_value is not None:
                return first_value
        # No enums, return 0 as default integer
        return 0
    elif base_type in ("Counter32", "Counter64"):
        return 0
    elif base_type == "IpAddress":
        return [0, 0, 0, 0]
    elif base_type == "TimeTicks":
        return 0
    elif base_type == "Bits":
        return []
    elif base_type == "Opaque":
        return []
    elif base_type == "PhysAddress":
        return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    elif base_type == "MacAddress":
        return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    elif base_type == "DateAndTime":
        return "2026-01-01,00:00:00.0"
    elif base_type == "TruthValue":
        return 1  # true(1)
    elif base_type == "RowStatus":
        return 1  # active(1)
    elif base_type == "StorageType":
        return 3  # volatile(3)

    # Fallback for unknown types - return None to indicate no default
    # (caller should handle appropriately, e.g., skip or use type-specific logic)
    return None

# Register encoders for textual conventions that don't need special encoding
# but appear in MIB definitions
from plugins.type_encoders import register_type_encoder

# ObjectIdentifier and aliases - pass through as-is (already handled by base_type_handler)
register_type_encoder("ObjectIdentifier", lambda x: x)
register_type_encoder("AutonomousType", lambda x: x)
register_type_encoder("ObjectName", lambda x: x)
register_type_encoder("NotificationName", lambda x: x)

# TimeStamp and Timestamp - pass through (already TimeTicks)
register_type_encoder("TimeStamp", lambda x: x)
register_type_encoder("Timestamp", lambda x: x)

# Other common textual conventions that pass through
register_type_encoder("SnmpAdminString", lambda x: x)
register_type_encoder("TruthValue", lambda x: x)
register_type_encoder("RowStatus", lambda x: x)
register_type_encoder("StorageType", lambda x: x)
register_type_encoder("DisplayString", lambda x: x)
register_type_encoder("PhysAddress", lambda x: x)
register_type_encoder("MacAddress", lambda x: x)