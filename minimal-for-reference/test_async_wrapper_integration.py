"""
Integration tests for async_wrapper.py against a real SNMP agent.

These tests require an SNMP agent running on localhost:161.
To verify the agent is running:
    snmpget -v2c -c public localhost:161 sysDescr.0

Note: These tests are separate from unit tests (test_async_wrapper.py)
which use mocked PySNMP libraries.
"""

# pyright: reportCallIssue=false

import unittest
from typing import Any

import pytest

from async_wrapper import (
    SnmpSyncError,
    SyncSnmpClient,
    get_sync,
    make_oid,
    shutdown_sync_wrapper,
)

try:
    from pysnmp.hlapi.asyncio import (
        CommunityData,
        ObjectType,
        SnmpEngine,
    )
except ImportError:
    # pytest.skip("PySNMP not installed", allow_module_level=True)
    pass


# Test configuration
TEST_HOST = "127.0.0.1"
TEST_PORT = 161
TEST_COMMUNITY = "public"
TEST_TIMEOUT = 2.0
TEST_RETRIES = 1

# Common OIDs
OID_SYSDESCR = "1.3.6.1.2.1.1.1.0"  # System description
OID_SYSUPTIME = "1.3.6.1.2.1.1.3.0"  # System uptime
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"  # System name


def check_snmp_agent_available() -> bool:
    """Check if SNMP agent is available on localhost:161."""
    try:
        engine = SnmpEngine()
        auth = CommunityData(TEST_COMMUNITY, mpModel=1)
        oid = ObjectType(make_oid(OID_SYSDESCR))
        get_sync(engine, auth, (TEST_HOST, TEST_PORT), [oid], timeout=1.0, retries=0)
        return True
    except Exception:
        return False


# Skip all integration tests if SNMP agent is not available
# pytestmark = pytest.mark.skipif(
#     not check_snmp_agent_available(),
#     reason="SNMP agent not available on localhost:161. "
#     "Start an SNMP agent or use system snmpd.",
# )


class TestIntegrationGetOperations(unittest.TestCase):
    """Integration tests for SNMP GET operations."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.engine = SnmpEngine()
        self.auth = CommunityData(TEST_COMMUNITY, mpModel=1)
        self.address = (TEST_HOST, TEST_PORT)
        self.timeout = TEST_TIMEOUT
        self.retries = TEST_RETRIES

    def test_get_sysdescr(self) -> None:
        """Test getting sysDescr.0 from real SNMP agent."""
        oid = ObjectType(make_oid(OID_SYSDESCR))
        result = get_sync(
            self.engine, self.auth, self.address, [oid], self.timeout, self.retries
        )

        # Verify we got results
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

        # Verify the result contains data
        varbind = result[0]
        oid_obj, value = varbind
        self.assertIsNotNone(value)
        print(f"\nsysDescr.0 = {value}")

    def test_get_multiple_oids(self) -> None:
        """Test getting multiple OIDs in one request."""
        oid_descr = ObjectType(make_oid(OID_SYSDESCR))
        oid_uptime = ObjectType(make_oid(OID_SYSUPTIME))
        oid_name = ObjectType(make_oid(OID_SYSNAME))

        result = get_sync(
            self.engine,
            self.auth,
            self.address,
            [oid_descr, oid_uptime, oid_name],
            self.timeout,
            self.retries,
        )

        # Should get 3 results
        self.assertEqual(len(result), 3)

        for varbind in result:
            oid_obj, value = varbind
            self.assertIsNotNone(value)
            print(f"\n{oid_obj.prettyPrint()} = {value}")

    def test_get_invalid_oid(self) -> None:
        """Test error handling with invalid/non-existent OID."""
        # Use a likely non-existent OID
        invalid_oid = ObjectType(make_oid("1.3.6.1.2.1.999.999.999.0"))

        with self.assertRaises(SnmpSyncError) as context:
            get_sync(
                self.engine,
                self.auth,
                self.address,
                [invalid_oid],
                self.timeout,
                self.retries,
            )

        # Verify error message contains useful info
        error_msg = str(context.exception)
        self.assertTrue(len(error_msg) > 0)
        print(f"\nExpected error for invalid OID: {error_msg}")


class TestIntegrationClientClass(unittest.TestCase):
    """Integration tests for SyncSnmpClient convenience class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = SyncSnmpClient(
            engine=SnmpEngine(),
            auth=CommunityData(TEST_COMMUNITY, mpModel=1),
            address=(TEST_HOST, TEST_PORT),
            timeout=TEST_TIMEOUT,
            retries=TEST_RETRIES,
        )

    def test_client_get_single_oid(self) -> None:
        """Test client GET with single OID."""
        oid = ObjectType(make_oid(OID_SYSDESCR))
        result = self.client.get(oid)

        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

        varbind = result[0]
        oid_obj, value = varbind
        self.assertIsNotNone(value)
        print(f"\nClient GET: {oid_obj.prettyPrint()} = {value}")

    def test_client_get_multiple_oids(self) -> None:
        """Test client GET with multiple OIDs."""
        oid_descr = ObjectType(make_oid(OID_SYSDESCR))
        oid_uptime = ObjectType(make_oid(OID_SYSUPTIME))

        result = self.client.get(oid_descr, oid_uptime)

        self.assertEqual(len(result), 2)
        print("\nClient GET multiple:")
        for varbind in result:
            oid_obj, value = varbind
            print(f"  {oid_obj.prettyPrint()} = {value}")

    def test_client_reusability(self) -> None:
        """Test that client can be reused for multiple requests."""
        oid = ObjectType(make_oid(OID_SYSDESCR))

        # Make multiple requests with same client
        result1 = self.client.get(oid)
        result2 = self.client.get(oid)

        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        # Results should be consistent
        self.assertEqual(len(result1), len(result2))


