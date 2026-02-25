"""Minimal PySNMP trap receiver example (main + worker thread).

This intentionally keeps the structure simple:
- Main thread handles lifecycle
- Worker thread runs an asyncio loop with PySNMP trap receiver
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
import signal
import socket
import threading
from collections.abc import Iterable
from typing import Any

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

HOST = "0.0.0.0"
PORT = 16662
COMMUNITY = "public"
MAX_LOG_QUEUE = 5000
SO_RCVBUF_BYTES = 1_048_576  # 1 MiB (OS may clamp)


def _oid_to_str(oid: Iterable[int]) -> str:
    return ".".join(str(part) for part in oid)


def worker(
    stop_event: threading.Event,
    host: str,
    port: int,
    community: str,
    engine_ref: dict[str, Any],
    log_queue: queue.Queue[str],
    counters: dict[str, int],
) -> None:
    """Run a minimal PySNMP trap listener in a dedicated thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    snmp_engine = SnmpEngine()
    transport = udp.UdpAsyncioTransport().open_server_mode((host, port))
    with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
        sock = getattr(transport, "socket", None)
        if isinstance(sock, socket.socket):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SO_RCVBUF_BYTES)
    config.add_transport(
        snmp_engine,
        udp.DOMAIN_NAME,
        transport,
    )
    config.add_v1_system(snmp_engine, "my-area", community)

    def _callback(
        _snmp_engine: object,
        _state_reference: object,
        _context_engine_id: object,
        _context_name: object,
        var_binds: Iterable[tuple[object, object]],
        _cb_ctx: object,
    ) -> None:
        try:
            rendered = []
            for oid, value in var_binds:
                if isinstance(oid, Iterable) and not isinstance(oid, (str, bytes, bytearray)):
                    oid_tuple = tuple(part for part in oid if isinstance(part, int))
                    oid_str = _oid_to_str(oid_tuple) if oid_tuple else "unknown"
                else:
                    oid_str = "unknown"
                rendered.append(f"{oid_str}={value}")
            message = "trap: " + " | ".join(rendered)
            counters["received"] += 1
            try:
                log_queue.put_nowait(message)
            except queue.Full:
                counters["dropped_log_messages"] += 1
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            counters["callback_errors"] += 1
            logging.exception("Error handling trap")

    ntfrcv.NotificationReceiver(snmp_engine, _callback)
    snmp_engine.transport_dispatcher.job_started(1)
    engine_ref["engine"] = snmp_engine

    try:
        # Blocking dispatcher: no polling/spin loop needed.
        snmp_engine.transport_dispatcher.run_dispatcher()
    finally:
        stop_event.set()
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            snmp_engine.transport_dispatcher.job_finished(1)
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            snmp_engine.transport_dispatcher.close_dispatcher()
        if not loop.is_closed():
            loop.close()


def main() -> int:
    """Start minimal PySNMP receiver and keep running until Ctrl+C."""
    stop_event = threading.Event()
    engine_ref: dict[str, Any] = {"engine": None}
    log_queue: queue.Queue[str] = queue.Queue(maxsize=MAX_LOG_QUEUE)
    counters: dict[str, int] = {
        "received": 0,
        "dropped_log_messages": 0,
        "callback_errors": 0,
    }

    def _shutdown(_signum: int, _frame: object) -> None:
        stop_event.set()
        engine = engine_ref.get("engine")
        if engine is not None:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                engine.transport_dispatcher.close_dispatcher()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    thread = threading.Thread(
        target=worker,
        args=(stop_event, HOST, PORT, COMMUNITY, engine_ref, log_queue, counters),
        daemon=True,
    )
    thread.start()

    print(f"Listening for SNMP traps on {HOST}:{PORT} (community: {COMMUNITY})", flush=True)

    try:
        while thread.is_alive() and not stop_event.is_set():
            try:
                print(log_queue.get(timeout=0.2), flush=True)
            except queue.Empty:
                pass

            thread.join(timeout=0.0)
    finally:
        stop_event.set()

    while True:
        try:
            print(log_queue.get_nowait(), flush=True)
        except queue.Empty:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
