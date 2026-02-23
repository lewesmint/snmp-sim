"""CLI tool to update schema_version in schema.json files."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable
from pathlib import Path

from app.model_paths import AGENT_MODEL_DIR

DEFAULT_SCHEMA_VERSION = "1.0.1"
logger = logging.getLogger(__name__)


def _iter_schema_files(schema_dir: Path) -> list[Path]:
    return sorted(schema_dir.rglob("schema.json"))


def main(argv: Iterable[str] | None = None) -> int:
    """Update schema_version for all schema.json files."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Update schema_version for all schema.json files.",
    )
    parser.add_argument(
        "--schema-dir",
        default=str(AGENT_MODEL_DIR),
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--set-version",
        default=DEFAULT_SCHEMA_VERSION,
        help=f"Version string to set (default: {DEFAULT_SCHEMA_VERSION})",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    schema_dir = Path(args.schema_dir)
    if not schema_dir.exists():
        logger.error("Schema directory not found: %s", schema_dir)
        return 1

    schema_files = _iter_schema_files(schema_dir)
    if not schema_files:
        logger.error("No schema.json files found.")
        return 1

    updated = 0
    for schema_file in schema_files:
        try:
            with schema_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue

            if data.get("schema_version") != args.set_version:
                data["schema_version"] = args.set_version
                with schema_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                updated += 1
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            logger.exception("Failed to update %s", schema_file)

    logger.info("Updated %s schema file(s) to version %s.", updated, args.set_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
