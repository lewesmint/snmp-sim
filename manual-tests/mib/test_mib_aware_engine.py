#!/usr/bin/env python3
"""Test if ObjectIdentity can work with MIB-aware SnmpEngine"""

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


async def test_with_mib_aware_engine() -> None:
    """Test using SnmpEngine with MIB builder"""
    print("\nTesting ObjectIdentity with MIB-aware SnmpEngine:\n")

    # Create SnmpEngine with MIB builder
    snmpEngine = SnmpEngine()
    mibBuilder = snmpEngine.get_mib_builder()

    # Load standard MIBs
    print("Loading SNMPv2-MIB...")
    mibBuilder.load_modules("SNMPv2-MIB")
    print("✅ Loaded\n")

    test_cases = [
        ("sysDescr.0", "Simple name.suffix"),
        ("SNMPv2-MIB::sysDescr.0", "Full module::name.suffix"),
        ("1.3.6.1.2.1.1.1.0", "Numeric OID (control)"),
    ]

    for oid_str, description in test_cases:
        print(f"Testing: {description:30} | '{oid_str}'")
        try:
            target = await UdpTransportTarget.create(("127.0.0.1", 161))
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                snmpEngine,
                CommunityData("public", mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid_str)),
            )

            if errorIndication:
                print(f"  ❌ Error: {str(errorIndication)[:70]}")
            elif errorStatus:
                print(f"  ❌ Status error: {str(errorStatus)}")
            elif varBinds:
                oid_returned = str(varBinds[0][0])
                value = str(varBinds[0][1])[:50]
                print("  ✅ Success!")
                print(f"     OID returned: {oid_returned}")
                print(f"     Value: {value}...")
            else:
                print("  ❌ No results")
        except Exception as e:
            print(f"  ❌ Exception: {type(e).__name__}: {str(e)[:70]}")

        print()


asyncio.run(test_with_mib_aware_engine())
