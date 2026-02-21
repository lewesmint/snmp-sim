#!/usr/bin/env python3
"""Optimized tests for SNMP wrapper: get_sync, set_sync, get_next_sync."""

import sys
import time
from snmp_wrapper import (
    StatelessSnmpClient,
    PersistentSnmpClient,
    SnmpSyncError,
    make_oid,
)
from pysnmp.hlapi.asyncio import CommunityData, ObjectType

# Test configuration
PARROT_ADDRESS = ("parrot", 161)
PUBLIC_AUTH = CommunityData("public", mpModel=1)


# ============================================================================
# Test 1: StatelessSnmpClient
# ============================================================================


def test_stateless_client_get() -> None:
    """Test: StatelessSnmpClient.get() retrieves values correctly."""
    client = StatelessSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    # Old test with enterprise MIB OIDs
    # oids = [
    #     ("1.3.6.1.4.1.99999.1.1.0", "myString"),
    #     ("1.3.6.1.4.1.99999.1.2.0", "myCounter"),
    #     ("1.3.6.1.4.1.99999.1.3.0", "myGauge"),
    # ]

    # Test standard MIB OIDs - can pass multiple ObjectType as separate args
    oids = [
        ("1.3.6.1.2.1.1.1.0", "sysDescr", "Simple Python SNMP Agent"),
        ("1.3.6.1.2.1.1.4.0", "sysContact", "admin"),
    ]

    # Build ObjectType objects for variadic call
    var_binds = [ObjectType(make_oid(oid)) for oid, _, _ in oids]

    # Call get with multiple OIDs at once
    result = client.get(*var_binds)
    assert result is not None and len(result) == len(oids), (
        f"Expected {len(oids)} results, got {len(result)}"
    )

    # Validate each result
    for i, (oid, name, expected_str) in enumerate(oids):
        obj_type = result[i]
        value_str = str(obj_type[1])
        assert expected_str in value_str, (
            f"Expected '{expected_str}' in {name} value, got: {value_str}"
        )

    print("StatelessSnmpClient.get() works")


