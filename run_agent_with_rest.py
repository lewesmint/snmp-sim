"""Run the SNMP agent alongside the REST API server."""

import argparse
import asyncio
import contextlib
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, NoReturn, cast

import uvicorn

from app.app_config import AppConfig
from app.api_state import set_snmp_agent
from app.model_paths import AGENT_MODEL_DIR, COMPILED_MIBS_DIR
from app.snmp_agent import SNMPAgent

_psutil: Any | None
try:
    import psutil as _psutil
except ImportError:
    _psutil = None

psutil_module: Any | None = _psutil

logger = logging.getLogger(__name__)

REST_PORT = 8800
LOCALHOST_BIND = "127.0.0.1"
API_HOST = "0.0.0.0"  # noqa: S104
NETSTAT_MIN_PARTS = 5
NETSTAT_STATE_INDEX = 3
DEFAULT_SNMP_PORT = 11161


def _configure_cli_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SNMP Agent with REST API")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of compiled MIB files and schemas",
    )
    parser.add_argument(
        "--rebuild-schemas",
        action="store_true",
        help="Force regeneration of schema files only",
    )
    return parser.parse_args()


def _handle_rebuild_flags(args: argparse.Namespace) -> None:
    if args.rebuild:
        logger.info("Forcing rebuild of compiled MIBs and schemas...")
        compiled_dir = COMPILED_MIBS_DIR
        schema_dir = AGENT_MODEL_DIR

        if compiled_dir.exists():
            logger.info("Removing %s...", compiled_dir)
            shutil.rmtree(compiled_dir)

        if schema_dir.exists():
            logger.info("Removing %s...", schema_dir)
            shutil.rmtree(schema_dir)

        logger.info("Rebuild flags cleared. MIBs and schemas will be regenerated on startup.")

    if args.rebuild_schemas:
        logger.info("Forcing regeneration of schemas...")
        schema_dir = AGENT_MODEL_DIR

        if schema_dir.exists():
            logger.info("Removing %s...", schema_dir)
            shutil.rmtree(schema_dir)

        logger.info("Schema regeneration flag set. Schemas will be regenerated on startup.")


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((LOCALHOST_BIND, port))
        except OSError:
            return True
        return False


def _find_pids_psutil(port: int) -> list[int]:
    if psutil_module is None:
        return []

    pids: set[int] = set()
    for conn in psutil_module.net_connections(kind="inet"):
        laddr = getattr(conn, "laddr", None)
        if laddr and getattr(laddr, "port", None) == port and conn.pid:
            pids.add(conn.pid)
    return list(pids)


def _find_pids_windows(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],  # noqa: S607
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []

    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < NETSTAT_MIN_PARTS:
            continue
        local = parts[1]
        state = parts[NETSTAT_STATE_INDEX]
        pid = parts[-1]
        if f":{port}" in local and state.upper() == "LISTENING":
            with contextlib.suppress(ValueError):
                pids.add(int(pid))
    return list(pids)


def _run_port_command(command: list[str]) -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            command,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.SubprocessError, OSError):
        return ""


def _find_pids_lsof(port: int) -> list[int]:
    if not shutil.which("lsof"):
        return []
    out = _run_port_command(["lsof", "-ti", f":{port}"])
    if not out:
        return []
    return [int(value) for value in out.split() if value.strip()]


def _find_pids_ss(port: int) -> list[int]:
    if not shutil.which("ss"):
        return []

    out = _run_port_command(["ss", "-ltnp"])
    if not out:
        return []

    pids: set[int] = set()
    for line in out.splitlines():
        if f":{port} " in line or f":{port}\n" in line:
            match = re.search(r"pid=(\d+)", line)
            if match:
                pids.add(int(match.group(1)))
    return list(pids)


def _find_pids_netstat_posix(port: int) -> list[int]:
    if not shutil.which("netstat"):
        return []

    out = _run_port_command(["netstat", "-ltnp"])
    if not out:
        return []

    pids: set[int] = set()
    for line in out.splitlines():
        if f":{port} " not in line:
            continue
        match = re.search(r"(\d+)/(\S+)$", line.strip())
        if match:
            with contextlib.suppress(ValueError):
                pids.add(int(match.group(1)))
    return list(pids)


