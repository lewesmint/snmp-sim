"""SNMP Trap Receiver for monitoring incoming traps."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Callable
from datetime import datetime
from threading import Thread

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
)
from pysnmp.entity import config
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv

from app.app_logger import AppLogger
from app.oid_utils import oid_tuple_to_str


class TrapReceiver:
    """SNMP Trap Receiver that listens for incoming traps."""

    # Standard SNMP OIDs
    SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
    SNMP_TRAP_OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)

    # Test trap OID - we'll use this to identify test traps from the UI
    TEST_TRAP_OID = (1, 3, 6, 1, 4, 1, 99999, 0, 1)

    def __init__(
        self,
        port: int = 16662,
        community: str = "public",
        logger: Optional[logging.Logger] = None,
        on_trap_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        """
        Initialize the trap receiver.

        Args:
            port: UDP port to listen on (default: 16662 for GUI, not 162 for production)
            community: SNMPv2c community string to accept
            logger: Optional logger instance
            on_trap_callback: Optional callback function called when trap is received
        """
        self.port = port
        self.community = community
        self.logger = logger or AppLogger.get(__name__)
        self.on_trap_callback = on_trap_callback

        self.snmp_engine: Optional[SnmpEngine] = None
        self.running = False
        self.thread: Optional[Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Store received traps
        self.received_traps: list[dict[str, Any]] = []
        self.max_traps = 100  # Keep last 100 traps

    def start(self) -> None:
        """Start the trap receiver in a background thread."""
        if self.running:
            self.logger.warning("Trap receiver already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_receiver, daemon=True)
        self.thread.start()
        self.logger.info(f"Trap receiver started on port {self.port}")

    def stop(self) -> None:
        """Stop the trap receiver."""
        if not self.running:
            return

        self.running = False

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.thread:
            self.thread.join(timeout=2.0)

        self.logger.info("Trap receiver stopped")

    def _run_receiver(self) -> None:
        """Run the trap receiver event loop (runs in background thread)."""
        # Create new event loop for this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._async_receiver())
        except Exception as e:
            self.logger.exception(f"Trap receiver error: {e}")
        finally:
            self.loop.close()

    async def _async_receiver(self) -> None:
        """Async trap receiver implementation."""
        # Create SNMP engine
        self.snmp_engine = SnmpEngine()

        # UDP transport
        config.addTransport(
            self.snmp_engine,
            udp.domainName,
            udp.UdpTransport().openServerMode(("0.0.0.0", self.port)),
        )

        # SNMPv2c community
        config.addV1System(self.snmp_engine, "my-area", self.community)

        # Register callback for trap reception
        ntfrcv.NotificationReceiver(self.snmp_engine, self._trap_callback)

        self.logger.info(f"Listening for traps on UDP port {self.port}")
        self.snmp_engine.transportDispatcher.jobStarted(1)

        # Run until stopped
        try:
            while self.running:
                await asyncio.sleep(0.1)
                # Process SNMP engine dispatcher
                self.snmp_engine.transportDispatcher.runDispatcher(timeout=0.1)
        finally:
            if self.snmp_engine:
                try:
                    self.snmp_engine.transportDispatcher.jobFinished(1)
                except Exception:
                    pass
                # Only close dispatcher if event loop is still running
                try:
                    loop = asyncio.get_event_loop()
                    if loop and not loop.is_closed():
                        self.snmp_engine.transportDispatcher.closeDispatcher()
                except RuntimeError:
                    # Event loop already gone, cleanup will happen automatically
                    pass

    def _trap_callback(
        self,
        snmpEngine: Any,
        stateReference: Any,
        contextEngineId: Any,
        contextName: Any,
        varBinds: Any,
        cbCtx: Any,
    ) -> None:
        """Callback invoked when a trap is received."""
        try:
            # Parse varbinds
            trap_data = self._parse_trap(varBinds)

            # Store trap
            self.received_traps.append(trap_data)
            if len(self.received_traps) > self.max_traps:
                self.received_traps.pop(0)  # Remove oldest

            # Log trap
            self.logger.info(
                f"Received trap: {trap_data['trap_oid_str']} "
                f"from {trap_data.get('source', 'unknown')}"
            )

            # Call callback if provided
            if self.on_trap_callback:
                try:
                    self.on_trap_callback(trap_data)
                except Exception as e:
                    self.logger.error(f"Error in trap callback: {e}")

        except Exception as e:
            self.logger.exception(f"Error processing trap: {e}")

    def _parse_trap(self, varBinds: Any) -> dict[str, Any]:
        """Parse trap varbinds into a structured dictionary."""
        timestamp = datetime.now().isoformat()
        uptime = None
        trap_oid = None
        trap_oid_str = "unknown"
        varbinds = []
        is_test_trap = False

        for oid, val in varBinds:
            oid_tuple = tuple(oid)
            oid_str = oid_tuple_to_str(oid_tuple)

            # Extract value
            value_str = str(val)
            if hasattr(val, "prettyPrint"):
                value_str = val.prettyPrint()

            # Check for standard trap OIDs
            if oid_tuple == self.SYS_UPTIME_OID:
                uptime = value_str
            elif oid_tuple == self.SNMP_TRAP_OID:
                trap_oid = tuple(val)  # The value is the trap OID
                trap_oid_str = oid_tuple_to_str(trap_oid)
                # Check if this is a test trap
                if trap_oid == self.TEST_TRAP_OID:
                    is_test_trap = True

            varbinds.append(
                {
                    "oid": oid_tuple,
                    "oid_str": oid_str,
                    "value": value_str,
                    "type": type(val).__name__,
                }
            )

        return {
            "timestamp": timestamp,
            "uptime": uptime,
            "trap_oid": trap_oid,
            "trap_oid_str": trap_oid_str,
            "is_test_trap": is_test_trap,
            "varbinds": varbinds,
            "source": "unknown",  # Could be extracted from transport info if needed
        }

    def get_received_traps(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Get list of received traps (most recent first)."""
        traps = list(reversed(self.received_traps))
        if limit:
            return traps[:limit]
        return traps

    def clear_traps(self) -> None:
        """Clear all received traps."""
        self.received_traps.clear()
        self.logger.info("Cleared all received traps")

    def is_running(self) -> bool:
        """Check if the receiver is running."""
        return self.running
