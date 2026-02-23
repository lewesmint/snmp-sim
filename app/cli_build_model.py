"""CLI wrapper for building an internal model from configured MIB schemas."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, cast

from app.app_config import AppConfig
from app.cli_model_common import print_model_summary as _print_model_summary
from app.cli_model_common import write_model_output
from app.model_paths import AGENT_MODEL_DIR

logger = logging.getLogger(__name__)


def load_mib_schema(mib_name: str, schema_dir: str) -> dict[str, Any] | None:
    """Load schema.json for a given MIB."""
    schema_path = Path(schema_dir) / mib_name / "schema.json"
    if not schema_path.exists():
        logger.warning("Schema not found: %s", schema_path)
        return None
    try:
        with schema_path.open("r", encoding="utf-8") as f:
            return cast("dict[str, Any]", json.load(f))
    except json.JSONDecodeError:
        logger.exception("Error: Failed to parse %s", schema_path)
        return None


def build_internal_model(mibs: list[str], schema_dir: str) -> dict[str, dict[str, Any]]:
    """Build internal model by loading all MIB schemas."""
    model = {}
    for mib in mibs:
        schema = load_mib_schema(mib, schema_dir)
        if schema is not None:
            model[mib] = schema
    return model


def print_model_summary(model: dict[str, dict[str, Any]]) -> None:
    """Print a summary of the loaded model."""
    _print_model_summary(model)


def main(argv: list[str] | None = None) -> int:
    """Build an internal model from configured MIB schemas."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Build an internal model from configured MIB schemas. "
        "Loads schema.json files and creates a combined in-memory model."
    )
    parser.add_argument(
        "--schema-dir",
        default=str(AGENT_MODEL_DIR),
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--output",
        help="Optional output file to save the model as JSON",
    )

    args = parser.parse_args(argv)

    try:
        config = AppConfig()
    except FileNotFoundError:
        logger.exception("Error: Config file not found")
        return 1

    mibs_raw = config.get("mibs", [])
    mibs = mibs_raw if isinstance(mibs_raw, list) else []
    mibs = [str(mib) for mib in mibs]
    if not mibs:
        logger.error("No MIBs configured")
        return 1

    logger.info("Building model for %s configured MIBs...", len(mibs))
    model = build_internal_model(mibs, args.schema_dir)

    if not model:
        logger.error("Error: No schemas could be loaded")
        return 1

    print_model_summary(model)

    if args.output and not write_model_output(model, args.output):
        return 1

    logger.info("Internal model built successfully.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