def test_stateless_client_repeated_calls() -> None:
    """Test: StatelessSnmpClient handles repeated calls (different engine each time)."""
    client = StatelessSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    # Make 5 rapid calls (each creates fresh engine)
    for i in range(5):
        result = client.get(ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0")))
        assert result is not None and len(result) >= 1, f"Call {i + 1} failed"
        obj_type = result[0]
        oid_str = str(obj_type[0])
        assert "99999" in oid_str, f"Call {i + 1} returned wrong OID"
        value = obj_type[1]
        assert value is not None, f"Call {i + 1} returned None value"

    print("StatelessSnmpClient handles repeated calls")


# ============================================================================
# Test 2: PersistentSnmpClient
# ============================================================================


def test_persistent_client_get() -> None:
    """Test: PersistentSnmpClient.get() retrieves values correctly."""
    client = PersistentSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    try:
        # Test multiple OIDs (same engine reused)
        oids = [
            ("1.3.6.1.2.1.1.1.0", "sysDescr", "Simple Python SNMP Agent"),
            ("1.3.6.1.2.1.1.4.0", "sysContact", "admin"),
        ]

        for oid, name, expected_str in oids:
            result = client.get(ObjectType(make_oid(oid)))
            assert result is not None and len(result) >= 1, f"Expected result for {name}"

            # result is (ObjectType(...),), so result[0] is ObjectType, result[0][1] is the value
            obj_type = result[0]
            value_str = str(obj_type[1])
            assert expected_str in value_str, (
                f"Expected '{expected_str}' in {name} value, got: {value_str}"
            )

        print("✅ PersistentSnmpClient.get() works")
    finally:
        client.shutdown()


def test_persistent_client_interleaved_ops() -> None:
    """Test: PersistentSnmpClient handles mixed get/set/get_next operations."""
    client = PersistentSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    try:
        # GET
        result1 = client.get(ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0")))
        assert result1, "GET failed"

        # GET-NEXT
        result2 = client.get_next(ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0")))
        assert result2, "GET-NEXT failed"

        # GET again (engine still working)
        result3 = client.get(ObjectType(make_oid("1.3.6.1.4.1.99999.1.2.0")))
        assert result3, "Second GET failed"

        print("PersistentSnmpClient handles interleaved operations")
    finally:
        client.shutdown()


def test_persistent_client_set() -> None:
    """Test: PersistentSnmpClient.set() can set writable OID values."""
    from pysnmp.proto.rfc1902 import Integer

    client = PersistentSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    try:
        # Set a writable integer value
        oid = "1.3.6.1.4.1.99999.1.4.0"
        new_value = 80

        # Perform SET operation
        result = client.set(ObjectType(make_oid(oid), Integer(new_value)))
        assert result is not None and len(result) >= 1, f"SET failed for {oid}"

        # Verify by getting the value back
        get_result = client.get(ObjectType(make_oid(oid)))
        assert get_result is not None and len(get_result) >= 1, "GET after SET failed"

        obj_type = get_result[0]
        retrieved_value = int(obj_type[1])
        assert retrieved_value == new_value, f"Expected {new_value}, got {retrieved_value}"

        print(f"✅ PersistentSnmpClient.set() works (set to {new_value})")
    finally:
        client.shutdown()


# ============================================================================
# Test 3: GET-NEXT for snmpwalk
# ============================================================================


def test_snmpwalk_simulation() -> None:
    """Test: PersistentSnmpClient.get_next() can simulate snmpwalk."""
    client = PersistentSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    try:
        current_oid = ObjectType(make_oid("1.3.6.1.4.1.99999"))
        oid_count = 0

        # Walk through enterprise MIB using get_next
        for iteration in range(20):
            result = client.get_next(current_oid)
            assert result is not None and len(result) >= 1, (
                f"GET-NEXT failed at iteration {iteration}"
            )

            # result is (ObjectType(...),), so result[0] is ObjectType with [0]=OID, [1]=value
            obj_type = result[0]
            oid_str = str(obj_type[0])
            oid_count += 1

            # Stop when we walk past enterprise root
            if "99999" not in oid_str:
                break

            # Create new ObjectType for next iteration using the returned OID
            current_oid = ObjectType(obj_type[0])

        assert oid_count > 1, "Expected to walk multiple OIDs"
        print(f"✅ Snmpwalk simulation works ({oid_count} OIDs walked)")
    finally:
        client.shutdown()


# ============================================================================
# Test 4: Performance Comparison
# ============================================================================


def test_performance_comparison() -> None:
    """Test: Compare performance of both clients."""
    oid = ObjectType(make_oid("1.3.6.1.4.1.99999.1.1.0"))
    iterations = 5

    # Stateless: fresh engine per call
    print("\n  Stateless client (fresh engine per call):")
    client_stateless = StatelessSnmpClient(
        auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1
    )
    start = time.time()
    for i in range(iterations):
        client_stateless.get(oid)
    stateless_time = time.time() - start
    print(
        f"    {iterations} calls: {stateless_time:.2f}s ({stateless_time / iterations:.2f}s per call)"
    )

    # Persistent: reused engine
    print("\n  Persistent client (reused engine):")
    client_persistent = PersistentSnmpClient(
        auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1
    )
    try:
        start = time.time()
        for i in range(iterations):
            client_persistent.get(oid)
        persistent_time = time.time() - start
        print(
            f"    {iterations} calls: {persistent_time:.2f}s ({persistent_time / iterations:.2f}s per call)"
        )

        # Speed comparison
        speedup = stateless_time / persistent_time if persistent_time > 0 else float("inf")
        print(f"\n  Speedup: {speedup:.1f}x faster with persistent client")
        assert persistent_time > 0, "Persistent client timing must be positive"
        assert speedup >= 0.9, (
            "Expected persistent client to be roughly equal or faster (allowing 10% margin)"
        )
    finally:
        client_persistent.shutdown()


# ============================================================================
# Test 5: Error Handling
# ============================================================================


def test_error_handling() -> None:
    """Test: Wrapper handles errors gracefully."""
    client = StatelessSnmpClient(auth=PUBLIC_AUTH, address=PARROT_ADDRESS, timeout=1.0, retries=1)

    # Try invalid OID (should not crash, just return "no such object")
    try:
        result = client.get(ObjectType(make_oid("1.3.6.1.999.999.999.0")))
        # May succeed but return "No Such Object" string
        assert result is not None and isinstance(result, (list, tuple)), (
            "Expected non-None result for invalid OID"
        )
    except SnmpSyncError as e:
        # Or raise error - both are acceptable
        print(f"  (Invalid OID raised error as expected: {e})")

    print("✅ Error handling works")


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SNMP WRAPPER TEST SUITE")
    print("=" * 70)
    print(f"Target: {PARROT_ADDRESS}")

    tests = [
        ("StatelessSnmpClient.get()", test_stateless_client_get),
        ("StatelessSnmpClient (repeated calls)", test_stateless_client_repeated_calls),
        ("PersistentSnmpClient.get()", test_persistent_client_get),
        (
            "PersistentSnmpClient (interleaved ops)",
            test_persistent_client_interleaved_ops,
        ),
        ("PersistentSnmpClient (SET operation)", test_persistent_client_set),
        ("Snmpwalk simulation", test_snmpwalk_simulation),
        ("Performance comparison", test_performance_comparison),
        ("Error handling", test_error_handling),
    ]

    failed = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 70)
        try:
            test_func()
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed.append((test_name, e))

    print("\n" + "=" * 70)
    if not failed:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {len(failed)} TEST(S) FAILED:")
        for test_name, error in failed:
            print(f"  • {test_name}: {error}")
        sys.exit(1)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
