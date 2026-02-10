#!/usr/bin/env python3
"""Test GETNEXT with OID "1" using the new retry logic"""
import asyncio
from typing import Any
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, next_cmd
)

class FakeLogger:
    def log(self, msg: str, level: str = "INFO") -> None:
        print(f"[{level}] {msg}")

async def test_getnext_with_retry() -> bool:
    """Test GETNEXT with OID "1" using retry logic"""
    oid = "1"
    host, port, community = "127.0.0.1", 161, "public"
    logger = FakeLogger()
    
    async def async_next() -> tuple[Any, ...]:
        # next_cmd returns a coroutine that yields ONE result
        from pysnmp.proto.error import StatusInformation
        target = await UdpTransportTarget.create((host, port))
        
        # Try with original OID first
        oid_to_use = oid
        try:
            return await next_cmd(  # type: ignore[no-any-return]
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid_to_use))
            )
        except StatusInformation as e:
            # If serialization error and OID is very short (just "1"), try with ".0"
            error_ind = e.get('errorIndication')
            if (str(error_ind) == "SNMP message serialization error" and 
                oid == "1"):
                try:
                    logger.log("Retrying GETNEXT with normalized OID: 1.0")
                    return await next_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(ObjectIdentity("1.0"))
                    )
                except StatusInformation as retry_e:
                    error_indication = retry_e.get('errorIndication', str(retry_e))
                    return (error_indication, None, None, [])
            else:
                # For other errors, return the error
                error_indication = error_ind or str(e)
                return (error_indication, None, None, [])

    errorIndication, errorStatus, errorIndex, varBinds = await async_next()
    
    print(f"errorIndication: {errorIndication}")
    print(f"errorStatus: {errorStatus}")
    print(f"errorIndex: {errorIndex}")
    print(f"varBinds count: {len(varBinds) if varBinds else 0}")
    
    if not errorIndication and not errorStatus and varBinds:
        for oid_result, value in varBinds:
            print(f"  {oid_result} = {str(value)[:60]}...")
        print("\nTest PASSED - Got valid result")
        return True
    else:
        print("\nTest FAILED - Unexpected response")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_getnext_with_retry())
