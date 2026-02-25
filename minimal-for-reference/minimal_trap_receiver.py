"""Minimal PySNMP trap receiver (main + worker thread)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
import signal
import socket
import threading
from collections.abc import Iterable

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

HOST = "0.0.0.0"
PORT = 16662
COMMUNITY = "public"
MAX_LOG_QUEUE = 5_000
SO_RCVBUF_BYTES = 1_048_576  # 1 MiB (OS may clamp)

log = logging.getLogger(__name__)


def _pp(obj: object) -> str:
    """Pretty-print a PySNMP object, falling back to str()."""
    pretty = getattr(obj, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(obj)


def _render_var_binds(var_binds: Iterable[tuple[object, object]]) -> str:
    """Render var-binds using PySNMP's pretty-printer when available."""
    return "trap: " + " | ".join(f"{_pp(oid)}={_pp(val)}" for oid, val in var_binds)


class TrapReceiver:
    """PySNMP trap receiver running in a worker thread.

    Call run() in a dedicated thread; call shutdown() from any thread to stop.
    Received trap strings are posted to log_queue; None is the shutdown sentinel
    and is written exclusively by the worker's finally block.
    """

    def __init__(
        self,
        host: str,
        port: int,
        community: str,
        log_queue: queue.Queue[str | None],
    ) -> None:
        self.host = host
        self.port = port
        self.community = community
        self.log_queue = log_queue

        # Simple counters. Safe because they are only mutated in the worker thread
        # and only read by main after thread.join().
        self.received = 0
        self.dropped_log_messages = 0
        self.callback_errors = 0

        self._engine: SnmpEngine | None = None
        self._engine_lock = threading.Lock()
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Signal the receiver to stop. Safe to call from any thread,
        including signal handlers. Idempotent.

        Does not enqueue the sentinel; that is the worker's job.
        """
        self._stop_event.set()
        with self._engine_lock:
            engine = self._engine

        if engine is not None:
            with contextlib.suppress(AttributeError, OSError):
                engine.transport_dispatcher.close_dispatcher()

    def run(self) -> None:
        """Run the blocking trap dispatcher. Returns only after shutdown()."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            engine = SnmpEngine()
            transport = udp.UdpAsyncioTransport().open_server_mode((self.host, self.port))
            self._tune_rcvbuf(transport)

            config.add_transport(engine, udp.DOMAIN_NAME, transport)
            config.add_v1_system(engine, "my-area", self.community)
            ntfrcv.NotificationReceiver(engine, self._on_trap)

            engine.transport_dispatcher.job_started(1)

            with self._engine_lock:
                self._engine = engine

            if self._stop_event.is_set():
                self.shutdown()
                return

            try:
                engine.transport_dispatcher.run_dispatcher()
            finally:
                self._stop_event.set()
                with self._engine_lock:
                    self._engine = None

                with contextlib.suppress(AttributeError, OSError):
                    engine.transport_dispatcher.job_finished(1)
                with contextlib.suppress(AttributeError, OSError):
                    engine.transport_dispatcher.close_dispatcher()

        except Exception:
            log.exception("Trap receiver worker failed")
            self._stop_event.set()
            with self._engine_lock:
                self._engine = None

        finally:
            # Sentinel written here and only here, after all trap messages have been
            # produced. If the queue is full, main is draining, so this will unblock.
            self.log_queue.put(None)

            asyncio.set_event_loop(None)
            loop.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tune_rcvbuf(self, transport: object) -> None:
        sock = getattr(transport, "socket", None)
        if not isinstance(sock, socket.socket):
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SO_RCVBUF_BYTES)
        except OSError as exc:
            log.warning("Could not set SO_RCVBUF=%d: %s", SO_RCVBUF_BYTES, exc)

    def _on_trap(
        self,
        _engine: object,
        _state_ref: object,
        _ctx_engine_id: object,
        _ctx_name: object,
        var_binds: Iterable[tuple[object, object]],
        _cb_ctx: object,
    ) -> None:
        try:
            message = _render_var_binds(var_binds)
            self.received += 1

            try:
                self.log_queue.put_nowait(message)
            except queue.Full:
                self.dropped_log_messages += 1

        except Exception:  # noqa: BLE001
            self.callback_errors += 1
            log.exception("Unhandled error in trap callback")


def main() -> int:
    """Run trap receiver until interrupted."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    log_queue: queue.Queue[str | None] = queue.Queue(maxsize=MAX_LOG_QUEUE)
    receiver = TrapReceiver(HOST, PORT, COMMUNITY, log_queue)

    def _on_signal(_signum: int, _frame: object) -> None:
        receiver.shutdown()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    thread = threading.Thread(target=receiver.run, name="snmp-trap-worker", daemon=False)
    thread.start()

    log.info("Listening for SNMP traps on %s:%d (community: %s)", HOST, PORT, COMMUNITY)

    try:
        while True:
            msg = log_queue.get()
            if msg is None:
                break
            log.info(msg)
    finally:
        receiver.shutdown()
        thread.join()

        while True:
            try:
                msg = log_queue.get_nowait()
            except queue.Empty:
                break
            if msg is None:
                break
            log.info(msg)

    log.info(
        "Shutdown complete. received=%d dropped_log_messages=%d callback_errors=%d",
        receiver.received,
        receiver.dropped_log_messages,
        receiver.callback_errors,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
