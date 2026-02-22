"""CLI tool to update schema_version in schema.json files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from app.model_paths import AGENT_MODEL_DIR

DEFAULT_SCHEMA_VERSION = "1.0.1"


def _iter_schema_files(schema_dir: Path) -> list[Path]:
    return sorted(schema_dir.rglob("schema.json"))


def main(argv: Iterable[str] | None = None) -> int:
    """Update schema_version for all schema.json files."""
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
        print(f"Schema directory not found: {schema_dir}")
        return 1

    schema_files = _iter_schema_files(schema_dir)
    if not schema_files:
        print("No schema.json files found.")
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
        except Exception as exc:
            print(f"Failed to update {schema_file}: {exc}")

    print(f"Updated {updated} schema file(s) to version {args.set_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
