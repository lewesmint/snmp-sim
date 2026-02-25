"""Basic type default value plugin."""

from typing import cast

from app.default_value_plugins import register_plugin
from app.types import TypeInfo
from plugins.type_encoders import register_type_encoder

# Register encoders for textual conventions that don't need special encoding
# but appear in MIB definitions


_NULL_MAC = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
_SYS_OBJECT_ID = [1, 3, 6, 1, 4, 1, 99999]
_ZERO_OID = [0, 0]
_ZERO_IP = [0, 0, 0, 0]

_SYMBOL_DEFAULTS: dict[str, object] = {
    "sysDescr": "Simple Python SNMP Agent",
    "sysObjectID": _SYS_OBJECT_ID,
    "sysContact": "Admin <admin@example.com>",
    "sysName": "snmp-agent",
    "sysLocation": "Server Room",
    "sysUpTime": 0,
    "sysServices": 72,
}

_DIRECT_TYPE_DEFAULTS: dict[str, object] = {
    "Counter32": 0,
    "Counter64": 0,
    "IpAddress": _ZERO_IP,
    "TimeTicks": 0,
    "Bits": [],
    "Opaque": [],
    "PhysAddress": _NULL_MAC,
    "MacAddress": _NULL_MAC,
    "DateAndTime": "2026-01-01,00:00:00.0",
    "TruthValue": 1,
    "RowStatus": 1,
    "StorageType": 3,
}

_STRING_TYPES = {"OctetString", "DisplayString", "SnmpAdminString", "OCTET STRING"}
_OID_TYPES = {"ObjectIdentifier", "AutonomousType", "OBJECT IDENTIFIER"}
_INTEGER_TYPES = {"Integer32", "Integer", "Gauge32", "Unsigned32", "INTEGER"}
_PLACEHOLDER_STRINGS = {"", "unset", "default", "none", "null", "n/a"}
_IPV4_OCTET_COUNT = 4
_IPV4_MAX_OCTET = 255
_DEFAULT_IPV4 = "0.0.0.0"  # noqa: S104


def _is_mac_symbol(symbol_name: str) -> bool:
    return (
        "PhysAddress" in symbol_name
        or "MacAddress" in symbol_name
        or symbol_name in {"ifPhysAddress", "ipNetMediaPhysAddress", "atPhysAddress"}
    )


def _is_ip_address_type(type_info: TypeInfo) -> bool:
    """Return True when type metadata represents IpAddress semantics."""
    base_type = str(type_info.get("base_type", ""))
    if base_type == "IpAddress":
        return True
    if base_type != "OCTET STRING":
        return False

    size_info = type_info.get("size")
    if isinstance(size_info, dict):
        allowed = size_info.get("allowed")
        if isinstance(allowed, list) and allowed == [4]:
            return True

    constraints = type_info.get("constraints")
    if isinstance(constraints, list):
        for constraint in constraints:
            if not isinstance(constraint, dict):
                continue
            if constraint.get("type") != "ValueSizeConstraint":
                continue
            if (
                constraint.get("min") == _IPV4_OCTET_COUNT
                and constraint.get("max") == _IPV4_OCTET_COUNT
            ):
                return True

    return False


def _encode_ip_address(value: object) -> str:  # noqa: PLR0911
    """Normalize Python value into valid dotted IPv4 syntax for PySNMP IpAddress."""

    def _normalize_octet(item: object) -> int | None:
        if not isinstance(item, (int, float, str, bytes, bytearray)):
            return None
        try:
            octet = int(item)
        except (TypeError, ValueError):
            return None
        return octet if 0 <= octet <= _IPV4_MAX_OCTET else None

    if isinstance(value, str):
        candidate = value.strip()
        if candidate.lower() in _PLACEHOLDER_STRINGS:
            return _DEFAULT_IPV4
        parts = candidate.split(".")
        if len(parts) != _IPV4_OCTET_COUNT:
            return _DEFAULT_IPV4
        octets: list[int] = []
        for part in parts:
            octet = _normalize_octet(part)
            if octet is None:
                return _DEFAULT_IPV4
            octets.append(octet)
        return ".".join(str(octet) for octet in octets)

    if isinstance(value, (list, tuple)) and len(value) == _IPV4_OCTET_COUNT:
        octets = []
        for part in value:
            octet = _normalize_octet(part)
            if octet is None:
                return _DEFAULT_IPV4
            octets.append(octet)
        return ".".join(str(octet) for octet in octets)

    return _DEFAULT_IPV4


def _get_first_enum_value(enums: object) -> object | None:
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
    if isinstance(enums, dict) and enums:
        values = list(enums.values())
        values.sort()
        return cast("object", values[0])

    # Handle list format (from type registry)
    if isinstance(enums, list) and enums:
        # List of dicts with 'value' key
        first_enum = enums[0]
        if isinstance(first_enum, dict):
            return first_enum.get("value")
        # Or list of values
        return cast("object", enums[0])

    return None


@register_plugin("basic_types")
def get_default_value(type_info: TypeInfo, symbol_name: str) -> object | None:
    """Provide default values for basic SNMP types."""
    base_type = type_info.get("base_type", "")
    default_value: object | None = _SYMBOL_DEFAULTS.get(symbol_name)

    if default_value is not None:
        return default_value

    if _is_mac_symbol(symbol_name):
        default_value = _NULL_MAC
    elif _is_ip_address_type(type_info):
        default_value = _ZERO_IP
    elif base_type in _STRING_TYPES:
        default_value = "unset"
    elif base_type in _OID_TYPES:
        default_value = _ZERO_OID
    elif base_type in _INTEGER_TYPES:
        default_value = 0
        enums = type_info.get("enums")
        if enums:
            first_value = _get_first_enum_value(enums)
            if first_value is not None:
                default_value = first_value
    else:
        default_value = _DIRECT_TYPE_DEFAULTS.get(str(base_type))

    return default_value


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
register_type_encoder("IpAddress", _encode_ip_address)
