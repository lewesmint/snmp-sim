"""Shared helpers for CLI commands that load/build MIB models."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict


ModelDict = Dict[str, Dict[str, Any]]


def print_model_summary(model: ModelDict) -> None:
    """Print a summary of loaded MIB schemas and table counts."""
    print(f"Loaded {len(model)} MIB schemas:")
    for mib, schema in model.items():
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


def write_model_output(model: ModelDict, output_path: str) -> bool:
    """Write model JSON to disk and print result. Return True on success."""
    try:
        with open(output_path, "w", encoding="utf-8") as file_obj:
            json.dump(model, file_obj, indent=2)
        print(f"Model saved to {output_path}")
        return True
    except IOError as error:
        print(f"Error: Failed to save model: {error}", file=sys.stderr)
        return False
