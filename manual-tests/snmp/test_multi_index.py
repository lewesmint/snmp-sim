#!/usr/bin/env python3
"""Test script to verify multi-index table expansion."""

import logging
from app.mib_registrar import MibRegistrar

# Create a mock logger
logger = logging.getLogger("test")
logger.setLevel(logging.DEBUG)

# Create a minimal test with mock objects
class MockTable:
    pass

# Create registrar with minimal args
registrar = MibRegistrar(
    mib_builder=object(),
    mib_scalar_instance=object(),
    mib_table=MockTable,
    mib_table_row=MockTable,
    mib_table_column=MockTable,
    logger=logger,
    start_time=0.0
)

# Test IpAddress expansion
print("Testing IpAddress expansion:")
result = registrar._expand_index_value_to_oid_components("192.168.1.1", "IpAddress")
print(f"  '192.168.1.1' -> {result}")
assert result == (192, 168, 1, 1), f"Expected (192, 168, 1, 1), got {result}"

# Test port expansion  
print("Testing Unsigned32 expansion:")
result = registrar._expand_index_value_to_oid_components(8080, "Unsigned32")
print(f"  8080 -> {result}")
assert result == (8080,), f"Expected (8080,), got {result}"

# Test combined
print("\nTesting combined multi-index:")
ip_parts = registrar._expand_index_value_to_oid_components("192.168.1.1", "IpAddress")
port_parts = registrar._expand_index_value_to_oid_components(8080, "Unsigned32")
combined = ip_parts + port_parts
print(f"  Combined OID suffix: .{'.'.join(str(x) for x in combined)}")
assert combined == (192, 168, 1, 1, 8080), f"Expected (192, 168, 1, 1, 8080), got {combined}"

print("\n✅ All tests passed!")
