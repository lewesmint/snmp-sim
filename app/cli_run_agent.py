"""CLI wrapper for running the SNMP agent with a preloaded internal model."""

from __future__ import annotations

import argparse
import logging
import sys

from app.app_config import AppConfig
from app.cli_build_model import build_internal_model
from app.model_paths import AGENT_MODEL_DIR
from app.snmp_agent import SNMPAgent

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the SNMP agent with a preloaded model from configured MIB schemas."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Run the SNMP agent with a preloaded internal model from "
            "configured MIB schemas. Builds the model and starts the agent "
            "to respond to GET and GETNEXT requests."
        )
    )
    parser.add_argument(
        "--schema-dir",
        default=str(AGENT_MODEL_DIR),
        help="Directory containing MIB schema subdirectories (default: agent-model)",
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
        logger.exception("Error: Config file not found: %s", args.config)
        return 1

    mibs_raw = config.get("mibs", [])
    mibs = mibs_raw if isinstance(mibs_raw, list) else []
    mibs = [str(mib) for mib in mibs]
    if not mibs:
        logger.error("No MIBs configured")
        return 1

    logger.info("Building internal model for %s configured MIBs...", len(mibs))
    model = build_internal_model(mibs, args.schema_dir)

    if not model:
        logger.error("Error: No schemas could be loaded")
        return 1

    logger.info(
        "Model built with %s MIBs. Starting SNMP agent on %s:%s...",
        len(model),
        args.host,
        args.port,
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
        logger.info("Agent stopped by user.")
    except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
        logger.exception("Error running agent")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
