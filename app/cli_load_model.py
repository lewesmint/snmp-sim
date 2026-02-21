"""CLI wrapper for loading existing MIB schemas without config."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict
from app.types import TypeRegistry


def load_all_schemas(schema_dir: str) -> TypeRegistry:
    """Load all schema.json files from subdirectories in schema_dir."""
    model: TypeRegistry = {}
    if not os.path.exists(schema_dir):
        print(f"Schema directory not found: {schema_dir}", file=sys.stderr)
        return model

    from pathlib import Path

    for item in os.listdir(schema_dir):
        mib_dir = Path(schema_dir) / item
        if mib_dir.is_dir():
            schema_path = mib_dir / "schema.json"
            if schema_path.exists():
                try:
                    with open(schema_path, "r", encoding="utf-8") as f:
                        schema = json.load(f)
                    if schema:  # Only include non-empty schemas
                        model[item] = schema
                except json.JSONDecodeError as e:
                    print(f"Error loading {schema_path}: {e}", file=sys.stderr)
                except Exception as e:
                    print(f"Error processing {item}: {e}", file=sys.stderr)

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
        description="Load all existing MIB schemas from agent-model directory without config."
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

    print(f"Loading all schemas from {args.schema_dir}...")
    model = load_all_schemas(args.schema_dir)

    if not model:
        print("No schemas found or loaded", file=sys.stderr)
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

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
