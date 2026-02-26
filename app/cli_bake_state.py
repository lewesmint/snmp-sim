"""CLI tool to bake current MIB state into agent-model schema files.

This tool:
1. Backs up existing agent-model directory to agent-model-backups/{timestamp}/
2. Reads current state from agent-model/mib_state.json
3. Merges state values into schema files as initial values
4. Updates schema files in-place
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from app.json_format import write_json_with_horizontal_oid_lists
from app.model_paths import AGENT_MODEL_BACKUPS_DIR, AGENT_MODEL_DIR, MIB_STATE_FILE

logger = logging.getLogger(__name__)


def _object_oid_string(obj_data: dict[str, Any]) -> str:
    return ".".join(str(part) for part in obj_data["oid"])


def _normalize_scalar_oid(oid: str) -> str:
    return oid.removesuffix(".0")


def _schema_objects_view(schema: dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", schema.get("objects", schema))


def _process_schema_file(
    schema_file: Path,
    schema_dir: Path,
    scalars: dict[str, Any],
    tables: dict[str, Any],
) -> int:
    try:
        with schema_file.open(encoding="utf-8") as f:
            schema = json.load(f)

        objects = _schema_objects_view(schema)

        scalar_baked = _bake_scalars(objects, scalars)
        table_baked = _bake_tables(objects, tables)
        baked_total = scalar_baked + table_baked

        if baked_total > 0:
            write_json_with_horizontal_oid_lists(schema_file, schema)
            logger.info("✓ Updated %s", schema_file.relative_to(schema_dir.parent))
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        logger.exception("Error processing %s", schema_file)
        return 0
    return baked_total


def _find_table_entry_obj(objects: dict[str, Any], table_obj: dict[str, Any]) -> dict[str, Any]:
    expected_entry_oid = [*list(table_obj["oid"]), 1]
    for other_data in objects.values():
        if (
            isinstance(other_data, dict)
            and other_data.get("type") == "MibTableRow"
            and list(other_data.get("oid", [])) == expected_entry_oid
        ):
            return other_data
    return {}


def _parse_index_values(
    instance_str: str,
    index_columns: list[str],
    columns_meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if index_columns == ["__index__"]:
        row["__index__"] = instance_str
        return row

    parts = instance_str.split(".")
    pos = 0
    for col_name in index_columns:
        col_type = columns_meta.get(col_name, {}).get("type", "")
        if col_type == "IpAddress":
            if pos + 4 <= len(parts):
                row[col_name] = ".".join(parts[pos : pos + 4])
                pos += 4
            else:
                row[col_name] = ".".join(parts[pos:])
                pos = len(parts)
        elif pos < len(parts):
            try:
                row[col_name] = int(parts[pos])
            except (ValueError, IndexError):
                row[col_name] = parts[pos] if pos < len(parts) else ""
            pos += 1

    return row


def _build_rows_for_instances(
    instances_dict: dict[str, Any],
    index_columns: list[str],
    columns_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance_str, instance_data in instances_dict.items():
        row = _parse_index_values(instance_str, index_columns, columns_meta)

        if isinstance(instance_data, dict):
            column_values = instance_data.get("column_values", {})
            if isinstance(column_values, dict):
                row.update(column_values)
            index_values = instance_data.get("index_values", {})
            if isinstance(index_values, dict):
                row.update(index_values)

        if row:
            rows.append(row)

    return rows


def _bake_scalars(objects: dict[str, Any], scalars: dict[str, Any]) -> int:
    baked_count = 0
    for oid, value in scalars.items():
        normalized_oid = _normalize_scalar_oid(oid)
        for obj_name, obj_data in objects.items():
            if not (isinstance(obj_data, dict) and "oid" in obj_data):
                continue

            obj_oid_str = _object_oid_string(obj_data)
            if obj_oid_str == normalized_oid or oid.endswith(f".{obj_oid_str}.0"):
                obj_data["initial"] = value
                baked_count += 1
                logger.info("  Baked scalar %s (%s) = %s", obj_name, oid, value)

    return baked_count


def _bake_tables(objects: dict[str, Any], tables: dict[str, Any]) -> int:
    baked_count = 0
    for table_oid, instances_dict in tables.items():
        if not isinstance(instances_dict, dict):
            continue

        for obj_name, obj_data in objects.items():
            if not (isinstance(obj_data, dict) and obj_data.get("type") == "MibTable"):
                continue

            if _object_oid_string(obj_data) != table_oid:
                continue

            entry_obj = _find_table_entry_obj(objects, obj_data)
            index_columns = entry_obj.get("indexes", [])
            if not isinstance(index_columns, list):
                index_columns = []

            columns_meta = {
                column_name: column_meta
                for column_name in index_columns
                if isinstance((column_meta := objects.get(column_name)), dict)
            }

            rows = _build_rows_for_instances(instances_dict, index_columns, columns_meta)
            if rows:
                obj_data["rows"] = rows
                baked_count += len(rows)
                logger.info(
                    "  Baked %s row(s) for table %s (%s)",
                    len(rows),
                    obj_name,
                    table_oid,
                )
            break

    return baked_count


def backup_schemas(schema_dir: Path, backup_base: Path) -> Path:
    """Backup existing schema directory with timestamp."""
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / timestamp

    if schema_dir.exists():
        logger.info("Backing up %s to %s...", schema_dir, backup_dir)
        shutil.copytree(schema_dir, backup_dir)
        logger.info("✓ Backup created: %s", backup_dir)
    else:
        logger.warning("Schema directory %s does not exist, skipping backup", schema_dir)

    return backup_dir


def load_mib_state(state_file: Path) -> dict[str, Any]:
    """Load current MIB state from mib_state.json."""
    if not state_file.exists():
        logger.warning("State file %s does not exist", state_file)
        return {"scalars": {}, "tables": {}, "deleted_instances": []}

    with state_file.open(encoding="utf-8") as f:
        state: dict[str, Any] = json.load(f)
        return state


def bake_state_into_schemas(schema_dir: Path, state: dict[str, Any]) -> int:
    """Bake state values into schema files as initial values.

    Returns the number of values baked.
    """
    baked_total = 0
    scalars = state.get("scalars", {})
    tables = state.get("tables", {})

    # Process all schema files
    for schema_file in schema_dir.rglob("schema.json"):
        baked_total += _process_schema_file(schema_file, schema_dir, scalars, tables)

    return baked_total


def main(argv: list[str] | None = None) -> int:
    """Bake state into schemas."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Bake current MIB state into agent-model schema files"
    )
    parser.add_argument(
        "--schema-dir",
        default=str(AGENT_MODEL_DIR),
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--state-file",
        default=str(MIB_STATE_FILE),
        help="MIB state file to bake from (default: agent-model/mib_state.json)",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(AGENT_MODEL_BACKUPS_DIR),
        help="Directory for backups (default: agent-model-backups)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup before baking",
    )

    args = parser.parse_args(argv)

    schema_dir = Path(args.schema_dir)
    state_file = Path(args.state_file)
    backup_base = Path(args.backup_dir)

    logger.info("%s", "=" * 60)
    logger.info("Baking MIB State into Agent Model Schemas")
    logger.info("%s", "=" * 60)

    # Backup existing schemas
    if not args.no_backup:
        _backup_dir = backup_schemas(schema_dir, backup_base)
    else:
        logger.info("Skipping backup (--no-backup specified)")

    # Load current state
    logger.info("\nLoading state from %s...", state_file)
    state = load_mib_state(state_file)
    scalar_count = len(state.get("scalars", {}))
    table_count = len(state.get("tables", {}))
    logger.info("✓ Loaded %s scalar(s) and %s table(s)", scalar_count, table_count)

    # Bake state into schemas
    logger.info("\nBaking state into schemas in %s...", schema_dir)
    baked_count = bake_state_into_schemas(schema_dir, state)

    # Clear the state file now that values have been baked
    logger.info("\nClearing state file %s...", state_file)
    with state_file.open("w", encoding="utf-8") as f:
        json.dump(
            {"scalars": {}, "tables": {}, "deleted_instances": []},
            f,
            indent=2,
            sort_keys=True,
        )
    logger.info("✓ State file cleared")

    logger.info("\n%s", "=" * 60)
    logger.info("✓ Baking complete! Baked %s value(s) into schemas", baked_count)
    logger.info("✓ State file has been cleared")
    logger.info("%s", "=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
