"""SNMP trap sender wrapper using pysnmp.

Note on pysnmp type hints:
    The send_notification() function's type hints are incorrect in pysnmp v7.
    The type signature shows `*varBinds: NotificationType`, but the actual
    implementation and documentation support three formats:
    - Tuples of (OID, value) pairs  <- We use this for flexibility
    - ObjectType instances
    - NotificationType instances

    We use raw tuples because this is a simulator that needs to send arbitrary
    traps with arbitrary varbinds, not just MIB-defined traps. This is the
    correct approach per pysnmp documentation, despite what the type hints say.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal, Optional, Tuple

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    SnmpEngine,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.proto import rfc1902


class TrapSender:
    """Encapsulates SNMP trap sending using pysnmp.

    This implementation follows the SNMPv2c trap structure as demonstrated in
    minimal-for-reference/send_coldstart_trap.py, using direct tuple varbinds
    for maximum flexibility in a simulator context.
    """

    # Standard SNMP OIDs for trap structure
    SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)      # SNMPv2-MIB::sysUpTime.0
    SNMP_TRAP_OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)  # SNMPv2-MIB::snmpTrapOID.0

    def __init__(
        self,
        dest: Tuple[str, int] = ("localhost", 162),
        community: str = "public",
        logger: Optional[logging.Logger] = None,
        start_time: Optional[float] = None,
    ) -> None:
        self.snmpEngine = SnmpEngine()
        self.dest = dest
        self.community = community
        self.logger = logger or logging.getLogger(__name__)
        # Use provided start_time (agent's start time) or current time
        self.start_time = start_time if start_time is not None else time.time()

    def send_trap(
        self,
        oid: Tuple[int, ...],
        value: Any,
        trap_type: Literal["trap", "inform"] = "inform",
        uptime: Optional[int] = None,
    ) -> None:
        """Send an SNMP trap or inform following SNMPv2c structure.

        Args:
            oid: OID tuple identifying the trap or the varbind to send
            value: Value to send with the trap
            trap_type: 'trap' for unconfirmed, 'inform' for confirmed
            uptime: Optional uptime in centiseconds. If None, calculated from start_time
        """
        if trap_type not in ("trap", "inform"):
            self.logger.error(
                f"Invalid trap_type '{trap_type}'. Must be 'trap' or 'inform'."
            )
            return

        try:
            # Calculate uptime if not provided
            if uptime is None:
                uptime_seconds = time.time() - self.start_time
                uptime = int(uptime_seconds * 100)  # Convert to centiseconds

            async def _send() -> Tuple[Optional[str], int, int, Any]:
                # Send trap with proper SNMPv2c structure per RFC 3416:
                # 1. sysUpTime.0 (mandatory)
                # 2. snmpTrapOID.0 (mandatory)
                # 3. Additional varbinds (optional - the actual trap data)

                # Build varbinds as tuples (see module docstring for type hint explanation)
                varbinds = [
                    (self.SYS_UPTIME_OID, rfc1902.TimeTicks(uptime)),
                    (self.SNMP_TRAP_OID, rfc1902.ObjectIdentifier(oid)),
                ]

                # Only add additional varbind if value is provided
                if value is not None:
                    varbinds.append((oid, value))

                result = await send_notification(
                    self.snmpEngine,
                    CommunityData(self.community),
                    await UdpTransportTarget.create(self.dest),
                    ContextData(),
                    trap_type,
                    *varbinds,
                )
                return result

            error_indication, error_status, error_index, _ = asyncio.run(_send())

            if error_indication:
                self.logger.error(f"Trap send error: {error_indication}")
            elif error_status:
                self.logger.error(f"Trap send error: {error_status} at {error_index}")
            else:
                self.logger.info(
                    f"Trap sent to {self.dest} for OID {oid} with value {value}"
                )
        except Exception as exc:  # pragma: no cover - exercised by tests via mock
            self.logger.exception(f"Exception while sending SNMP trap: {exc}")
