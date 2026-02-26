"""SNMP Trap Receiver for monitoring incoming traps."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from threading import Thread
from typing import cast

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine

TransportInfoGetter = Callable[[object], object]
ExecutionContextGetter = Callable[[str], object]
BASE_CONTEXT_EXCEPTIONS = (AttributeError, LookupError)
SOURCE_CONTEXT_EXCEPTIONS = (
    *BASE_CONTEXT_EXCEPTIONS,
    OSError,
    TypeError,
    ValueError,
)


def _oid_tuple_to_str(oid: Iterable[int]) -> str:
    return ".".join(str(part) for part in oid)


class TrapReceiver:
    """SNMP Trap Receiver that listens for incoming traps."""

    SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
    SNMP_TRAP_OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)
    TEST_TRAP_OID = (1, 3, 6, 1, 4, 1, 99999, 0, 1)
    TRANSPORT_INFO_PAIR_LEN = 2

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 16662,
        community: str = "public",
        logger: logging.Logger | None = None,
        on_trap_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Initialize TrapReceiver."""
        self.host = host
        self.port = port
        self.community = community
        self.logger = logger or logging.getLogger(__name__)
        self.on_trap_callback = on_trap_callback

        self.snmp_engine: SnmpEngine | None = None
        self.running = False
        self.thread: Thread | None = None

        self.received_traps: list[dict[str, object]] = []
        self.max_traps = 100

    def start(self) -> None:
        """Start the background trap listener thread."""
        if self.running:
            self.logger.warning("Trap receiver already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_receiver, daemon=True)
        self.thread.start()
        self.logger.info("%s", f"Trap receiver started on port {self.port}")

    def stop(self) -> None:
        """Stop the trap listener thread and close the dispatcher."""
        if not self.running:
            return

        self.running = False
        if self.snmp_engine:
            dispatcher = getattr(self.snmp_engine, "transport_dispatcher", None)
            close_dispatcher = (
                getattr(dispatcher, "close_dispatcher", None)
                if dispatcher is not None
                else None
            )
            if not callable(close_dispatcher) and dispatcher is not None:
                close_dispatcher = getattr(dispatcher, "closeDispatcher", None)
            if callable(close_dispatcher):
                with contextlib.suppress(
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                ):
                    close_dispatcher()
        if self.thread:
            self.thread.join(timeout=3.0)

        self.logger.info("Trap receiver stopped")

    def _run_receiver(self) -> None:
        event_loop: asyncio.AbstractEventLoop | None = None
        try:
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
            self.snmp_engine = SnmpEngine()
            add_transport = getattr(config, "add_transport", None)
            if not callable(add_transport):
                add_transport = getattr(config, "addTransport", None)
            if not callable(add_transport):
                raise RuntimeError("pysnmp config missing add_transport")

            self._add_udp_transport(
                add_transport=add_transport,
                transport_module=udp,
                bind_host=self.host,
                bind_port=self.port,
            )

            add_v1_system = getattr(config, "add_v1_system", None)
            if not callable(add_v1_system):
                add_v1_system = getattr(config, "addV1System", None)
            if not callable(add_v1_system):
                raise RuntimeError("pysnmp config missing add_v1_system")

            add_v1_system(self.snmp_engine, "my-area", self.community)
            ntfrcv.NotificationReceiver(self.snmp_engine, self._trap_callback)

            self.logger.info("%s", f"Listening for traps on UDP port {self.port}")

            dispatcher = getattr(self.snmp_engine, "transport_dispatcher", None)
            if dispatcher is None:
                dispatcher = getattr(self.snmp_engine, "transportDispatcher", None)
            if dispatcher is None:
                raise RuntimeError("pysnmp engine missing transport dispatcher")

            job_started = getattr(dispatcher, "job_started", None)
            if not callable(job_started):
                job_started = getattr(dispatcher, "jobStarted", None)
            if callable(job_started):
                job_started(1)

            run_dispatcher = getattr(dispatcher, "run_dispatcher", None)
            if not callable(run_dispatcher):
                run_dispatcher = getattr(dispatcher, "runDispatcher", None)
            if not callable(run_dispatcher):
                raise RuntimeError("pysnmp dispatcher missing run_dispatcher")

            run_dispatcher()
        except RuntimeError as error:
            if "Event loop stopped before Future completed" not in str(error):
                self.logger.exception("Trap receiver error")
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Trap receiver error")
        finally:
            if self.snmp_engine:
                dispatcher = getattr(self.snmp_engine, "transport_dispatcher", None)
                if dispatcher is None:
                    dispatcher = getattr(self.snmp_engine, "transportDispatcher", None)
                if dispatcher is not None:
                    job_finished = getattr(dispatcher, "job_finished", None)
                    if not callable(job_finished):
                        job_finished = getattr(dispatcher, "jobFinished", None)
                    if callable(job_finished):
                        with contextlib.suppress(
                            AttributeError,
                            LookupError,
                            OSError,
                            TypeError,
                            ValueError,
                        ):
                            job_finished(1)
                    close_dispatcher = getattr(dispatcher, "close_dispatcher", None)
                    if not callable(close_dispatcher):
                        close_dispatcher = getattr(dispatcher, "closeDispatcher", None)
                    if callable(close_dispatcher):
                        with contextlib.suppress(
                            AttributeError,
                            LookupError,
                            OSError,
                            TypeError,
                            ValueError,
                        ):
                            close_dispatcher()
            if event_loop is not None:
                with contextlib.suppress(RuntimeError):
                    if not event_loop.is_closed():
                        event_loop.close()
            self.running = False

    def _add_udp_transport(
        self,
        *,
        add_transport: Callable[[SnmpEngine, object, object], None],
        transport_module: object,
        bind_host: str,
        bind_port: int,
    ) -> None:
        transport_cls = getattr(transport_module, "UdpAsyncioTransport", None)
        if transport_cls is None:
            transport_cls = getattr(transport_module, "UdpTransport", None)
        if transport_cls is None:
            raise RuntimeError("No compatible UDP transport found for pysnmp")

        transport = transport_cls()
        open_server_mode = getattr(transport, "open_server_mode", None)
        if not callable(open_server_mode):
            open_server_mode = getattr(transport, "openServerMode", None)
        if not callable(open_server_mode):
            raise RuntimeError("UDP transport missing open_server_mode")

        transport = open_server_mode((bind_host, bind_port))

        domain_name = getattr(transport_module, "DOMAIN_NAME", None)
        if domain_name is None:
            domain_name = getattr(transport_module, "domainName", None)

        add_transport(self.snmp_engine, domain_name, transport)


    def _trap_callback(
        self,
        snmp_engine: object,
        state_reference: object,
        _context_engine_id: object,
        _context_name: object,
        var_binds: Iterable[tuple[object, object]],
        _cb_ctx: object,
    ) -> None:
        try:
            source = self._extract_source(snmp_engine, state_reference)
            trap_data = self._parse_trap(var_binds, source=source)

            self.received_traps.append(trap_data)
            if len(self.received_traps) > self.max_traps:
                self.received_traps.pop(0)

            self.logger.info(
                "%s", f"Received trap: {trap_data['trap_oid_str']} "
                f"from {trap_data.get('source', 'unknown')}"
            )
            self.logger.info(
                "%s",
                "Trap details: "
                f"uptime={trap_data.get('uptime', 'unknown')}, "
                f"varbind_count={self._varbind_count(trap_data)}, "
                f"varbinds={self._format_varbinds_for_log(trap_data)}",
            )

            if self.on_trap_callback:
                try:
                    self.on_trap_callback(trap_data)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    self.logger.exception("Error in trap callback")

        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Error processing trap")

    def _format_varbinds_for_log(self, trap_data: dict[str, object]) -> str:
        raw_varbinds = trap_data.get("varbinds", [])
        if not isinstance(raw_varbinds, list) or not raw_varbinds:
            return "none"

        rendered_varbinds: list[str] = []
        for varbind in raw_varbinds:
            if not isinstance(varbind, dict):
                continue
            oid_str = str(varbind.get("oid_str", "unknown"))
            value = str(varbind.get("value", ""))
            rendered_varbinds.append(f"{oid_str}={value}")

        if not rendered_varbinds:
            return "none"
        return " | ".join(rendered_varbinds)

    def _varbind_count(self, trap_data: dict[str, object]) -> int:
        raw_varbinds = trap_data.get("varbinds")
        if isinstance(raw_varbinds, list):
            return len(raw_varbinds)
        return 0

    def _format_transport_address(self, transport_address: object) -> str:
        if (
            isinstance(transport_address, tuple)
            and len(transport_address) >= self.TRANSPORT_INFO_PAIR_LEN
        ):
            return f"{transport_address[0]}:{transport_address[1]}"
        return str(transport_address)

    def _get_transport_info_getter(self, snmp_engine: object) -> TransportInfoGetter | None:
        message_dispatcher = getattr(snmp_engine, "message_dispatcher", None)
        if message_dispatcher is None:
            message_dispatcher = getattr(snmp_engine, "msgAndPduDsp", None)
        if message_dispatcher is None:
            return None

        getter = getattr(message_dispatcher, "get_transport_info", None)
        if callable(getter):
            return cast("TransportInfoGetter", getter)

        legacy_getter = getattr(message_dispatcher, "getTransportInfo", None)
        if callable(legacy_getter):
            return cast("TransportInfoGetter", legacy_getter)

        return None

    def _extract_source_from_transport_info(
        self,
        snmp_engine: object,
        state_reference: object,
    ) -> str | None:
        get_transport_info = self._get_transport_info_getter(snmp_engine)
        if not callable(get_transport_info):
            return None

        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            transport_info = get_transport_info(state_reference)
            if (
                isinstance(transport_info, tuple)
                and len(transport_info) == self.TRANSPORT_INFO_PAIR_LEN
            ):
                return self._format_transport_address(transport_info[1])

        return None

    def _get_execution_context_getter(
        self,
        snmp_engine: object,
    ) -> ExecutionContextGetter | None:
        observer = getattr(snmp_engine, "observer", None)
        if observer is None:
            return None

        getter = getattr(observer, "get_execution_context", None)
        if callable(getter):
            return cast("ExecutionContextGetter", getter)

        legacy_getter = getattr(observer, "getExecutionContext", None)
        if callable(legacy_getter):
            return cast("ExecutionContextGetter", legacy_getter)

        return None

    def _extract_source_from_observer(self, snmp_engine: object) -> str | None:
        get_execution_context = self._get_execution_context_getter(snmp_engine)
        if not callable(get_execution_context):
            return None

        execution_points = (
            "rfc3412.receiveMessage:request",
            "rfc3412.receiveMessage:response",
            "rfc2576.processIncomingMsg",
        )
        for execution_point in execution_points:
            with contextlib.suppress(*SOURCE_CONTEXT_EXCEPTIONS):
                context = get_execution_context(execution_point)
                if not isinstance(context, dict):
                    continue
                transport_address = context.get("transportAddress")
                if transport_address is not None:
                    return self._format_transport_address(transport_address)
                transport_information = context.get("transportInformation")
                if (
                    isinstance(transport_information, tuple)
                    and len(transport_information) == self.TRANSPORT_INFO_PAIR_LEN
                ):
                    return self._format_transport_address(transport_information[1])

        return None

    def _extract_source(self, snmp_engine: object, state_reference: object) -> str:
        source_from_transport = self._extract_source_from_transport_info(
            snmp_engine,
            state_reference,
        )
        if source_from_transport is not None:
            return source_from_transport

        source_from_observer = self._extract_source_from_observer(snmp_engine)
        if source_from_observer is not None:
            return source_from_observer

        return "unknown"

    def _parse_trap(
        self,
        var_binds: Iterable[tuple[object, object]],
        source: str = "unknown",
    ) -> dict[str, object]:
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        uptime = None
        trap_oid = None
        trap_oid_str = "unknown"
        varbinds: list[dict[str, object]] = []
        is_test_trap = False

        for oid, val in var_binds:
            if not isinstance(oid, Iterable) or isinstance(oid, (str, bytes, bytearray)):
                continue
            oid_tuple = tuple(part for part in oid if isinstance(part, int))
            if not oid_tuple:
                continue
            oid_str = _oid_tuple_to_str(oid_tuple)

            value_str = str(val)
            pretty_print = getattr(val, "prettyPrint", None)
            if callable(pretty_print):
                try:
                    value_str = str(pretty_print())
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    value_str = str(val)

            if oid_tuple == self.SYS_UPTIME_OID:
                uptime = value_str
            elif oid_tuple == self.SNMP_TRAP_OID:
                if isinstance(val, Iterable) and not isinstance(val, (str, bytes, bytearray)):
                    trap_oid = tuple(val)
                else:
                    trap_oid = None
                if trap_oid is not None:
                    trap_oid_str = _oid_tuple_to_str(trap_oid)
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
            "source": source,
        }

    def get_received_traps(self, limit: int | None = None) -> list[dict[str, object]]:
        """Return received traps in reverse chronological order."""
        traps = list(reversed(self.received_traps))
        if limit:
            return traps[:limit]
        return traps

    def clear_traps(self) -> None:
        """Remove all stored traps from in-memory history."""
        self.received_traps.clear()
        self.logger.info("Cleared all received traps")

    def is_running(self) -> bool:
        """Report whether the receiver thread is currently running."""
        return self.running


def main(argv: Iterable[str] | None = None) -> int:
    """Run trap receiver until interrupted."""
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Run SNMP trap receiver and log incoming traps",
        epilog="Example: %(prog)s --host 0.0.0.0 --port 162 --community public",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",  # noqa: S104
        help="Bind interface (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=16662,
        help="UDP port to listen on (default: 16662)",
    )
    parser.add_argument(
        "--community",
        default="public",
        help="SNMPv2c community (default: public)",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    receiver = TrapReceiver(host=args.host, port=args.port, community=args.community, logger=logger)

    def _shutdown(_signum: int, _frame: object) -> None:
        receiver.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    receiver.start()
    logger.info("Trap receiver running. Press Ctrl+C to stop.")

    try:
        while receiver.is_running():
            time.sleep(0.2)
    except KeyboardInterrupt:
        receiver.stop()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["TrapReceiver", "main"]
