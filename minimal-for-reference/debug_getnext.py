#!/usr/bin/env python3
"""Debug get_next_sync hanging."""

from async_wrapper import get_sync, get_next_sync, make_oid
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType

address = ("parrot", 161)

print("Test 1: get_sync")
engine1 = SnmpEngine()
auth1 = CommunityData("public", mpModel=1)
result = get_sync(
    engine1,
    auth1,
    address,
    [ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))],
    timeout=1.0,
    retries=1,
)
for var_bind in result:
    print(f"✓ {var_bind}")

print("\nTest 2: get_next_sync (fresh engine, short timeout)")
engine2 = SnmpEngine()
auth2 = CommunityData("public", mpModel=1)
try:
    result = get_next_sync(
        engine2,
        auth2,
        address,
        [ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))],
        timeout=0.5,
        retries=1,
    )
    for var_bind in result:
        print(f"✓ {var_bind}")
except Exception as e:
    print(f"Error: {e}")
