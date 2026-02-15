"""
Example usage of the async_wrapper synchronous SNMP wrapper.

This demonstrates how to use the wrapper for basic SNMP operations.
Note: Requires a running SNMP agent on the target.
"""
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from async_wrapper import (
    SyncSnmpClient,
    get_sync,
    make_oid,
    set_sync,
    shutdown_sync_wrapper,
)

# Import PySNMP 7.x components
try:
    from pysnmp.hlapi.asyncio import (
        CommunityData,
        ObjectType,
        SnmpEngine,
    )
except ImportError:
    print("PySNMP 7.x is required. Install with: pip install pysnmp")
    exit(1)


def example_basic_get() -> None:
    """Example 1: Basic GET using function."""
    print("\n=== Example 1: Basic GET ===")

    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)  # SNMPv2c
    address = ("127.0.0.1", 161)

    try:
        # Get sysDescr.0 (1.3.6.1.2.1.1.1.0)
        oid = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))
        result = get_sync(engine, auth, address, [oid], timeout=1.0, retries=1)

        print("sysDescr.0:")
        for vb in result:
            print(f"  {vb.prettyPrint()}")

    except Exception as e:
        print(f"Error: {e}")


def example_basic_set() -> None:
    """Example 2: Basic SET using function."""
    print("\n=== Example 2: Basic SET ===")

    engine = SnmpEngine()
    auth = CommunityData("private", mpModel=1)  # SNMPv2c with write community
    address = ("127.0.0.1", 161)

    try:
        # Set sysContact.0 to a new value (example uses writable OID)
        # In production, you'd use an actual writable OID
        oid = ObjectType(make_oid("1.3.6.1.2.1.1.4.0"), "admin@example.com")
        result = set_sync(engine, auth, address, [oid], timeout=1.0, retries=1)

        print("SET result:")
        for vb in result:
            print(f"  {vb.prettyPrint()}")

    except Exception as e:
        print(f"Error: {e}")


def example_client_class() -> None:
    """Example 3: Using the convenience SyncSnmpClient class."""
    print("\n=== Example 3: Using SyncSnmpClient ===")

    # Create a reusable client
    client = SyncSnmpClient(
        engine=SnmpEngine(),
        auth=CommunityData("public", mpModel=1),
        address=("127.0.0.1", 161),
        timeout=1.0,
        retries=1,
    )

    try:
        # Get multiple OIDs
        oid_descr = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))  # sysDescr
        oid_uptime = ObjectType(make_oid("1.3.6.1.2.1.1.3.0"))  # sysUpTime

        print("Getting multiple OIDs...")
        result = client.get(oid_descr, oid_uptime)

        for vb in result:
            print(f"  {vb.prettyPrint()}")

    except Exception as e:
        print(f"Error: {e}")


def example_async_context() -> None:
    """Example 4: Using from within an async context (demonstrates threading)."""
    print("\n=== Example 4: From async context ===")
    import asyncio

    async def async_main() -> None:
        """This function runs in an asyncio event loop."""
        print("Running sync SNMP operation from async context...")

        engine = SnmpEngine()
        auth = CommunityData("public", mpModel=1)
        address = ("127.0.0.1", 161)

        try:
            oid = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))
            # The sync function detects the running loop and uses a background thread
            result = get_sync(engine, auth, address, [oid], timeout=1.0, retries=1)
            for vb in result:
                print(f"  {vb.prettyPrint()}")
        except Exception as e:
            print(f"Error: {e}")

    try:
        asyncio.run(async_main())
    except Exception as e:
        print(f"Async error: {e}")


def example_error_handling() -> None:
    """Example 5: Error handling."""
    print("\n=== Example 5: Error Handling ===")

    from async_wrapper import SnmpSyncError

    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)
    address = ("192.0.2.1", 161)  # Unreachable (TEST-NET-1)

    try:
        oid = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))
        result = get_sync(engine, auth, address, [oid], timeout=0.1, retries=0)
        for vb in result:
            print(f"  {vb.prettyPrint()}")

    except SnmpSyncError as e:
        print(f"SNMP Error (expected): {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    print("SNMP Async Wrapper Examples")
    print("============================")
    print("Note: These examples assume SNMP agent running on 127.0.0.1:161")
    print("Modify the target address to test against your SNMP agent.")

    # Run examples (comment out those that require a running SNMP agent)
    example_basic_get()
    # example_basic_set()  # Requires write access (private community)
    example_client_class()
    example_async_context()
    example_error_handling()

    # Clean up the background event loop thread
    print("\nShutting down...")
    shutdown_sync_wrapper()
    print("Done!")
