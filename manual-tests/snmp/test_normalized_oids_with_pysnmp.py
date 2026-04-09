#!/usr/bin/env python3
"""Test that all normalized OID formats work with pysnmp"""

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
    """Normalize OID to work with pysnmp."""
    oid = oid.strip()
    parts = [p for p in oid.split(".") if p]
    if len(parts) == 1:
        return f"{oid.rstrip('.')}.0"
    return oid


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate normalized OID handling via GETNEXT")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP target host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP target UDP port")
    parser.add_argument("--community", default="public", help="SNMP community string")
    return parser


async def test_normalized_oid(oid_str: str, host: str, port: int, community: str) -> bool:
    """Test GETNEXT with normalized OID"""
    normalized = normalize_oid(oid_str)
    print(f"Testing: '{oid_str}' → '{normalized}'", end=" ... ")

    try:
        target = await UdpTransportTarget.create((host, port))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
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


async def main(host: str, port: int, community: str) -> bool:
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
    print(f"Target: {host}:{port}, community={community}")
    print("=" * 70 + "\n")

    results = []
    for oid in test_cases:
        result = await test_normalized_oid(oid, host=host, port=port, community=community)
        results.append(result)

    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} normalized OID formats work with pysnmp")
    print("=" * 70 + "\n")

    return all(results)


if __name__ == "__main__":
    args = _build_parser().parse_args()
    success = asyncio.run(main(host=args.host, port=args.port, community=args.community))
    exit(0 if success else 1)