def _find_pids_on_port(port: int) -> list[int]:
    """Return PIDs listening on a TCP port via psutil or platform tools."""
    with contextlib.suppress(psutil_module.Error if psutil_module else Exception):
        pids = _find_pids_psutil(port)
        if pids:
            return pids

    if sys.platform.startswith("win"):
        return _find_pids_windows(port)

    for finder in (_find_pids_lsof, _find_pids_ss, _find_pids_netstat_posix):
        with contextlib.suppress(ValueError):
            pids = finder(port)
            if pids:
                return pids
    return []


def _kill_pids_windows(pids: list[int]) -> None:
    for pid in pids:
        with contextlib.suppress(subprocess.SubprocessError, OSError):
            subprocess.check_call(  # noqa: S603
                ["taskkill", "/PID", str(pid), "/T", "/F"],  # noqa: S607
                stderr=subprocess.DEVNULL,
            )


def _kill_pids_posix(pids: list[int]) -> None:
    for pid in pids:
        with contextlib.suppress(OSError, PermissionError):
            os.kill(pid, signal.SIGTERM)
    time.sleep(1)
    for pid in pids:
        with contextlib.suppress(OSError, PermissionError):
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)


def _kill_pids(pids: list[int]) -> None:
    if not pids:
        return
    if platform.system() == "Windows":
        _kill_pids_windows(pids)
        return
    _kill_pids_posix(pids)


def _configure_uvicorn_loggers() -> None:
    for name in ("uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def _abort_start(message: str) -> NoReturn:
    logger.error("%s", message)
    raise SystemExit(1)


def _find_available_rest_port(start_port: int, max_attempts: int = 20) -> int:
    """Find the next available TCP port starting from start_port."""
    for attempt in range(max_attempts):
        candidate = start_port + attempt
        if not _is_port_in_use(candidate):
            return candidate
    msg = f"Could not find available port after {max_attempts} attempts starting from {start_port}"
    _abort_start(msg)


def _ensure_snmp_port_available(port: int) -> None:
    """Fail if SNMP port is in use - SNMP port must not be shared."""
    if not _is_port_in_use(port):
        return

    pids = _find_pids_on_port(port)
    error_msg = f"SNMP port {port} is already in use"
    if pids:
        error_msg += f" by PIDs {pids}"
    error_msg += ". Please stop the conflicting process and try again."
    _abort_start(error_msg)


def _ensure_rest_port_available(port: int) -> int:
    """Find available REST port (hopping to next available if needed). Returns the port to use."""
    if not _is_port_in_use(port):
        logger.info("REST API port %s is available", port)
        return port

    logger.warning("REST API port %s is in use, finding alternative...", port)
    available_port = _find_available_rest_port(port)
    logger.info("REST API will use port %s instead (original %s in use)", available_port, port)
    return available_port


def run_snmp_agent(agent: SNMPAgent) -> None:
    """Run the SNMP agent in a separate thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agent.run()


def main() -> int:
    """Parse arguments, start SNMP in background, and run REST API."""
    _configure_cli_logging()
    args = _parse_args()
    _handle_rebuild_flags(args)

    # Load config to get SNMP port
    config = AppConfig("data/agent_config.yaml")
    snmp_port: int = int(cast(int | str, config.get("snmp.port", DEFAULT_SNMP_PORT)))

    # Check SNMP port availability before starting agent
    logger.info("Checking SNMP port %s availability...", snmp_port)
    _ensure_snmp_port_available(snmp_port)

    agent = SNMPAgent(port=snmp_port)
    set_snmp_agent(agent)

    snmp_thread = threading.Thread(target=run_snmp_agent, args=(agent,), daemon=True)
    snmp_thread.start()

    logger.info("Starting SNMP Agent with REST API...")
    logger.info("SNMP Agent running in background on port %s", snmp_port)
    logger.info("Press Ctrl+C to stop")

    _configure_uvicorn_loggers()
    actual_rest_port = _ensure_rest_port_available(REST_PORT)
    logger.info("REST API available at http://localhost:%s", actual_rest_port)

    uvicorn.run(
        "app.api:app",
        host=API_HOST,
        port=actual_rest_port,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
