import sys
import threading
import uvicorn
import asyncio
import argparse
from pathlib import Path
import shutil
from app.snmp_agent import SNMPAgent
import app.api


def run_snmp_agent(agent: SNMPAgent) -> None:
    """Run the SNMP agent in a separate thread with its own event loop."""
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        agent.run()
    except Exception as e:
        print(f"\nSNMP Agent ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    try:
        # Parse command-line arguments
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
        args = parser.parse_args()

        # Handle rebuild flags
        if args.rebuild:
            print("Forcing rebuild of compiled MIBs and schemas...")
            compiled_dir = Path("compiled-mibs")
            schema_dir = Path("agent-model")

            if compiled_dir.exists():
                print(f"Removing {compiled_dir}...")
                shutil.rmtree(compiled_dir)

            if schema_dir.exists():
                print(f"Removing {schema_dir}...")
                shutil.rmtree(schema_dir)

            print(
                "Rebuild flags cleared. MIBs and schemas will be regenerated on startup."
            )

        if args.rebuild_schemas:
            print("Forcing regeneration of schemas...")
            schema_dir = Path("agent-model")

            if schema_dir.exists():
                print(f"Removing {schema_dir}...")
                shutil.rmtree(schema_dir)

            print(
                "Schema regeneration flag set. Schemas will be regenerated on startup."
            )

        # Create the SNMP agent
        agent = SNMPAgent()

        # Set the global reference for the REST API
        app.api.snmp_agent = agent

        # Start SNMP agent in background thread
        snmp_thread = threading.Thread(
            target=run_snmp_agent, args=(agent,), daemon=True
        )
        snmp_thread.start()

        print("Starting SNMP Agent with REST API...")
        print("SNMP Agent running in background")
        print("REST API available at http://localhost:8800")
        print("Press Ctrl+C to stop")

        # Ensure uvicorn loggers propagate to the root logger configured by AppLogger
        import logging
        import socket
        import subprocess
        import signal
        import time
        import os
        import platform
        import re

        def _is_port_in_use(port: int) -> bool:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                return False
            except OSError:
                return True
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        def _find_pids_on_port(port: int) -> list[int]:
            """Cross-platform: try psutil, then platform native commands.
            Returns list of PIDs listening on the given TCP port.
            """
            # Try psutil first (pure python, recommended)
            try:
                import psutil

                pids = set()
                for conn in psutil.net_connections(kind="inet"):
                    laddr = getattr(conn, "laddr", None)
                    if laddr and getattr(laddr, "port", None) == port:
                        if conn.pid:
                            pids.add(conn.pid)
                return list(pids)
            except Exception:
                pass

            # Fall back to platform-specific commands
            # Use sys.platform for consistency with AppConfig.get_platform_setting
            is_windows = sys.platform.startswith("win")
            if is_windows:
                # netstat -ano : parse lines with LISTENING and the PID in last column
                try:
                    out = subprocess.check_output(
                        ["netstat", "-ano"], stderr=subprocess.DEVNULL, text=True
                    )
                    pids = set()
                    for line in out.splitlines():
                        parts = line.split()
                        if len(parts) >= 5:
                            local = parts[1]
                            state = parts[3] if len(parts) >= 4 else ""
                            pid = parts[-1]
                            if f":{port}" in local and state.upper() == "LISTENING":
                                try:
                                    pids.add(int(pid))
                                except Exception:
                                    continue
                    return list(pids)
                except Exception:
                    return []
            else:
                # POSIX systems: try lsof, then ss, then netstat
                if shutil.which("lsof"):
                    try:
                        out = subprocess.check_output(
                            ["lsof", "-ti", f":{port}"],
                            stderr=subprocess.DEVNULL,
                            text=True,
                        )
                        return [int(x) for x in out.split() if x.strip()]
                    except Exception:
                        pass
                if shutil.which("ss"):
                    try:
                        out = subprocess.check_output(
                            ["ss", "-ltnp"], stderr=subprocess.DEVNULL, text=True
                        )
                        pids = set()
                        for line in out.splitlines():
                            if f":{port} " in line or f":{port}\n" in line:
                                # look for pid=1234
                                m = re.search(r"pid=(\d+)", line)
                                if m:
                                    pids.add(int(m.group(1)))
                        return list(pids)
                    except Exception:
                        pass
                if shutil.which("netstat"):
                    try:
                        out = subprocess.check_output(
                            ["netstat", "-ltnp"], stderr=subprocess.DEVNULL, text=True
                        )
                        pids = set()
                        for line in out.splitlines():
                            if f":{port} " in line:
                                m = re.search(r"(\d+)/(\S+)$", line.strip())
                                if m:
                                    try:
                                        pids.add(int(m.group(1)))
                                    except Exception:
                                        pass
                        return list(pids)
                    except Exception:
                        pass
                return []

        def _kill_pids(pids: list[int]) -> None:
            """Cross-platform kill: graceful SIGTERM then SIGKILL on POSIX; taskkill on Windows."""
            if not pids:
                return
            system = platform.system()
            if system == "Windows":
                for pid in pids:
                    try:
                        subprocess.check_call(
                            ["taskkill", "/PID", str(pid), "/T", "/F"],
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception:
                        pass
                return

            # POSIX
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            # Wait a short time for graceful shutdown
            time.sleep(1)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    # still exists -> force kill
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
                except OSError:
                    # process gone
                    pass

        for name in ("uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            # Remove uvicorn's handlers so logs propagate to root handlers
            lg.handlers = []
            lg.propagate = True

        # Before starting Uvicorn, check if port is free and offer to kill occupying process
        rest_port = 8800
        if _is_port_in_use(rest_port):
            pids = _find_pids_on_port(rest_port)
            prompt = f"Port {rest_port} appears to be in use"
            if pids:
                prompt += f" by PIDs {pids}"
            prompt += ". Kill the process(es) and retry? [y/N]: "
            try:
                ans = input(prompt)
            except Exception:
                ans = "n"
            if ans and ans.lower() == "y":
                if pids:
                    _kill_pids(pids)
                    # Wait a moment for processes to terminate
                    time.sleep(1)
                # Re-check port
                if _is_port_in_use(rest_port):
                    print(f"Port {rest_port} still in use, aborting start")
                    raise SystemExit(1)
                print(f"Port {rest_port} freed, starting REST API")
            else:
                print("Aborting start due to port in use")
                raise SystemExit(1)

        # Start the FastAPI server
        uvicorn.run(
            "app.api:app",
            host="0.0.0.0",
            port=rest_port,
            reload=False,
            log_level="info",
        )

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
