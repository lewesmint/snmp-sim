#!/usr/bin/env python3
"""
Test script to perform SNMP GET on sysDescr.0 from localhost:161
"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    get_cmd,
)
from pysnmp.smi.rfc1902 import ObjectType, ObjectIdentity


async def test_get_sysdescr() -> bool:
    """Test SNMP GET for sysDescr.0"""

    host = "127.0.0.1"
    port = 161
    community = "public"
    oid = "1.3.6.1.2.1.1.1.0"  # sysDescr.0

    print(f"Testing SNMP GET for {oid} from {host}:{port}")
    print(f"Community: {community}")
    print()

    try:
        # Perform SNMP GET
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=0),  # mpModel=0 for SNMPv1
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        if errorIndication:
            print(f"❌ Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"❌ SNMP Error: {errorStatus} at index {errorIndex}")
            return False
        else:
            print("✅ Success!")
            print()
            print("Results:")
            for varBind in varBinds:
                oid_str = varBind[0].prettyPrint()
                value = varBind[1].prettyPrint()
                print(f"  OID: {oid_str}")
                print(f"  Value: {value}")
                print(f"  Type: {type(varBind[1]).__name__}")
            return True

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_get_sysdescr())
    exit(0 if success else 1)
