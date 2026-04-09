#!/usr/bin/env python3
"""
Test script to perform SNMP GET on sysDescr.0.
"""

import argparse
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    get_cmd,
)
from pysnmp.smi.rfc1902 import ObjectType, ObjectIdentity


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SNMP GET sysDescr.0 smoke test")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP target host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP target UDP port")
    parser.add_argument("--community", default="public", help="SNMP community string")
    parser.add_argument(
        "--snmp-version",
        choices=("v1", "v2c"),
        default="v2c",
        help="SNMP version to use",
    )
    return parser


async def test_get_sysdescr(host: str, port: int, community: str, snmp_version: str) -> bool:
    """Test SNMP GET for sysDescr.0"""

    oid = "1.3.6.1.2.1.1.1.0"  # sysDescr.0
    mp_model = 0 if snmp_version == "v1" else 1

    print(f"Testing SNMP GET for {oid} from {host}:{port}")
    print(f"Community: {community} (SNMP {snmp_version})")
    print()

    try:
        # Perform SNMP GET
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=mp_model),
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
    args = _build_parser().parse_args()
    success = asyncio.run(
        test_get_sysdescr(
            host=args.host,
            port=args.port,
            community=args.community,
            snmp_version=args.snmp_version,
        )
    )
    exit(0 if success else 1)
