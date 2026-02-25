"""SNMP Trap Receiver for monitoring incoming traps (worker + sentinel pipeline).

Philosophy:
- Worker thread owns PySNMP dispatcher and networking.
- Worker callback is fast: capture minimal data and enqueue, never blocks.
- Main thread (consumer) does all heavy work: parsing, source extraction, logging,
  history retention, user callbacks.
- Shutdown is deterministic:
  - main requests stop by closing dispatcher
  - worker exits and enqueues exactly one sentinel (None)
  - main consumes until sentinel, then joins worker

Queue contract:
- Items are TrapEvent instances produced by the worker.
- Exactly one None is produced by the worker at shutdown.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import queue
import signal
import socket
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

DEFAULT_HOST = "0.0.0.0"  # noqa: S104
DEFAULT_PORT = 16662
DEFAULT_COMMUNITY = "public"
MAX_QUEUE = 5_000
SO_RCVBUF_BYTES = 1_048_576  # 1 MiB (OS may clamp)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    """Configuration for TrapReceiver."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    community: str = DEFAULT_COMMUNITY


def _pp(obj: object) -> str:
    """Pretty-print a PySNMP object, falling back to str()."""
    pretty = getattr(obj, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(obj)


def _oid_tuple_to_str(oid: Iterable[int]) -> str:
    return ".".join(str(part) for part in oid)


@dataclass(frozen=True, slots=True)
class TrapEvent:
    """Raw trap event captured in the worker thread, parsed in the main thread."""

    captured_at_utc: str
    transport_domain: object
    transport_address: object
    var_binds: tuple[tuple[object, object], ...]


ParsedTrap = dict[str, Any]


class TrapReceiver:
    """SNMP Trap Receiver that listens for incoming traps in a worker thread.

    Public API:
      - start(): starts the background worker thread
      - stop(): requests shutdown and waits for the worker to finish; drains
                the queue so stop() is safe even when run_forever() is not active.
                Do not call from a signal handler — use _request_shutdown() instead.
      - run_forever(): consume events in the calling thread until shutdown

    Monitoring features:
      - stores last max_traps parsed traps in memory (owned by consumer thread)
      - calls on_trap_callback(trap_dict) from the consumer thread (not the worker)
    """

    SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
    SNMP_TRAP_OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)
    TRANSPORT_INFO_TUPLE_LENGTH = 2
    TRANSPORT_ADDRESS_TUPLE_LENGTH = 2

    def __init__(
        self,
        # FIX 1: renamed 'config' -> 'cfg' to avoid shadowing pysnmp.entity.config
        cfg: ReceiverConfig | None = None,
        *,
        max_traps: int = 100,
        logger: logging.Logger | None = None,
        on_trap_callback: Callable[[ParsedTrap], None] | None = None,
        queue_maxsize: int = MAX_QUEUE,
    ) -> None:
        """Initialize TrapReceiver."""
        if cfg is None:
            cfg = ReceiverConfig()
        self.host = cfg.host
        self.port = cfg.port
        self.community = cfg.community
        self.logger = logger or logging.getLogger(__name__)
        self.on_trap_callback = on_trap_callback
        self._queue: queue.Queue[TrapEvent | None] = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._engine: SnmpEngine | None = None
        self._engine_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self.received = 0
        self.dropped_events = 0
        self.parse_errors = 0
        self._history: deque[ParsedTrap] = deque(maxlen=max_traps)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background worker thread."""
        if self._worker is not None and self._worker.is_alive():
            self.logger.warning("Trap receiver already running")
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._worker_main,
            name="snmp-trap-worker",
            daemon=False,
        )
        self._worker.start()
        self.logger.info("Trap receiver started on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Request shutdown and wait for the worker to finish.

        Drains queued events so the worker's final blocking put(None) always
        gets through, even when no other consumer is running. Safe to call
        from a separate thread, but do not call concurrently with run_forever()
        or from a signal handler — use _request_shutdown() for those cases.
        """
        self._request_shutdown()
        # FIX 2: act as a consumer while waiting so the worker's blocking
        # put(None) always has room, even when run_forever() is not active.
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                worker = self._worker
                if worker is None or not worker.is_alive():
                    break
                continue
            if item is None:
                break
            self._process_trap_item(item)
        if self._worker is not None:
            self._worker.join()
        self.logger.info("Trap receiver stopped")

    def run_forever(self, poll_interval_s: float = 0.0) -> None:
        """Consume events until shutdown sentinel is received.

        If you want the component style start/stop, call start() then this
        in the main thread, and use _request_shutdown() from signal handlers.
        """
        if self._worker is None or not self._worker.is_alive():
            self.start()
        self._consume_until_sentinel(poll_interval_s=poll_interval_s)

    # ------------------------------------------------------------------
    # Introspection / history
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Report whether the receiver is running."""
        worker = self._worker
        return worker is not None and worker.is_alive() and not self._stop_event.is_set()

    def get_received_traps(self, limit: int | None = None) -> list[ParsedTrap]:
        """Return received traps in reverse chronological order.

        Safe because history is only mutated by the consumer thread (typically main).
        """
        traps = list(reversed(self._history))
        if limit is not None:
            return traps[:limit]
        return traps

    def clear_traps(self) -> None:
        """Clear all stored traps from in-memory history."""
        self._history.clear()
        self.logger.info("Cleared all received traps")

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def request_shutdown(self) -> None:
        """Non-blocking shutdown request. Safe to call from signal handlers."""
        self._request_shutdown()

    def _request_shutdown(self) -> None:
        """Non-blocking shutdown request. Safe to call from signal handlers."""
        self._stop_event.set()
        with self._engine_lock:
            engine = self._engine
        if engine is not None:
            with contextlib.suppress(AttributeError, OSError):
                engine.transport_dispatcher.close_dispatcher()

    def _worker_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine = SnmpEngine()
            transport = udp.UdpAsyncioTransport().open_server_mode((self.host, self.port))
            self._tune_rcvbuf(transport)
            config.add_transport(engine, udp.DOMAIN_NAME, transport)
            config.add_v1_system(engine, "my-area", self.community)
            ntfrcv.NotificationReceiver(engine, self._on_trap_worker)
            engine.transport_dispatcher.job_started(1)
            with self._engine_lock:
                self._engine = engine
            if self._stop_event.is_set():
                return
            try:
                # Blocking call. Shutdown happens via close_dispatcher().
                engine.transport_dispatcher.run_dispatcher()
            finally:
                with contextlib.suppress(AttributeError, OSError):
                    engine.transport_dispatcher.job_finished(1)
                with contextlib.suppress(AttributeError, OSError):
                    engine.transport_dispatcher.close_dispatcher()
        except Exception:
            self.logger.exception("Trap receiver worker failed")
        finally:
            self._stop_event.set()
            with self._engine_lock:
                self._engine = None
            # Producer-only sentinel: written exactly once, after all trap
            # messages have been enqueued. Blocks if the queue is full, relying
            # on the consumer (run_forever or stop()) to drain and make room.
            self._queue.put(None)
            asyncio.set_event_loop(None)
            loop.close()

    def _on_trap_worker(
        self,
        snmp_engine: object,
        state_reference: object,
        _context_engine_id: object,
        _context_name: object,
        var_binds: Iterable[tuple[object, object]],
        _cb_ctx: object,
    ) -> None:
        """Worker-thread callback: capture minimal data and enqueue quickly."""
        try:
            captured_at_utc = datetime.now(tz=timezone.utc).isoformat()
            transport_domain: object = "unknown"
            transport_address: object = "unknown"
            # Best-effort transport info extraction; keep it cheap.
            md = (
                getattr(snmp_engine, "message_dispatcher", None)
                or getattr(snmp_engine, "msgAndPduDsp", None)
            )
            getter = (
                getattr(md, "get_transport_info", None)
                or getattr(md, "getTransportInfo", None)
            )
            if callable(getter):
                with contextlib.suppress(Exception):
                    info = getter(state_reference)
                    if isinstance(info, tuple) and len(info) == self.TRANSPORT_INFO_TUPLE_LENGTH:
                        transport_domain, transport_address = info[0], info[1]
            event = TrapEvent(
                captured_at_utc=captured_at_utc,
                transport_domain=transport_domain,
                transport_address=transport_address,
                var_binds=tuple(var_binds),
            )
            self.received += 1
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self.dropped_events += 1
        except Exception:
            # Never allow callback exceptions to break reception.
            self.parse_errors += 1
            self.logger.exception("Unhandled error in worker trap callback")

    def _tune_rcvbuf(self, transport: object) -> None:
        sock = getattr(transport, "socket", None)
        if not isinstance(sock, socket.socket):
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SO_RCVBUF_BYTES)
        except OSError as exc:
            self.logger.warning("Could not set SO_RCVBUF=%d: %s", SO_RCVBUF_BYTES, exc)

    # ------------------------------------------------------------------
    # Consumer (main thread)
    # ------------------------------------------------------------------

    def _try_get_queue_item(self, poll_interval_s: float) -> tuple[TrapEvent | None, bool]:
        """Get item from queue with optional polling.

        Returns
        -------
            Tuple of (item, should_continue) where should_continue indicates
            whether to continue the loop without processing.

        """
        if poll_interval_s > 0.0:
            try:
                item = self._queue.get(timeout=poll_interval_s)
            except queue.Empty:
                return (None, True)
            else:
                return (item, False)
        else:
            item = self._queue.get()
            return (item, False)

    def _process_trap_item(self, item: TrapEvent) -> None:
        """Process a single trap item."""
        # FIX 4: catch parse errors so a malformed trap doesn't crash the consumer
        try:
            trap = self._parse_trap_event(item)
        except Exception:
            self.parse_errors += 1
            self.logger.exception("Error parsing trap event")
            return
        self._history.append(trap)
        self._log_trap(trap)
        if self.on_trap_callback is not None:
            try:
                self.on_trap_callback(trap)
            except Exception:
                self.logger.exception("Error in on_trap_callback")

    def _drain_remaining_queue(self) -> None:
        """Drain any remaining queued items after shutdown."""
        while True:
            try:
                leftover = self._queue.get_nowait()
            except queue.Empty:
                break
            if leftover is None:
                break
            trap = self._parse_trap_event(leftover)
            self._history.append(trap)
            self._log_trap(trap)

    def _consume_until_sentinel(self, poll_interval_s: float = 0.0) -> None:
        """Consume events until None sentinel is received."""
        self.logger.info("Listening for traps on UDP %s:%d", self.host, self.port)
        try:
            while True:
                item, should_continue = self._try_get_queue_item(poll_interval_s)
                if should_continue:
                    continue
                if item is None:
                    break
                self._process_trap_item(item)
        finally:
            # Ensure shutdown is requested and worker is joined.
            self._request_shutdown()
            worker = self._worker
            if worker is not None:
                worker.join()
            self._drain_remaining_queue()

    def _format_transport_address(self, transport_address: object) -> str:
        if (
            isinstance(transport_address, tuple)
            and len(transport_address) >= self.TRANSPORT_ADDRESS_TUPLE_LENGTH
        ):
            return f"{transport_address[0]}:{transport_address[1]}"
        return str(transport_address)

    def _parse_trap_event(self, event: TrapEvent) -> ParsedTrap:
        """Parse a TrapEvent into a structured dict."""
        uptime: str | None = None
        trap_oid: tuple[int, ...] | None = None
        trap_oid_str = "unknown"
        varbinds: list[dict[str, object]] = []

        for oid, val in event.var_binds:
            oid_str = _pp(oid)
            value_str = _pp(val)
            oid_tuple: tuple[int, ...] | None = None
            # Attempt to build an integer OID tuple for comparisons.
            if isinstance(oid, Iterable) and not isinstance(oid, (str, bytes, bytearray)):
                parts = [p for p in oid if isinstance(p, int)]
                if parts:
                    oid_tuple = tuple(parts)
            if oid_tuple == self.SYS_UPTIME_OID:
                uptime = value_str
            if (
                oid_tuple == self.SNMP_TRAP_OID
                and isinstance(val, Iterable)
                and not isinstance(val, (str, bytes, bytearray))
            ):
                trap_parts = [p for p in val if isinstance(p, int)]
                if trap_parts:
                    trap_oid = tuple(trap_parts)
                    trap_oid_str = _oid_tuple_to_str(trap_oid)
            varbinds.append(
                {
                    "oid": oid_tuple,
                    "oid_str": oid_str,
                    "value": value_str,
                    "type": type(val).__name__,
                }
            )

        source = self._format_transport_address(event.transport_address)
        return {
            "timestamp": event.captured_at_utc,
            "uptime": uptime,
            "trap_oid": trap_oid,
            "trap_oid_str": trap_oid_str,
            "varbinds": varbinds,
            "source": source,
        }

    def _log_trap(self, trap: ParsedTrap) -> None:
        trap_oid_str = trap.get("trap_oid_str", "unknown")
        source = trap.get("source", "unknown")
        uptime = trap.get("uptime", "unknown")
        varbinds = trap.get("varbinds", [])
        vb_count = len(varbinds) if isinstance(varbinds, list) else 0
        self.logger.info("Received trap: %s from %s", trap_oid_str, source)
        self.logger.info("Trap details: uptime=%s varbind_count=%d", uptime, vb_count)


def main(argv: Iterable[str] | None = None) -> int:
    """Run trap receiver until interrupted."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Run SNMP trap receiver and log incoming traps",
        epilog="Example: %(prog)s --host 0.0.0.0 --port 162 --community public",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to listen on")
    parser.add_argument("--community", default=DEFAULT_COMMUNITY, help="SNMPv2c community")
    parser.add_argument("--max-traps", type=int, default=100, help="Keep last N traps in memory")
    args = parser.parse_args(list(argv) if argv is not None else None)

    receiver = TrapReceiver(
        cfg=ReceiverConfig(  # FIX 1: cfg= not config=
            host=args.host,
            port=args.port,
            community=args.community,
        ),
        max_traps=args.max_traps,
        logger=logging.getLogger("snmp_trap_receiver"),
    )

    def _on_signal(_signum: int, _frame: object) -> None:
        # FIX 3: non-blocking; run_forever()'s finally handles join and drain
        receiver.request_shutdown()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    receiver.start()
    receiver.run_forever()

    log.info(
        "Shutdown complete. received=%d dropped_events=%d parse_errors=%d",
        receiver.received,
        receiver.dropped_events,
        receiver.parse_errors,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["ReceiverConfig", "TrapEvent", "TrapReceiver", "main"]
