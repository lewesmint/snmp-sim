#!/usr/bin/env python3
"""Test if pysnmp ObjectIdentity accepts MIB names"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
)


async def test_mib_name() -> None:
    """Test GET with MIB name instead of numeric OID"""
    print("\nTesting pysnmp ObjectIdentity with MIB names:\n")

    test_cases = [
        ("sysDescr.0", "sysDescr.0"),
        ("SNMPv2-MIB::sysDescr.0", "SNMPv2-MIB::sysDescr.0"),
        ("1.3.6.1.2.1.1.1.0", "Numeric OID (control)"),
    ]

    for oid_str, description in test_cases:
        print(f"Testing: {description:40} | OID: '{oid_str}'")
        try:
            target = await UdpTransportTarget.create(("127.0.0.1", 161))
            errorIndication, errorStatus, _, varBinds = await get_cmd(
                SnmpEngine(),
                CommunityData("public", mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid_str)),
            )

            if errorIndication:
                print(f"  Result: ❌ Error: {errorIndication}")
            elif errorStatus:
                print(f"  Result: ❌ Status error: {errorStatus}")
            elif varBinds:
                value = str(varBinds[0][1])[:60]
                print(f"  Result: ✅ Success! Got: {value}...")
            else:
                print("  Result: ❌ No results")
        except Exception as e:
            print(f"  Result: ❌ Exception: {type(e).__name__}: {str(e)[:60]}")

        print()


asyncio.run(test_mib_name())
