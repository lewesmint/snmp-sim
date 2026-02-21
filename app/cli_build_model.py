"""CLI wrapper for building an internal model from configured MIB schemas."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, cast

from app.app_config import AppConfig


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
    print(f"Loaded {len(model)} MIB schemas:")
    for mib, schema in model.items():
        # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
        if isinstance(schema, dict) and "objects" in schema:
            objects = schema["objects"]
        else:
            objects = schema

        object_count = len(objects) if isinstance(objects, dict) else 0
        table_count = (
            sum(
                1
                for obj in objects.values()
                if isinstance(obj, dict) and obj.get("type") == "MibTable"
            )
            if isinstance(objects, dict)
            else 0
        )
        print(f"  {mib}: {object_count} objects, {table_count} tables")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an internal model from configured MIB schemas. "
        "Loads schema.json files and creates a combined in-memory model."
    )
    parser.add_argument(
        "--schema-dir",
        default="agent-model",
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
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(model, f, indent=2)
            print(f"Model saved to {args.output}")
        except IOError as e:
            print(f"Error: Failed to save model: {e}", file=sys.stderr)
            return 1

    print("Internal model built successfully.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
