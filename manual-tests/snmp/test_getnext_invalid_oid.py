#!/usr/bin/env python3
"""Test GETNEXT with invalid OID to check error handling"""

import asyncio
from typing import Any
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    next_cmd,
)


async def test_getnext_with_invalid_oid() -> bool:
    """Test GETNEXT with OID '1' which is invalid"""
    oid = "1"
    host, port, community = "127.0.0.1", 161, "public"

    async def async_next() -> tuple[Any, ...]:
        # next_cmd returns a coroutine that yields ONE result
        from pysnmp.proto.error import StatusInformation

        target = await UdpTransportTarget.create((host, port))
        try:
            return await next_cmd(  # type: ignore[no-any-return]
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        except StatusInformation as e:
            # Handle serialization errors (e.g., invalid OID format)
            # StatusInformation implements get() method to access error details
            error_indication = e.get("errorIndication", str(e))
            return (error_indication, None, None, [])

    errorIndication, errorStatus, errorIndex, varBinds = await async_next()

    print(f"errorIndication: {errorIndication} (type: {type(errorIndication)})")
    print(f"errorStatus: {errorStatus}")
    print(f"errorIndex: {errorIndex}")
    print(f"varBinds: {varBinds}")

    if errorIndication:
        print(f"\nError caught successfully: {errorIndication}")
        return True
    else:
        print("\nNo error indication - unexpected!")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_getnext_with_invalid_oid())
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
