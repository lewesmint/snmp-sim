"""
Example usage of BaseTypeHandler for SNMP type management.
"""

from app.base_type_handler import BaseTypeHandler
from pysnmp.smi import builder
import json

# Load type registry
with open("data/types.json") as f:
    type_registry = json.load(f)

# Example 1: Initialize with type registry (required)
handler = BaseTypeHandler(type_registry=type_registry)

# Example 2: Get default values for any type
print("Integer32 default:", handler.get_default_value("Integer32"))  # 0
print("IpAddress default:", handler.get_default_value("IpAddress"))  # '0.0.0.0'
print("DisplayString default:", handler.get_default_value("DisplayString"))  # ''
print("Counter64 default:", handler.get_default_value("Counter64"))  # 0

# Example 3: Get default with context (e.g., initial value)
context = {"initial": 42}
print("With initial value:", handler.get_default_value("Integer32", context))  # 42

# Example 4: Resolve any type to its base ASN.1 type
print("\nBase types:")
print("Integer32 ->", handler.resolve_to_base_type("Integer32"))  # INTEGER
print("DisplayString ->", handler.resolve_to_base_type("DisplayString"))  # OCTET STRING
print("IpAddress ->", handler.resolve_to_base_type("IpAddress"))  # OCTET STRING
print("Counter64 ->", handler.resolve_to_base_type("Counter64"))  # INTEGER
print("RowStatus ->", handler.resolve_to_base_type("RowStatus"))  # INTEGER

# Example 5: Create PySNMP values

mib_builder = builder.MibBuilder()
value = handler.create_pysnmp_value("Integer32", 100, mib_builder)
print("\nCreated PySNMP value:", value)

# Example 6: Validate values
print("\nValidation:")
print("Valid Integer32(100):", handler.validate_value("Integer32", 100))  # True
print("Invalid Integer32('abc'):", handler.validate_value("Integer32", "abc"))  # False
print(
    "Valid DisplayString('test'):", handler.validate_value("DisplayString", "test")
)  # True

# Example 7: Handle any TEXTUAL-CONVENTION
# As long as it's in types.json, it works automatically!
print("\nCustom TC:")
print("CiscoAlarmSeverity default:", handler.get_default_value("CiscoAlarmSeverity"))
print("SnmpAdminString default:", handler.get_default_value("SnmpAdminString"))

# Example 8: Check type information from registry
type_info = handler.get_type_info("Integer32")
print("\nType info for Integer32:", type_info)
