#!/usr/bin/env python3
"""Test GETNEXT with valid OID to ensure normal operation works"""
import asyncio
from typing import Any
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, next_cmd
)

async def test_getnext_with_valid_oid() -> bool:
    """Test GETNEXT with valid OID"""
    oid = "1.3.6.1.2.1.1"
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
                ObjectType(ObjectIdentity(oid))
            )
        except StatusInformation as e:
            # Handle serialization errors (e.g., invalid OID format)
            # StatusInformation implements get() method to access error details
            error_indication = e.get('errorIndication', str(e))
            return (error_indication, None, None, [])

    errorIndication, errorStatus, errorIndex, varBinds = await async_next()
    
    print(f"errorIndication: {errorIndication}")
    print(f"errorStatus: {errorStatus}")
    print(f"errorIndex: {errorIndex}")
    print(f"varBinds count: {len(varBinds) if varBinds else 0}")
    
    if not errorIndication and not errorStatus and varBinds:
        for oid, value in varBinds:
            print(f"  {oid} = {value}")
        print("\nTest PASSED - Got valid result")
        return True
    else:
        print("\nTest FAILED - Unexpected response")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_getnext_with_valid_oid())
