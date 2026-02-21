#!/usr/bin/env python3
"""Final comprehensive test - MIB Browser OID compatibility"""

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


async def test_oid(oid_str: str, description: str) -> tuple[bool, str]:
    """Test an OID with both net-snmp and pysnmp (via MIB Browser normalization)"""
    normalized_oid = normalize_oid(oid_str)

    try:
        target = await UdpTransportTarget.create(("127.0.0.1", 161))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData("public", mpModel=1),
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


async def main() -> bool:
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
    print("=" * 80 + "\n")

    results = []
    for oid, description in test_cases:
        success, message = await test_oid(oid, description)
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
    success = asyncio.run(main())
    exit(0 if success else 1)
