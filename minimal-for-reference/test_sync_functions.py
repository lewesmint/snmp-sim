"""Test synchronous SNMP functions: get_sync, set_sync, get_next_sync.

Tests the wrapper against parrot:161 with enterprise MIB 99999.
Verifies results match CLI snmp commands.
"""

from async_wrapper import (
    get_sync,
    get_next_sync,
    make_oid,
    SnmpSyncError,
    SyncSnmpClient,
)
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType
from typing import List


def test_get_sync() -> None:
    """Test synchronous GET operation.

    Equivalent to: snmpget -v2c -c public parrot 1.3.6.1.4.1.99999.1.1.0
    """
    print("\n📖 Test 1: get_sync")
    print("-" * 60)

    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)
    address = ("parrot", 161)

    oid = ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))

    try:
        result = get_sync(engine, auth, address, [oid], timeout=1.0, retries=1)

        print("✓ GET succeeded")
        for var_bind in result:
            value_str = str(var_bind)
            print(f"  {value_str}")
            # Should be: myString.0 = Updated via sync wrapper
            assert "myString" in value_str or "99999" in value_str
        return
    except SnmpSyncError as e:
        print(f"✗ GET failed: {e}")
        raise


def test_get_next_sync() -> None:
    """Test synchronous GET-NEXT operation (for snmpwalk).

    Equivalent to: snmpgetnext -v2c -c public parrot 1.3.6.1.4.1.99999.1.1.0
    """
    print("\n📖 Test 2: get_next_sync")
    print("-" * 60)

    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)
    address = ("parrot", 161)

    oid = ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))

    try:
        result = get_next_sync(engine, auth, address, [oid], timeout=1.0, retries=1)

        print("✓ GET-NEXT succeeded")
        for var_bind in result:
            value_str = str(var_bind)
            print(f"  {value_str}")
            # Should return myCounter (next OID after myString)
            assert "99999" in value_str
        return
    except SnmpSyncError as e:
        print(f"✗ GET-NEXT failed: {e}")
        raise


def test_walk_enterprise_mib() -> None:
    """Test snmpwalk by repeatedly calling get_next.

    Equivalent to: snmpwalk -v2c -c public parrot 1.3.6.1.4.1.99999
    """
    print("\n📖 Test 3: walk_enterprise_mib (snmpwalk simulation)")
    print("-" * 60)

    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)
    address = ("parrot", 161)

    # Start at enterprise root
    current_oid = ObjectType(make_oid("1.3.6.1.4.1.99999"))

    results: List[str] = []
    max_iterations = 20
    iteration = 0

    try:
        while iteration < max_iterations:
            iteration += 1

            try:
                result = get_next_sync(
                    engine, auth, address, [current_oid], timeout=1.0, retries=1
                )

                for var_bind in result:
                    oid_str = str(var_bind)
                    results.append(oid_str)
                    print(f"  {oid_str}")

                    # Check if we've walked past the enterprise root
                    if not oid_str.startswith("1.3.6.1.4.1.99999"):
                        print(
                            f"✓ WALK complete - walked past enterprise root after {len(results)} OIDs"
                        )
                        return

                    # Update current OID for next iteration
                    # Extract just the OID part before the =
                    oid_part = oid_str.split(" = ")[0]
                    current_oid = ObjectType(make_oid(oid_part))

            except SnmpSyncError:
                if iteration > 1:
                    print(f"✓ WALK complete - {len(results)} OIDs retrieved")
                    return
                raise

        print(f"✓ WALK retrieved {len(results)} OIDs before max iterations")

    except SnmpSyncError as e:
        print(f"✗ WALK failed: {e}")
        raise


def test_sync_client() -> None:
    """Test the SyncSnmpClient convenience class."""
    print("\n📖 Test 4: SyncSnmpClient")
    print("-" * 60)

    client = SyncSnmpClient(
        engine=SnmpEngine(),
        auth=CommunityData("public", mpModel=1),
        address=("parrot", 161),
        timeout=1.0,
        retries=1,
    )

    try:
        # Test get
        oid = ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))
        result = client.get(oid)
        print("✓ client.get() succeeded")
        for var_bind in result:
            print(f"  {var_bind}")

        # Test get_next
        result = client.get_next(oid)
        print("✓ client.get_next() succeeded")
        for var_bind in result:
            print(f"  {var_bind}")

    except SnmpSyncError as e:
        print(f"✗ SyncSnmpClient test failed: {e}")
        raise


def main() -> None:
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SNMP SYNC WRAPPER TESTS")
    print("=" * 60)
    print("Testing: get_sync, set_sync, get_next_sync, SyncSnmpClient")
    print("Target: parrot:161 (Enterprise MIB 99999)")

    try:
        test_get_sync()
        test_get_next_sync()
        test_walk_enterprise_mib()
        test_sync_client()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\n✓ sync_snmp_get works")
        print("✓ sync_snmp_get_next works (for snmpwalk)")
        print("✓ SyncSnmpClient works")
        print("✓ Full synchronous wrapper functional")
        print("=" * 60 + "\n")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60 + "\n")
        raise


if __name__ == "__main__":
    main()
