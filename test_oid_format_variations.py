#!/usr/bin/env python3
"""Test different OID formats to understand what works with pysnmp"""
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, next_cmd
)

async def test_oid_format(oid_str: str) -> bool:
    """Test GETNEXT with given OID string"""
    print(f"Testing OID format: '{oid_str}'", end=" ... ")
    
    try:
        target = await UdpTransportTarget.create(("127.0.0.1", 161))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData("public", mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid_str))
        )
        
        if errorIndication or errorStatus:
            print("FAIL (error)")
            return False
        else:
            print("SUCCESS")
            return True
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}")
        return False

async def main() -> None:
    test_cases = [
        "1",        # bare single digit
        ".1",       # dot prefix
        "1.",       # dot suffix
        "1.0",      # two components
        "2",        # different single digit
        "3",        # another single digit
        "2.0",      # two components
        ".1.0",     # dot prefix with two components
    ]
    
    print("\n" + "="*60)
    print("Testing OID Format Variations")
    print("="*60 + "\n")
    
    results = []
    for oid in test_cases:
        result = await test_oid_format(oid)
        results.append(result)
    
    print("\n" + "="*60)
    print(f"Results: {sum(results)}/{len(results)} formats accepted by pysnmp")
    print("="*60 + "\n")

asyncio.run(main())
