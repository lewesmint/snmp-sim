"""Shared helpers for CLI commands that load/build MIB models."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ModelDict = dict[str, dict[str, object]]


def print_model_summary(model: ModelDict) -> None:
    """Print a summary of loaded MIB schemas and table counts."""
    logger.info("Loaded %s MIB schemas:", len(model))
    for mib, schema in model.items():
        objects = schema["objects"] if isinstance(schema, dict) and "objects" in schema else schema

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
        logger.info("  %s: %s objects, %s tables", mib, object_count, table_count)


def write_model_output(model: ModelDict, output_path: str) -> bool:
    """Write model JSON to disk and print result. Return True on success."""
    try:
        with Path(output_path).open("w", encoding="utf-8") as file_obj:
            json.dump(model, file_obj, indent=2)
        logger.info("Model saved to %s", output_path)
    except OSError:
        logger.exception("Error: Failed to save model")
        return False
    else:
        return True
