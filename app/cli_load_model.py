"""CLI wrapper for loading existing MIB schemas without config."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict
from app.types import TypeRegistry
from app.cli_model_common import print_model_summary as _print_model_summary
from app.cli_model_common import write_model_output
from app.model_paths import AGENT_MODEL_DIR


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
    _print_model_summary(model)


def main(argv: list[str] | None = None) -> int:
    """Load all existing MIB schemas from agent-model directory without config."""
    parser = argparse.ArgumentParser(
        description="Load all existing MIB schemas from agent-model directory without config."
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

    print(f"Loading all schemas from {args.schema_dir}...")
    model = load_all_schemas(args.schema_dir)

    if not model:
        print("No schemas found or loaded", file=sys.stderr)
        return 1

    print_model_summary(model)

    if args.output:
        if not write_model_output(model, args.output):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
