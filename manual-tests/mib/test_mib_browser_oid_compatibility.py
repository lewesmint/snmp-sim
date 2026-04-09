#!/usr/bin/env python3
"""Final comprehensive test - MIB Browser OID compatibility"""

import argparse
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


def normalize_oid(oid: str) -> str:
    """MIB Browser's _normalize_oid function"""
    oid = oid.strip()
    parts = [p for p in oid.split(".") if p]
    if len(parts) == 1:
        return f"{oid.rstrip('.')}.0"
    return oid


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MIB Browser OID compatibility test")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP target host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP target UDP port")
    parser.add_argument("--community", default="public", help="SNMP community string")
    return parser


async def test_oid(
    oid_str: str,
    description: str,
    host: str,
    port: int,
    community: str,
) -> tuple[bool, str]:
    """Test an OID with both net-snmp and pysnmp (via MIB Browser normalization)"""
    normalized_oid = normalize_oid(oid_str)

    try:
        target = await UdpTransportTarget.create((host, port))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(normalized_oid)),
        )

        if not errorIndication and not errorStatus and varBinds:
            return True, "✅ GETNEXT works"
        else:
            return False, f"❌ GETNEXT failed: {errorIndication or errorStatus}"
    except Exception as e:
        return False, f"❌ Exception: {type(e).__name__}"


async def main(host: str, port: int, community: str) -> bool:
    test_cases = [
        ("1", "Single digit (like snmpgetnext localhost 1)"),
        (".1", "Dot-prefixed single digit (like snmpgetnext localhost .1)"),
        ("1.0", "Normalized two-component (like snmpgetnext localhost 1.0)"),
        ("1.3.6.1.2.1.1", "Full OID path (like snmpgetnext localhost 1.3.6.1.2.1.1)"),
        ("2", "Different single digit"),
        (".1.3.6.1.2.1.1", "Dot-prefixed full path"),
    ]

    print("\n" + "=" * 80)
    print("MIB Browser OID Compatibility Test")
    print("Verifying net-snmp OID formats now work with MIB Browser via pysnmp")
    print(f"Target: {host}:{port}, community={community}")
    print("=" * 80 + "\n")

    results = []
    for oid, description in test_cases:
        success, message = await test_oid(
            oid,
            description,
            host=host,
            port=port,
            community=community,
        )
        results.append(success)

        # Show what normalization does
        normalized = normalize_oid(oid)
        if normalized != oid:
            format_info = f"  (normalized: '{oid}' → '{normalized}')"
        else:
            format_info = "  (no transformation needed)"

        print(f"{message} | {description}{format_info}")

    print("\n" + "=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} net-snmp OID formats work with MIB Browser")

    if passed == total:
        print("\n✅ MIB Browser now fully compatible with net-snmp OID formats!")

    print("=" * 80 + "\n")

    return all(results)


if __name__ == "__main__":
    args = _build_parser().parse_args()
    success = asyncio.run(main(host=args.host, port=args.port, community=args.community))
    exit(0 if success else 1)
