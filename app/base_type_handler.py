"""BaseTypeHandler: Clean type system that only hardcodes the 3 ASN.1 base types.

According to SNMPv2-SMI (RFC 2578), only these 3 types are fundamental:
- INTEGER
- OCTET STRING
- OBJECT IDENTIFIER

All other types (Integer32, Counter32, IpAddress, DisplayString, BITS, etc.)
are derived types that should be resolved from the type registry.
"""

import logging
from typing import ClassVar, Protocol, cast

from pysnmp.proto import rfc1902
from pysnmp_type_wrapper.interfaces import SupportsMibBuilder

from app.types import TypeInfo, TypeRegistry


class TypeFactory(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol for callable that creates type instances."""

    def __call__(self, value: object) -> object:
        """Create instance of the type."""
        ...  # pylint: disable=unnecessary-ellipsis

# Constraint range tuple size threshold
_CONSTRAINT_RANGE_SIZE = 2


class BaseTypeHandler:
    """Handles SNMP type resolution and value initialization using only base ASN.1 types.

    All derived types, application types, and TEXTUAL-CONVENTIONs are resolved via type registry.
    """

    # The only 3 hardcoded types in the entire system
    BASE_ASN1_TYPES: ClassVar[dict[str, str]] = {
        "INTEGER": "integer",
        "OCTET STRING": "octet_string",
        "OBJECT IDENTIFIER": "object_identifier",
    }

    def __init__(self, type_registry: TypeRegistry, logger: logging.Logger | None = None) -> None:
        """Initialize the BaseTypeHandler.

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
        """Get type information from registry.

        Args:
            type_name: Name of the type (e.g., 'Integer32', 'DisplayString', 'IpAddress')

        Returns:
            Dict with type information, or empty dict if not found

        """
        result: TypeInfo = self.type_registry.get(type_name, {})
        return result

    def resolve_to_base_type(self, type_name: str) -> str:
        """Resolve any type name to its base ASN.1 type.

        Args:
            type_name: object SNMP type name

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
        self.logger.warning(
            "Could not resolve base type for '%s', defaulting to INTEGER",
            type_name,
        )
        return "INTEGER"

    def _get_default_enum_value(self, type_info: TypeInfo) -> int | None:
        """Get default value from enumeration list.

        Args:
            type_info: Type information dict with enums

        Returns:
            Default enum value or None if no enums

        """
        enums = type_info.get("enums", [])
        if not enums or not isinstance(enums, list) or len(enums) == 0:
            return None

        # Try to find a sensible default enum name
        for enum in enums:
            enum_name = enum.get("name", "").lower()
            if enum_name in ["unknown", "other", "none", "notset", "unset", "default"]:
                value = enum.get("value", 0)
                return int(value) if isinstance(value, (int, float)) else 0
        # Otherwise return the first enum value
        value = enums[0].get("value", 0)
        return int(value) if isinstance(value, (int, float)) else 0

    def _get_default_integer_value(self, type_info: TypeInfo) -> int:
        """Get default value for INTEGER type with range constraints.

        Args:
            type_info: Type information dict with constraints

        Returns:
            Default integer value

        """
        constraints = type_info.get("constraints", [])
        min_val: int | None = None
        max_val: int | None = None

        for constraint in constraints:
            if constraint.get("type") == "ValueRangeConstraint":
                c_min = constraint.get("min")
                c_max = constraint.get("max")
                if c_min is not None and (min_val is None or c_min > min_val):
                    min_val = int(c_min) if not isinstance(c_min, int) else c_min
                if c_max is not None and (max_val is None or c_max < max_val):
                    max_val = int(c_max) if not isinstance(c_max, int) else c_max

        # Prefer 0 if it's in range, otherwise use min
        if min_val is not None and max_val is not None:
            if min_val <= 0 <= max_val:
                return 0
            return min_val
        return 0

    def _get_default_octet_string_value(
            self,
            type_name: str,
            type_info: TypeInfo,
    ) -> str | bytes:
        """Get default value for OCTET STRING type.

        Args:
            type_name: SNMP type name
            type_info: Type information dict

        Returns:
            Default octet string value

        """
        # Check if it's a special type
        if type_name == "IpAddress":
            return "0.0.0.0"  # noqa: S104
        if "address" in type_name.lower() and "mac" in type_name.lower():
            return "00:00:00:00:00:00"
        # BITS type - return empty bits
        if "bits" in type_info.get("syntax", "").lower():
            return ""
        # Default to empty bytes
        return b""

    def _is_human_readable_string(self, type_name: str, type_info: TypeInfo) -> bool:
        """Check if type represents a human-readable string.

        Args:
            type_name: SNMP type name
            type_info: Type information dict

        Returns:
            True if type is a human-readable string

        """
        # Check display hint for ASCII or UTF-8 text indicators
        display_hint = type_info.get("display_hint", "")
        if display_hint and ("a" in display_hint or "t" in display_hint):
            return True
        # Check for common string type names
        type_lower = type_name.lower()
        return any(
            keyword in type_lower
            for keyword in ["string", "display", "name", "descr", "label", "text"]
        )

    def _get_default_for_base_type(
            self,
            base_type: str,
            type_name: str,
            type_info: TypeInfo,
    ) -> int | str | bytes | tuple[int, ...]:
        """Get default value for a specific base type.

        Args:
            base_type: Base ASN.1 type
            type_name: SNMP type name
            type_info: Type information dict

        Returns:
            Default value for the base type

        """
        if base_type == "INTEGER":
            return self._get_default_integer_value(type_info)
        if base_type == "OCTET STRING":
            return self._get_default_octet_string_value(type_name, type_info)
        if base_type == "OBJECT IDENTIFIER":
            return (0, 0)
        # Fallback (shouldn't reach here)
        self.logger.warning("Unexpected base type '%s' for '%s'", base_type, type_name)
        return 0

    def get_default_value(
        self,
        type_name: str,
        context: TypeInfo | None = None,
    ) -> int | str | bytes | tuple[int, ...] | None:
        """Get a sensible default value for a type.

        Args:
            type_name: SNMP type name
            context: Optional context dict with 'initial', 'symbol_name', etc.

        Returns:
            Default value appropriate for the type

        """
        context = context or {}

        # If explicit initial value provided, use it
        if "initial" in context:
            return cast("int | str | bytes | tuple[int, ...] | None", context["initial"])

        # Use type_info from context if provided
        # (caller can supply resolved info), otherwise get from registry.
        if "type_info" in context and isinstance(context["type_info"], dict):
            type_info = context["type_info"]
        else:
            type_info = self.get_type_info(type_name)

        # Resolve to base ASN.1 type. Prefer base_type from type_info when available.
        base_type_name = type_info.get("base_type", type_name)
        base_type = self.resolve_to_base_type(base_type_name)

        # Check if it's a human-readable string type and return default
        if base_type == "OCTET STRING" and self._is_human_readable_string(type_name, type_info):
            return "Unset"

        # Handle enumerations
        enum_value = self._get_default_enum_value(type_info)
        if enum_value is not None:
            return enum_value

        # Handle specific base types
        return self._get_default_for_base_type(base_type, type_name, type_info)

    def create_pysnmp_value(
        self,
        type_name: str,
        *,
        value: int | str | bytes | tuple[int, ...] | bool,
        mib_builder: SupportsMibBuilder | None = None,
    ) -> object:
        """Create a PySNMP value object for the given type and value.

        Args:
            type_name: SNMP type name
            value: Python value to wrap
            mib_builder: Optional MIB builder to import type classes

        Returns:
            PySNMP value object

        """
        result: object = value

        if mib_builder is not None:
            # Try to import the actual type class
            type_class = self._get_pysnmp_type_class(type_name, mib_builder)

            if type_class is not None:
                try:
                    result = type_class(value)
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ) as e:
                    self.logger.warning(
                        "Failed to create %s with value %s: %s",
                        type_name,
                        value,
                        e,
                    )
            else:
                # Fallback: create based on base type
                base_type = self.resolve_to_base_type(type_name)
                try:
                    if base_type == "INTEGER":
                        result = rfc1902.Integer32(value)
                    elif base_type == "OCTET STRING":
                        encoded_value = value.encode("utf-8") if isinstance(value, str) else value
                        result = rfc1902.OctetString(encoded_value)
                    elif base_type == "OBJECT IDENTIFIER":
                        result = rfc1902.ObjectIdentifier(value)
                except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                    self.logger.exception("Failed to create PySNMP value")

        return result

    def _get_pysnmp_type_class(
        self,
        type_name: str,
        mib_builder: SupportsMibBuilder,
    ) -> TypeFactory | None:
        """Import PySNMP type class from MIB builder or rfc1902.

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
        mib_modules = ["SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"]
        for module in mib_modules:
            result = self._import_from_mib(module, type_name, mib_builder)
            if result is not None:
                return result

        # Fallback to rfc1902 for base RFC 1902 types
        # This works for: Integer32, Counter32, OctetString, IpAddress, etc.
        # This FAILS for: DisplayString, PhysAddress, MacAddress, etc. (returns None)
        return getattr(rfc1902, type_name, None)

    def _import_from_mib(
            self,
            module: str,
            type_name: str,
            mib_builder: SupportsMibBuilder,
    ) -> TypeFactory | None:
        """Import type from a MIB module.

        Args:
            module: MIB module name
            type_name: Type name to import
            mib_builder: MIB builder instance

        Returns:
            Type class or None if not found

        """
        try:
            return cast("TypeFactory", mib_builder.import_symbols(module, type_name)[0])
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            return None

    def _validate_integer(self, value: object, type_info: TypeInfo) -> bool:
        """Validate INTEGER type value with range constraints.

        Args:
            value: Value to validate
            type_info: Type information dict

        Returns:
            True if valid

        """
        if not isinstance(value, (int, bool)):
            return False
        # Check range constraints
        constraints = type_info.get("constraints", {})
        if "range" in constraints:
            range_val = constraints["range"]
            if isinstance(range_val, list) and len(range_val) >= _CONSTRAINT_RANGE_SIZE:
                min_range = int(range_val[0]) if not isinstance(range_val[0], int) else range_val[0]
                max_range = int(range_val[1]) if not isinstance(range_val[1], int) else range_val[1]
                int_value = int(value)
                return min_range <= int_value <= max_range
        return True

    def _validate_octet_string(self, value: object, type_info: TypeInfo) -> bool:
        """Validate OCTET STRING type value with size constraints.

        Args:
            value: Value to validate
            type_info: Type information dict

        Returns:
            True if valid

        """
        if not isinstance(value, (str, bytes, bytearray)):
            return False
        # Check size constraints
        constraints = type_info.get("constraints", {})
        if "size" in constraints:
            size = constraints["size"]
            length = len(value)
            if isinstance(size, int) and length != size:
                return False
            if (
                isinstance(size, list)
                and len(size) >= _CONSTRAINT_RANGE_SIZE
                and not (size[0] <= length <= size[1])
            ):
                return False
        return True

    def _validate_object_identifier(self, value: object) -> bool:
        """Validate OBJECT IDENTIFIER type value.

        Args:
            value: Value to validate

        Returns:
            True if valid

        """
        if not isinstance(value, (tuple, list)):
            return False
        return all(isinstance(x, int) for x in value)

    def validate_value(self, type_name: str, value: object) -> bool:
        """Validate that a value is appropriate for the given type.

        Args:
            type_name: SNMP type name
            value: Value to validate

        Returns:
            True if valid, False otherwise

        """
        type_info = self.get_type_info(type_name)
        base_type = self.resolve_to_base_type(type_name)

        if base_type == "INTEGER":
            return self._validate_integer(value, type_info)
        if base_type == "OCTET STRING":
            return self._validate_octet_string(value, type_info)
        if base_type == "OBJECT IDENTIFIER":
            return self._validate_object_identifier(value)

        return True
