"""CLI wrapper for loading existing MIB schemas without config."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.cli_model_common import print_model_summary as _print_model_summary
from app.cli_model_common import write_model_output
from app.model_paths import AGENT_MODEL_DIR


def load_all_schemas(schema_dir: str) -> dict[str, dict[str, object]]:
    """Load all schema.json files from subdirectories in schema_dir."""
    model: dict[str, dict[str, object]] = {}
    schema_root = Path(schema_dir)
    if not schema_root.exists():
        sys.stderr.write(f"Schema directory not found: {schema_dir}\n")
        return model

    for mib_dir in schema_root.iterdir():
        if mib_dir.is_dir():
            item = mib_dir.name
            schema_path = mib_dir / "schema.json"
            if schema_path.exists():
                try:
                    with schema_path.open(encoding="utf-8") as f:
                        schema = json.load(f)
                    if schema:  # Only include non-empty schemas
                        model[item] = schema
                except json.JSONDecodeError as e:
                    sys.stderr.write(f"Error loading {schema_path}: {e}\n")
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ) as e:
                    sys.stderr.write(f"Error processing {item}: {e}\n")

    return model


def print_model_summary(model: dict[str, dict[str, object]]) -> None:
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

    sys.stdout.write(f"Loading all schemas from {args.schema_dir}...\n")
    model = load_all_schemas(args.schema_dir)

    if not model:
        sys.stderr.write("No schemas found or loaded\n")
        return 1

    print_model_summary(model)

    if args.output and not write_model_output(model, args.output):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
