"""Quick test of PySNMP 7.x API"""

import asyncio
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)


async def test_snmp_get() -> None:
    """Test basic SNMP GET with PySNMP 7.x"""
    engine = SnmpEngine()
    auth = CommunityData("public", mpModel=1)

    # Create transport target (async in PySNMP 7.x)
    target = await UdpTransportTarget.create(("127.0.0.1", 161), timeout=2.0, retries=1)

    # Create OID
    oid = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))

    # Perform GET
    errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
        engine, auth, target, ContextData(), oid
    )

    print(f"errorIndication: {errorIndication}")
    print(f"errorStatus: {errorStatus}")
    print(f"errorIndex: {errorIndex}")
    print("varBinds:")
    for vb in varBinds:
        print(f"  {vb.prettyPrint()}")


if __name__ == "__main__":
    asyncio.run(test_snmp_get())
