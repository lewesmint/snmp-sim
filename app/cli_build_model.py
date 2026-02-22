"""CLI wrapper for building an internal model from configured MIB schemas."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, cast

from app.app_config import AppConfig
from app.cli_model_common import print_model_summary as _print_model_summary
from app.cli_model_common import write_model_output
from app.model_paths import AGENT_MODEL_DIR


def load_mib_schema(mib_name: str, schema_dir: str) -> Dict[str, Any] | None:
    """Load schema.json for a given MIB."""
    from pathlib import Path

    schema_path = Path(schema_dir) / mib_name / "schema.json"
    if not schema_path.exists():
        print(f"Warning: Schema not found: {schema_path}", file=sys.stderr)
        return None
    try:
        with schema_path.open("r", encoding="utf-8") as f:
            return cast(Dict[str, Any], json.load(f))
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {schema_path}: {e}", file=sys.stderr)
        return None


def build_internal_model(mibs: list[str], schema_dir: str) -> Dict[str, Dict[str, Any]]:
    """Build internal model by loading all MIB schemas."""
    model = {}
    for mib in mibs:
        schema = load_mib_schema(mib, schema_dir)
        if schema is not None:
            model[mib] = schema
    return model


def print_model_summary(model: Dict[str, Dict[str, Any]]) -> None:
    """Print a summary of the loaded model."""
    _print_model_summary(model)


def main(argv: list[str] | None = None) -> int:
    """Build an internal model from configured MIB schemas."""
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
        print("Error: Config file not found", file=sys.stderr)
        return 1

    mibs = config.get("mibs", [])
    if not mibs:
        print("No MIBs configured", file=sys.stderr)
        return 1

    print(f"Building model for {len(mibs)} configured MIBs...")
    model = build_internal_model(mibs, args.schema_dir)

    if not model:
        print("Error: No schemas could be loaded", file=sys.stderr)
        return 1

    print_model_summary(model)

    if args.output:
        if not write_model_output(model, args.output):
            return 1

    print("Internal model built successfully.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