class TestIntegrationAsyncContext(unittest.TestCase):
    """Integration tests for using wrapper from async context."""

    def test_async_context_get(self) -> None:
        """Test GET operation from within async context (tests thread safety)."""
        import asyncio

        async def async_snmp_get() -> Any:
            """Perform SNMP GET from async context."""
            engine = SnmpEngine()
            auth = CommunityData(TEST_COMMUNITY, mpModel=1)
            oid = ObjectType(make_oid(OID_SYSDESCR))
            result = get_sync(
                engine,
                auth,
                (TEST_HOST, TEST_PORT),
                [oid],
                timeout=TEST_TIMEOUT,
                retries=TEST_RETRIES,
            )
            return result

        # Run in async context
        result = asyncio.run(async_snmp_get())

        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

        varbind = result[0]
        oid_obj, value = varbind
        self.assertIsNotNone(value)
        print(f"\nAsync context GET: {oid_obj.prettyPrint()} = {value}")


class TestIntegrationErrorHandling(unittest.TestCase):
    """Integration tests for error handling with real network errors."""

    def test_timeout_unreachable_host(self) -> None:
        """Test timeout error with unreachable host."""
        engine = SnmpEngine()
        auth = CommunityData(TEST_COMMUNITY, mpModel=1)
        # Use TEST-NET-1 (192.0.2.0/24) - reserved for documentation, guaranteed unreachable
        oid = ObjectType(make_oid(OID_SYSDESCR))

        with self.assertRaises(SnmpSyncError) as context:
            get_sync(engine, auth, ("192.0.2.1", 161), [oid], timeout=0.5, retries=0)

        error_msg = str(context.exception)
        # Should contain timeout or request timeout info
        print(f"\nExpected timeout error: {error_msg}")
        self.assertTrue(len(error_msg) > 0)

    def test_wrong_community_string(self) -> None:
        """Test authentication failure with wrong community string."""
        engine = SnmpEngine()
        auth = CommunityData("wrong_community_string", mpModel=1)
        oid = ObjectType(make_oid(OID_SYSDESCR))

        # Wrong community typically results in timeout (agent doesn't respond)
        with self.assertRaises(SnmpSyncError):
            get_sync(
                engine,
                auth,
                (TEST_HOST, TEST_PORT),
                [oid],
                timeout=TEST_TIMEOUT,
                retries=0,
            )


def tearDownModule() -> None:
    """Clean up after all integration tests."""
    shutdown_sync_wrapper()
    print("\n\nIntegration tests complete. Background event loop shut down.")


if __name__ == "__main__":
    print("=" * 70)
    print("SNMP Async Wrapper - Integration Tests")
    print("=" * 70)
    print(f"Target: {TEST_HOST}:{TEST_PORT}")
    print(f"Community: {TEST_COMMUNITY}")
    print()

    if not check_snmp_agent_available():
        print("ERROR: No SNMP agent detected on localhost:161")
        print("\nTo run these tests, ensure snmpd is running:")
        print(
            "  macOS: sudo launchctl load -w /System/Library/LaunchDaemons/org.net-snmp.snmpd.plist"
        )
        print("  Linux: sudo systemctl start snmpd")
        print("\nVerify with: snmpget -v2c -c public localhost:161 sysDescr.0")
        exit(1)

    print("SNMP agent detected. Running integration tests...\n")
    unittest.main(verbosity=2)
