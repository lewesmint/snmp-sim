"""SNMP trap sender wrapper using pysnmp."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, Optional, Tuple, cast

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    NotificationType,
    SnmpEngine,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.smi import builder


class TrapSender:
    """Encapsulates SNMP trap sending using pysnmp."""

    def __init__(
        self,
        mib_builder: builder.MibBuilder,
        dest: Tuple[str, int] = ("localhost", 162),
        community: str = "public",
        mib_name: str = "__MY_MIB",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.snmpEngine = SnmpEngine()
        self.dest = dest
        self.community = community
        self.mibBuilder = mib_builder
        self.mib_name = mib_name
        self.logger = logger or logging.getLogger(__name__)

    def send_trap(
        self,
        oid: Tuple[int, ...],
        value: Any,
        trap_type: Literal["trap", "inform"] = "inform",
    ) -> None:
        """Send an SNMP trap or inform."""
        if trap_type not in ("trap", "inform"):
            self.logger.error(
                f"Invalid trap_type '{trap_type}'. Must be 'trap' or 'inform'."
            )
            return

        try:
            mib_symbols = self.mibBuilder.import_symbols(self.mib_name, oid)
            mib_symbol = mib_symbols[0]
        except Exception as exc:  # pragma: no cover - exercised by tests via mock
            self.logger.error(f"Failed to import MIB symbol for OID {oid}: {exc}")
            return

        try:
            async def _send() -> Any:
                result = await send_notification(
                    self.snmpEngine,
                    CommunityData(self.community),
                    await UdpTransportTarget.create(self.dest),
                    ContextData(),
                    trap_type,
                    NotificationType(mib_symbol).add_var_binds((oid, value)),
                )
                error_indication = cast(tuple[Optional[str], int, int, list[tuple[Any, Any]]], result)[0]
                return error_indication

            error_indication = asyncio.run(_send())
            if error_indication:
                self.logger.error(f"Trap send error: {error_indication}")
            else:
                self.logger.info(
                    f"Trap sent to {self.dest} for OID {oid} with value {value}"
                )
        except Exception as exc:  # pragma: no cover - exercised by tests via mock
            self.logger.exception(f"Exception while sending SNMP trap: {exc}")
