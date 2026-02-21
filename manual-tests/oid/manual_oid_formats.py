#!/usr/bin/env python3
"""Test different OID formats with pysnmp GETNEXT"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    next_cmd,
)


async def test_oid(oid_str: str) -> bool:
    """Test GETNEXT with given OID string"""
    print(f"\nTesting OID: '{oid_str}'")

    try:
        target = await UdpTransportTarget.create(("127.0.0.1", 161))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData("public", mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid_str)),
        )

        if errorIndication:
            print(f"  Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"  Status error: {errorStatus}")
            return False
        else:
            if varBinds:
                for oid, value in varBinds:
                    print(f"  Result: {oid} = {value}")
                return True
            else:
                print("  No results")
                return False
    except Exception as e:
        print(f"  Exception: {type(e).__name__}: {e}")
        return False


async def main() -> None:
    test_oids = [
        "1",
        "1.0",
        "1.3",
        "1.3.6",
        "1.3.6.1",
        "1.3.6.1.2",
        "1.3.6.1.2.1",
        "1.3.6.1.2.1.1",
    ]

    for oid in test_oids:
        await test_oid(oid)


asyncio.run(main())
