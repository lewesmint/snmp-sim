#!/usr/bin/env python3
"""
Minimal script to send a coldStart SNMP trap.

This script sends an SNMPv2c coldStart notification using PySNMP v7+.
Mandatory SNMPv2 varbinds (sysUpTime.0 and snmpTrapOID.0) are generated
automatically by NotificationType.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    SnmpEngine,
    UdpTransportTarget,
    NotificationType,
    ObjectIdentity,
    send_notification,
)


async def send_coldstart_trap(destination: str, port: int) -> None:
    error_indication, error_status, error_index, _ = await send_notification(
        SnmpEngine(),
        CommunityData("public"),
        await UdpTransportTarget.create((destination, port)),
        ContextData(),
        "trap",
        NotificationType(
            ObjectIdentity("SNMPv2-MIB", "coldStart")
        ),
    )

    if error_indication:
        print(f"Trap send error: {error_indication}", file=sys.stderr)
        sys.exit(1)
    if error_status:
        print(
            f"Trap send error: {error_status} at {error_index}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"coldStart trap sent to {destination}:{port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a coldStart SNMP trap")
    parser.add_argument("destination", help="Destination IP address or hostname")
    parser.add_argument("port", type=int, help="Destination port")
    args = parser.parse_args()

    asyncio.run(send_coldstart_trap(args.destination, args.port))

if __name__ == "__main__":
    main()