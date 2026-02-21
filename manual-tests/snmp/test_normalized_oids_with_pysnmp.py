#!/usr/bin/env python3
"""Test that all normalized OID formats work with pysnmp"""

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
    """Normalize OID to work with pysnmp."""
    oid = oid.strip()
    parts = [p for p in oid.split(".") if p]
    if len(parts) == 1:
        return f"{oid.rstrip('.')}.0"
    return oid


async def test_normalized_oid(oid_str: str) -> bool:
    """Test GETNEXT with normalized OID"""
    normalized = normalize_oid(oid_str)
    print(f"Testing: '{oid_str}' → '{normalized}'", end=" ... ")

    try:
        target = await UdpTransportTarget.create(("127.0.0.1", 161))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData("public", mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(normalized)),
        )

        if errorIndication or errorStatus:
            print("FAIL")
            return False
        else:
            print("SUCCESS")
            return True
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}")
        return False


async def main() -> bool:
    test_cases = [
        "1",  # Single digit
        ".1",  # Dot prefix single digit
        "2",  # Different single digit
        ".2",  # Dot prefix different digit
        "1.0",  # Already normalized
        "1.3.6.1.2.1.1",  # Multi-component OID
        ".1.3.6.1.2.1.1",  # Dot-prefixed multi-component
    ]

    print("\n" + "=" * 70)
    print("Testing Normalized OID Formats with pysnmp")
    print("=" * 70 + "\n")

    results = []
    for oid in test_cases:
        result = await test_normalized_oid(oid)
        results.append(result)

    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} normalized OID formats work with pysnmp")
    print("=" * 70 + "\n")

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
