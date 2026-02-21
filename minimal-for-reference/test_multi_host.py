"""Multi-host SNMP test suite for synchronous wrapper."""

from async_wrapper import get_sync, make_oid, SnmpSyncError
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType
from typing import Dict, Tuple, Any

# Test configuration for different hosts
TEST_HOSTS = {
    "localhost": {
        "address": ("127.0.0.1", 161),
        "community": "public",
        "description": "macOS snmpd (read-only)",
    },
    "parrot": {
        "address": ("parrot", 161),
        "community": "public",
        "description": "Parrot Linux (read-only)",
    },
}

# Common OIDs to test
TEST_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
}


def test_host(
    host_name: str, host_config: Dict[str, Any], engine: SnmpEngine
) -> Tuple[bool, str]:
    """Test SNMP GET operation on a single host.

    Args:
        host_name: Name of host (for display)
        host_config: Configuration dict with address, community, description
        engine: SNMP engine instance

    Returns:
        (success: bool, result: str)
    """
    address = host_config["address"]
    community = host_config["community"]
    description = host_config["description"]

    print(f"\n📍 {host_name}: {description}")
    print(f"   Address: {address[0]}:{address[1]}")

    auth = CommunityData(community, mpModel=1)

    # Test sysDescr
    try:
        result = get_sync(
            engine,
            auth,
            address,
            [ObjectType(make_oid(TEST_OIDS["sysDescr"]))],
            timeout=2.0,
            retries=2,
        )
        for var_bind in result:
            value = (
                str(var_bind).split(" = ", 1)[1]
                if " = " in str(var_bind)
                else str(var_bind)
            )
            # Truncate long output
            if len(value) > 70:
                value = value[:67] + "..."
            print(f"   ✓ sysDescr: {value}")
        return True, "OK"

    except SnmpSyncError as e:
        error_msg = str(e)
        # Shorten common errors
        if "timeout" in error_msg.lower():
            error_msg = "Timeout - host unreachable"
        elif "refused" in error_msg.lower():
            error_msg = "Connection refused"
        print(f"   ✗ ERROR: {error_msg}")
        return False, error_msg
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {e}")
        return False, str(e)


def run_all_tests() -> None:
    """Run tests against all configured hosts."""
    engine = SnmpEngine()
    results: Dict[str, bool] = {}

    print("\n" + "=" * 70)
    print("SNMP Multi-Host Test Suite")
    print("=" * 70)

    for host_name, host_config in TEST_HOSTS.items():
        success, msg = test_host(host_name, host_config, engine)
        results[host_name] = success

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for host_name, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:8} {host_name}")

    passed = sum(1 for s in results.values() if s)
    total = len(results)
    print(f"\nTotal: {passed}/{total} hosts reachable")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_tests()
