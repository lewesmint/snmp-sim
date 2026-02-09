#!/usr/bin/env python3
"""
Minimal script to send a coldStart SNMP trap.

This script demonstrates sending an SNMPv2c coldStart trap with the proper structure:
1. sysUpTime.0 (mandatory for all SNMPv2c traps)
2. snmpTrapOID.0 (mandatory for all SNMPv2c traps, identifies the trap type)

The coldStart trap (RFC 3418) does not define any additional varbinds.
"""

import argparse
import asyncio
import sys
import warnings

# Workaround for pysnmp 7.1.22 bug - patch missing imports in compiler.py
# See: https://github.com/lextudio/pysnmp/blob/master/pysnmp/smi/compiler.py#L28
try:
    from pysmi.parser.dialect import smiV1Relaxed
    from pysmi.reader.url import getReadersFromUrls
    import pysnmp.smi.compiler
    pysnmp.smi.compiler.smiV1Relaxed = smiV1Relaxed  # pyright: ignore[reportAttributeAccessIssue]
    pysnmp.smi.compiler.getReadersFromUrls = getReadersFromUrls  # pyright: ignore[reportAttributeAccessIssue]
    # Suppress deprecation warnings from pysmi
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="pysmi")
except ImportError:
    pass  # pysmi not installed, MIB compilation won't work but we don't need it

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    SnmpEngine,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.proto import rfc1902


async def send_coldstart_trap(destination: str, port: int) -> None:
    """
    Send a coldStart SNMP trap following SNMPv2c structure.

    Args:
        destination: IP address or hostname of trap receiver
        port: UDP port number (typically 162 for SNMP traps)
    """

    # Standard SNMP OIDs (as tuples to avoid MIB resolution)
    sysUpTime_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)      # SNMPv2-MIB::sysUpTime.0
    snmpTrapOID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)  # SNMPv2-MIB::snmpTrapOID.0
    coldStart_OID = (1, 3, 6, 1, 6, 3, 1, 1, 5, 1)   # SNMPv2-MIB::coldStart

    # Uptime: 100 seconds = 10000 centiseconds
    uptime = 10000

    # Send the trap with proper SNMPv2c structure:
    # 1. sysUpTime.0 (mandatory)
    # 2. snmpTrapOID.0 (mandatory)
    # 3. Additional varbinds (coldStart defines none)
    # pysnmp's type hints are incorrect - it accepts tuples but types say NotificationType
    errorIndication, errorStatus, errorIndex, _ = await send_notification(
        SnmpEngine(),
        CommunityData('public'),  # SNMPv2c community string
        await UdpTransportTarget.create((destination, port)),
        ContextData(),
        'trap',  # Use 'trap' for unconfirmed, 'inform' for confirmed
        # SNMPv2c mandatory varbinds (order matters per RFC 3416)
        (sysUpTime_OID, rfc1902.TimeTicks(uptime)),  # pyright: ignore[reportArgumentType]
        (snmpTrapOID, rfc1902.ObjectIdentifier(coldStart_OID)),  # pyright: ignore[reportArgumentType]
        # coldStart trap defines no additional varbinds
    )

    if errorIndication:
        print(f"Trap send error: {errorIndication}", file=sys.stderr)
        sys.exit(1)
    elif errorStatus:
        print(f"Trap send error: {errorStatus} at {errorIndex}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"coldStart trap sent to {destination}:{port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a coldStart SNMP trap")
    parser.add_argument("destination", help="Destination IP address or hostname")
    parser.add_argument("port", type=int, help="Destination port")
    args = parser.parse_args()

    asyncio.run(send_coldstart_trap(args.destination, args.port))


if __name__ == "__main__":
    main()
