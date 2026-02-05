"""CLI wrapper for running the SNMP agent with a preloaded internal model."""

from __future__ import annotations

import argparse
import sys

from app.app_config import AppConfig
from app.cli_build_model import build_internal_model
from app.snmp_agent import SNMPAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the SNMP agent with a preloaded internal model from configured MIB schemas. "
        "Builds the model and starts the agent to respond to GET and GETNEXT requests."
    )
    parser.add_argument(
        "--schema-dir",
        default="mock-behaviour",
        help="Directory containing MIB schema subdirectories (default: mock-behaviour)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the SNMP agent to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=11161,
        help="Port to bind the SNMP agent to (default: 11161)",
    )
    parser.add_argument(
        "--config",
        default="agent_config.yaml",
        help="Path to the agent config file (default: agent_config.yaml)",
    )

    args = parser.parse_args(argv)

    try:
        config = AppConfig(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1

    mibs = config.get("mibs", [])
    if not mibs:
        print("No MIBs configured", file=sys.stderr)
        return 1

    print(f"Building internal model for {len(mibs)} configured MIBs...")
    model = build_internal_model(mibs, args.schema_dir)

    if not model:
        print("Error: No schemas could be loaded", file=sys.stderr)
        return 1

    print(
        f"Model built with {len(model)} MIBs. Starting SNMP agent on {args.host}:{args.port}..."
    )

    try:
        agent = SNMPAgent(
            host=args.host,
            port=args.port,
            config_path=args.config,
            preloaded_model=model,
        )
        agent.run()
    except KeyboardInterrupt:
        print("\nAgent stopped by user.")
    except Exception as e:
        print(f"Error running agent: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
