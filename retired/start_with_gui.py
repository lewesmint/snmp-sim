#!/usr/bin/env python3
"""Start the SNMP agent REST server and then launch the GUI.

Behavior:
- Starts `run_agent_with_rest.py` as a subprocess.
- Waits 5 seconds for the agent to start initializing.
- Launches the GUI (`ui/snmp_gui.py`) with `--host`/`--port`, `--autoconnect`, and `--connect-delay 5`.
- The GUI will attempt to connect 5 seconds after it launches.
- Connection failures are logged without popup dialogs.

This script is intended for local development convenience.
"""

import subprocess
import sys
import time
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--agent-cmd", default="python run_agent_with_rest.py")
    parser.add_argument(
        "--gui-delay", type=int, default=5, help="Seconds to wait before launching GUI"
    )
    args = parser.parse_args()

    # Start the agent
    print("Starting SNMP agent...")
    agent_log = Path("logs/agent_start.log")
    agent_log.parent.mkdir(parents=True, exist_ok=True)
    # If data/agent_config.yaml doesn't exist but root agent_config.yaml does, copy it
    root_cfg = Path("agent_config.yaml")
    data_cfg = Path("data/agent_config.yaml")
    if not data_cfg.exists() and root_cfg.exists():
        data_cfg.parent.mkdir(parents=True, exist_ok=True)
        try:
            data_cfg.write_text(root_cfg.read_text(), encoding="utf-8")
        except Exception:
            pass

    subprocess.Popen(
        args.agent_cmd.split(), stdout=agent_log.open("w"), stderr=subprocess.STDOUT
    )

    try:
        print(f"Waiting {args.gui_delay} seconds for agent to start initializing...")
        time.sleep(args.gui_delay)

        print("Launching GUI (will auto-connect after 5 seconds)...")
        gui_cmd = [
            sys.executable,
            "ui/snmp_gui.py",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--autoconnect",
            "--connect-delay",
            "5",
            "--silent-errors",
        ]
        subprocess.Popen(gui_cmd)

        print(
            "GUI launched. See logs/gui.log for GUI log output and logs/snmp-agent.log for agent logs."
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
