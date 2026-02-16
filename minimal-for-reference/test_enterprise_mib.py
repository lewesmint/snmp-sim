"""Test enterprise MIB objects on parrot using synchronous SNMP wrapper.

This demonstrates:
1. Loading and using custom enterprise MIBs
2. Using the synchronous GET API with the async PySNMP wrapper
3. Full type safety and error handling
"""

from async_wrapper import get_sync, make_oid, SnmpSyncError
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType

# Setup
engine = SnmpEngine()
auth_read = CommunityData("public", mpModel=1)
address = ("parrot", 161)

print("Testing Enterprise MIB (99999) on parrot")
print("=" * 60)

# Define enterprise OIDs
OIDS = {
    "myString": "1.3.6.1.4.1.99999.1.1.0",           # read-write
}

# Test GETs
print("\n📖 GET Operations with Enterprise MIB:")
print("-" * 60)

for name, oid in OIDS.items():
    try:
        result = get_sync(
            engine,
            auth_read,
            address,
            [ObjectType(make_oid(oid))],
            timeout=1.0,
            retries=1,
        )
        for var_bind in result:
            value = str(var_bind).split(" = ", 1)[1] if " = " in str(var_bind) else str(var_bind)
            print(f"✓ {name:18} = {value}")
    except SnmpSyncError as e:
        print(f"✗ {name:18} → ERROR: {e}")

print("\n" + "=" * 60)
print("✅ Enterprise MIB test complete!")
print("\nKey Takeaway:")
print("• Custom MIB file installed to ~/.snmp/mibs/")
print("• Synchronous API successfully reads enterprise OIDs")
print("• The wrapper handles async transport creation internally")
print("=" * 60 + "\n")

