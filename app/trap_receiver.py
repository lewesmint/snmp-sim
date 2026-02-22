"""SNMP Trap Receiver for monitoring incoming traps."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterable
from datetime import datetime, timezone
from threading import Thread
from typing import TYPE_CHECKING

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
)

from app.app_logger import AppLogger
from app.oid_utils import oid_tuple_to_str

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable


class TrapReceiver:
    """SNMP Trap Receiver that listens for incoming traps."""

    # Standard SNMP OIDs
    SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
    SNMP_TRAP_OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)

    # Test trap OID - we'll use this to identify test traps from the UI
    TEST_TRAP_OID = (1, 3, 6, 1, 4, 1, 99999, 0, 1)

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 16662,
        community: str = "public",
        logger: logging.Logger | None = None,
        on_trap_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Initialize the trap receiver.

        Args:
            host: IP/hostname interface to bind for trap listening
            port: UDP port to listen on (default: 16662 for GUI, not 162 for production)
            community: SNMPv2c community string to accept
            logger: Optional logger instance
            on_trap_callback: Optional callback function called when trap is received

        """
        self.host = host
        self.port = port
        self.community = community
        self.logger = logger or AppLogger.get(__name__)
        self.on_trap_callback = on_trap_callback

        self.snmp_engine: SnmpEngine | None = None
        self.running = False
        self.thread: Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

        # Store received traps
        self.received_traps: list[dict[str, object]] = []
        self.max_traps = 100  # Keep last 100 traps

    def start(self) -> None:
        """Start the trap receiver in a background thread."""
        if self.running:
            self.logger.warning("Trap receiver already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_receiver, daemon=True)
        self.thread.start()
        self.logger.info("%s", f"Trap receiver started on port {self.port}")

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
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Trap receiver error")
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
            udp.UdpTransport().openServerMode((self.host, self.port)),
        )

        # SNMPv2c community
        config.addV1System(self.snmp_engine, "my-area", self.community)

        # Register callback for trap reception
        ntfrcv.NotificationReceiver(self.snmp_engine, self._trap_callback)

        self.logger.info("%s", f"Listening for traps on UDP port {self.port}")
        self.snmp_engine.transportDispatcher.jobStarted(1)

        # Run until stopped
        try:
            while self.running:
                await asyncio.sleep(0.1)
                # Process SNMP engine dispatcher
                self.snmp_engine.transportDispatcher.runDispatcher(timeout=0.1)
        finally:
            if self.snmp_engine:
                with contextlib.suppress(
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                ):
                    self.snmp_engine.transportDispatcher.jobFinished(1)
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
        _snmp_engine: object,
        _state_reference: object,
        _context_engine_id: object,
        _context_name: object,
        var_binds: Iterable[tuple[object, object]],
        _cb_ctx: object,
    ) -> None:
        """Handle a received trap callback."""
        try:
            # Parse varbinds
            trap_data = self._parse_trap(var_binds)

            # Store trap
            self.received_traps.append(trap_data)
            if len(self.received_traps) > self.max_traps:
                self.received_traps.pop(0)  # Remove oldest

            # Log trap
            self.logger.info(
                "%s", f"Received trap: {trap_data['trap_oid_str']} "
                f"from {trap_data.get('source', 'unknown')}"
            )

            # Call callback if provided
            if self.on_trap_callback:
                try:
                    self.on_trap_callback(trap_data)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    self.logger.exception("Error in trap callback")

        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Error processing trap")

    def _parse_trap(self, var_binds: Iterable[tuple[object, object]]) -> dict[str, object]:
        """Parse trap varbinds into a structured dictionary."""
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        uptime = None
        trap_oid = None
        trap_oid_str = "unknown"
        varbinds = []
        is_test_trap = False

        for oid, val in var_binds:
            if not isinstance(oid, Iterable) or isinstance(oid, (str, bytes, bytearray)):
                continue
            oid_tuple = tuple(part for part in oid if isinstance(part, int))
            if not oid_tuple:
                continue
            oid_str = oid_tuple_to_str(oid_tuple)

            # Extract value
            value_str = str(val)
            pretty_print = getattr(val, "prettyPrint", None)
            if callable(pretty_print):
                try:
                    value_str = str(pretty_print())
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    value_str = str(val)

            # Check for standard trap OIDs
            if oid_tuple == self.SYS_UPTIME_OID:
                uptime = value_str
            elif oid_tuple == self.SNMP_TRAP_OID:
                if isinstance(val, Iterable) and not isinstance(val, (str, bytes, bytearray)):
                    trap_oid = tuple(val)
                else:
                    trap_oid = None
                if trap_oid is not None:
                    trap_oid_str = oid_tuple_to_str(trap_oid)
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

    def get_received_traps(self, limit: int | None = None) -> list[dict[str, object]]:
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
