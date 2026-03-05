"""Minimal synchronous SNMP GET/SET test program.

Usage:
  python simple_test.py                        # Test against localhost:161 (macOS snmpd)
  python simple_test.py parrot                 # Test against parrot:161
  python simple_test.py parrot 1161            # Test against parrot:1161
  python simple_test.py parrot 1161 write      # Test SET on parrot
"""

import sys

try:
    from minimal_for_reference.async_wrapper import SnmpSyncError, get_sync, make_oid, set_sync
except ModuleNotFoundError:
    from async_wrapper import SnmpSyncError, get_sync, make_oid, set_sync
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType
from pysnmp.proto.rfc1902 import OctetString

# Parse arguments
host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 161
test_set = len(sys.argv) > 3 and sys.argv[3] == "write"

# Setup
engine = SnmpEngine()
auth = CommunityData("public", mpModel=1)
address = (host, port)

print(f"Testing synchronous SNMP operations on {address[0]}:{address[1]}")
print("=" * 60)

# Test GET - sysDescr.0
print("\n1. GET sysDescr.0")
try:
    result = get_sync(
        engine,
        auth,
        address,
        [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
        timeout=1.0,
        retries=2,
    )
    for var_bind in result:
        print(f"   ✓ {var_bind.prettyPrint()}")
except SnmpSyncError as e:
    print(f"   ✗ ERROR: {e}")
    sys.exit(1)

# Test SET if requested
if test_set:
    print("\n2. SET sysContact.0")
    auth_write = CommunityData("private", mpModel=1)
    try:
        result = set_sync(
            engine,
            auth_write,
            address,
            [
                ObjectType(
                    make_oid("1.3.6.1.2.1.1.4.0"), OctetString("test@example.com")
                )
            ],
            timeout=1.0,
            retries=1,
        )
        for var_bind in result:
            print(f"   ✓ SET: {var_bind.prettyPrint()}")

        # Verify SET worked
        print("\n3. GET sysContact.0 (verify SET)")
        result = get_sync(
            engine,
            auth,
            address,
            [ObjectType(make_oid("1.3.6.1.2.1.1.4.0"))],
            timeout=1.0,
            retries=2,
        )
        for var_bind in result:
            print(f"   ✓ {var_bind.prettyPrint()}")

    except SnmpSyncError as e:
        print(f"   ✗ ERROR: {e}")
else:
    print("\n💡 To test SET, run:")
    print(f"   python simple_test.py {host} {port} write")

print("\n" + "=" * 60)
print("Done!")
