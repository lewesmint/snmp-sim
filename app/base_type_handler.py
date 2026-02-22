"""
BaseTypeHandler: Clean type system that only hardcodes the 3 ASN.1 base types.

According to SNMPv2-SMI (RFC 2578), only these 3 types are fundamental:
- INTEGER
- OCTET STRING
- OBJECT IDENTIFIER

All other types (Integer32, Counter32, IpAddress, DisplayString, BITS, etc.)
are derived types that should be resolved from the type registry.
"""

from typing import Any, Optional
import logging

from app.types import TypeInfo, TypeRegistry


class BaseTypeHandler:
    """
    Handles SNMP type resolution and value initialization using only base ASN.1 types.
    All derived types, application types, and TEXTUAL-CONVENTIONs are resolved via type registry.
    """

    # The only 3 hardcoded types in the entire system
    BASE_ASN1_TYPES = {
        "INTEGER": "integer",
        "OCTET STRING": "octet_string",
        "OBJECT IDENTIFIER": "object_identifier",
    }

    def __init__(self, type_registry: TypeRegistry, logger: Optional[logging.Logger] = None):
        """
        Initialize the BaseTypeHandler.

        Args:
            type_registry: Type registry dict mapping type names to type info
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self._type_registry = type_registry

    @property
    def type_registry(self) -> TypeRegistry:
        """Get the type registry."""
        return self._type_registry

    def get_type_info(self, type_name: str) -> TypeInfo:
        """
        Get type information from registry.

        Args:
            type_name: Name of the type (e.g., 'Integer32', 'DisplayString', 'IpAddress')

        Returns:
            Dict with type information, or empty dict if not found
        """
        result: TypeInfo = self.type_registry.get(type_name, {})
        return result

    def resolve_to_base_type(self, type_name: str) -> str:
        """
        Resolve any type name to its base ASN.1 type.

        Args:
            type_name: Any SNMP type name

        Returns:
            One of: 'INTEGER', 'OCTET STRING', 'OBJECT IDENTIFIER'
        """
        # Check if it's already a base type
        if type_name in self.BASE_ASN1_TYPES:
            return type_name

        # Map SNMP application types to ASN.1 base types
        snmp_to_asn1_map = {
            "Integer32": "INTEGER",
            "Unsigned32": "INTEGER",
            "Counter32": "INTEGER",
            "Counter64": "INTEGER",
            "Gauge32": "INTEGER",
            "TimeTicks": "INTEGER",
            "OctetString": "OCTET STRING",
            "IpAddress": "OCTET STRING",
            "Opaque": "OCTET STRING",
            "Bits": "OCTET STRING",
            "ObjectIdentifier": "OBJECT IDENTIFIER",
            # ASN.1 base types (abstract)
            "Integer": "INTEGER",
            "Null": "INTEGER",  # Null is rarely used, maps to INTEGER
            # Abstract CHOICE types (structural only, not used in OBJECT-TYPEs)
            "ObjectSyntax": "INTEGER",  # CHOICE type, default to INTEGER
            "SimpleSyntax": "INTEGER",  # CHOICE type, default to INTEGER
            "ApplicationSyntax": "INTEGER",  # CHOICE type, default to INTEGER
            # Type aliases
            "ObjectName": "OBJECT IDENTIFIER",  # Alias for ObjectIdentifier
            "NotificationName": "OBJECT IDENTIFIER",  # Alias for ObjectIdentifier
        }

        if type_name in snmp_to_asn1_map:
            return snmp_to_asn1_map[type_name]

        # Look up in registry and recursively resolve
        type_info = self.get_type_info(type_name)
        base_type = type_info.get("base_type", "")

        if base_type and base_type != type_name:
            return self.resolve_to_base_type(base_type)

        # Default fallback
        self.logger.warning(f"Could not resolve base type for '{type_name}', defaulting to INTEGER")
        return "INTEGER"

    def get_default_value(self, type_name: str, context: Optional[TypeInfo] = None) -> Any:
        """
        Get a sensible default value for a type.

        Args:
            type_name: SNMP type name
            context: Optional context dict with 'initial', 'symbol_name', etc.

        Returns:
            Default value appropriate for the type
        """
        context = context or {}

        # If explicit initial value provided, use it
        if "initial" in context:
            return context["initial"]

        # Use type_info from context if provided
        # (caller can supply resolved info), otherwise get from registry.
        if "type_info" in context and isinstance(context["type_info"], dict):
            type_info = context["type_info"]
        else:
            type_info = self.get_type_info(type_name)

        # Resolve to base ASN.1 type. Prefer base_type from type_info when available.
        base_type_name = type_info.get("base_type", type_name)
        base_type = self.resolve_to_base_type(base_type_name)

        # Check if it's a human-readable string type based on display hint
        display_hint = type_info.get("display_hint", "")
        if base_type == "OCTET STRING":
            # Display hints with 'a' (ASCII) or 't' (UTF-8 text) indicate human-readable strings
            if display_hint and ("a" in display_hint or "t" in display_hint):
                return "Unset"
            # Also check for common string type names (heuristic for types without display hints)
            type_lower = type_name.lower()
            if any(
                keyword in type_lower
                for keyword in ["string", "display", "name", "descr", "label", "text"]
            ):
                return "Unset"

        # Handle enumerations
        enums = type_info.get("enums", [])
        if enums and isinstance(enums, list) and len(enums) > 0:
            # For enums, try to find a sensible default
            # Look for common default enum names
            for enum in enums:
                enum_name = enum.get("name", "").lower()
                if enum_name in [
                    "unknown",
                    "other",
                    "none",
                    "notset",
                    "unset",
                    "default",
                ]:
                    return enum.get("value", 0)
            # Otherwise return the first enum value
            return enums[0].get("value", 0)

        if base_type == "INTEGER":
            # Check constraints for valid range
            constraints = type_info.get("constraints", [])
            min_val = None
            max_val = None

            for constraint in constraints:
                if constraint.get("type") == "ValueRangeConstraint":
                    c_min = constraint.get("min")
                    c_max = constraint.get("max")
                    if c_min is not None and (min_val is None or c_min > min_val):
                        min_val = c_min
                    if c_max is not None and (max_val is None or c_max < max_val):
                        max_val = c_max

            # Prefer 0 if it's in range, otherwise use min
            if min_val is not None and max_val is not None:
                if min_val <= 0 <= max_val:
                    return 0
                return min_val
            return 0

        if base_type == "OCTET STRING":
            # Check if it's a special type
            if type_name in ["IpAddress"]:
                return "0.0.0.0"
            if "address" in type_name.lower() and "mac" in type_name.lower():
                return "00:00:00:00:00:00"
            # BITS type - return empty bits
            if "bits" in type_info.get("syntax", "").lower():
                return ""
            # Default to empty bytes
            return b""

        if base_type == "OBJECT IDENTIFIER":
            return (0, 0)

        # Should never reach here
        self.logger.warning(f"Unexpected base type '{base_type}' for '{type_name}'")
        return 0

    def create_pysnmp_value(self, type_name: str, value: Any, mib_builder: Any = None) -> Any:
        """
        Create a PySNMP value object for the given type and value.

        Args:
            type_name: SNMP type name
            value: Python value to wrap
            mib_builder: Optional MIB builder to import type classes

        Returns:
            PySNMP value object
        """
        if mib_builder is None:
            # Return raw value if no MIB builder available
            return value

        # Try to import the actual type class
        type_class = self._get_pysnmp_type_class(type_name, mib_builder)

        if type_class is not None:
            try:
                return type_class(value)
            except Exception as e:
                self.logger.warning(f"Failed to create {type_name} with value {value}: {e}")
                return value

        # Fallback: create based on base type
        base_type = self.resolve_to_base_type(type_name)

        try:
            if base_type == "INTEGER":
                from pysnmp.proto import rfc1902

                return rfc1902.Integer32(value)
            if base_type == "OCTET STRING":
                from pysnmp.proto import rfc1902

                if isinstance(value, str):
                    value = value.encode("utf-8")
                return rfc1902.OctetString(value)
            if base_type == "OBJECT IDENTIFIER":
                from pysnmp.proto import rfc1902

                return rfc1902.ObjectIdentifier(value)
        except Exception as e:
            self.logger.error(f"Failed to create PySNMP value: {e}")

        return value

    def _get_pysnmp_type_class(self, type_name: str, mib_builder: Any) -> Optional[Any]:
        """
        Import PySNMP type class from MIB builder or rfc1902.

        Strategy:
        1. Try MibBuilder first (for TEXTUAL-CONVENTIONs like DisplayString, PhysAddress)
        2. Fallback to rfc1902 (for base types like Integer32, OctetString, Counter32)

        Note: TEXTUAL-CONVENTIONs (DisplayString, PhysAddress, etc.) are NOT in rfc1902.
        They must come from MibBuilder.import_symbols('SNMPv2-TC', ...).
        See docs/PYSNMP_TYPE_SOURCING.md for details.

        Args:
            type_name: SNMP type name (e.g., 'DisplayString', 'Integer32', 'OctetString')
            mib_builder: MIB builder instance

        Returns:
            PySNMP type class or None if not found
        """
        # Try MibBuilder first - handles both base types and TEXTUAL-CONVENTIONs
        # SNMPv2-SMI: base types (Integer32, Counter32, etc.)
        # SNMPv2-TC: TEXTUAL-CONVENTIONs (DisplayString, PhysAddress, etc.)
        # SNMPv2-CONF: conformance types (rarely used for values)
        for module in ["SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"]:
            try:
                return mib_builder.import_symbols(module, type_name)[0]
            except Exception:
                continue

        # Fallback to rfc1902 for base RFC 1902 types
        # This works for: Integer32, Counter32, OctetString, IpAddress, etc.
        # This FAILS for: DisplayString, PhysAddress, MacAddress, etc. (returns None)
        try:
            from pysnmp.proto import rfc1902

            return getattr(rfc1902, type_name, None)
        except ImportError:
            pass

        return None

    def validate_value(self, type_name: str, value: Any) -> bool:
        """
        Validate that a value is appropriate for the given type.

        Args:
            type_name: SNMP type name
            value: Value to validate

        Returns:
            True if valid, False otherwise
        """
        type_info = self.get_type_info(type_name)
        base_type = self.resolve_to_base_type(type_name)

        # Type compatibility check
        if base_type == "INTEGER":
            if not isinstance(value, (int, bool)):
                return False
            # Check range constraints
            constraints = type_info.get("constraints", {})
            if "range" in constraints:
                range_val = constraints["range"]
                if isinstance(range_val, list) and len(range_val) >= 2:
                    if not range_val[0] <= value <= range_val[1]:
                        return False

        elif base_type == "OCTET STRING":
            if not isinstance(value, (str, bytes, bytearray)):
                return False
            # Check size constraints
            constraints = type_info.get("constraints", {})
            if "size" in constraints:
                size = constraints["size"]
                length = len(value)
                if isinstance(size, int):
                    if length != size:
                        return False
                elif isinstance(size, list) and len(size) >= 2:
                    if not size[0] <= length <= size[1]:
                        return False

        elif base_type == "OBJECT IDENTIFIER":
            if not isinstance(value, (tuple, list)):
                return False
            if not all(isinstance(x, int) for x in value):
                return False

        return True
