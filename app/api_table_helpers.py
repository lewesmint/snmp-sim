"""Helper functions for API table operations and schema management."""

from __future__ import annotations

from typing import Any
from fastapi import HTTPException

from app.model_paths import AGENT_MODEL_DIR


def extract_schema_objects(schema: Any) -> dict[str, Any]:
    """Extract objects dictionary from schema, handling both flat and nested formats."""
    if not isinstance(schema, dict):
        return {}
    objects = schema.get("objects", schema)
    return objects if isinstance(objects, dict) else {}


def load_all_agent_schemas() -> dict[str, Any]:
    """Load all schemas from the agent-model directory."""
    from app.cli_load_model import load_all_schemas

    return load_all_schemas(str(AGENT_MODEL_DIR))


def get_default_row_from_schemas(schemas: dict[str, Any], table_oid: str) -> dict[str, Any]:
    """Get the first default row from a table in the schemas."""
    parts = tuple(int(x) for x in table_oid.split(".")) if table_oid else ()
    for schema in schemas.values():
        objects = extract_schema_objects(schema)
        for obj_data in objects.values():
            if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                obj_oid = tuple(obj_data.get("oid", []))
                if obj_oid == parts:
                    rows = obj_data.get("rows", [])
                    if rows and isinstance(rows[0], dict):
                        return rows[0]
    return {}


def should_use_default_value(val: Any) -> bool:
    """Check if a value should be replaced with a default value."""
    if val is None:
        return True
    if isinstance(val, str) and val.strip().lower() == "unset":
        return True
    return False


def extract_instance_index_str(values: dict[str, Any]) -> str:
    """Extract instance index string from values dictionary containing __index__ keys."""
    index_parts = []
    i = 1
    while True:
        key = "__index__" if i == 1 else f"__index_{i}__"
        if key in values:
            index_parts.append(str(values[key]))
            i += 1
        else:
            break

    if index_parts:
        return ".".join(index_parts)

    if "index" in values:
        return str(values["index"])
    if "instance" in values:
        return str(values["instance"])
    if not values:
        return "1"
    return ".".join(str(v) for v in values.values())


def parse_index_values(index_str: str) -> dict[str, str]:
    """Parse a dotted index string into a dictionary with __index__ keys."""
    parsed_index_values: dict[str, str] = {}
    for i, part in enumerate(index_str.split("."), 1):
        key = "__index__" if i == 1 else f"__index_{i}__"
        parsed_index_values[key] = part
    return parsed_index_values


def merge_column_defaults(
    columns: dict[str, Any],
    incoming_values: dict[str, Any],
    default_row: dict[str, Any],
    excluded_columns: set[str],
) -> dict[str, Any]:
    """Merge incoming values with defaults from schema and default row."""
    merged: dict[str, Any] = {}
    for col_name, col_meta in columns.items():
        if col_name in excluded_columns:
            continue
        if col_name in incoming_values and not should_use_default_value(incoming_values[col_name]):
            merged[col_name] = incoming_values[col_name]
            continue
        if col_name in default_row:
            merged[col_name] = default_row[col_name]
            continue
        default_val = col_meta.get("default", "") if isinstance(col_meta, dict) else ""
        if default_val != "":
            merged[col_name] = default_val
    return merged


def convert_index_value(  # noqa: PLR0912
    col_name: str,
    value: str | int,
    columns: dict[str, Any],
) -> int | tuple[int, ...] | str:
    """Convert an index value to the appropriate type based on column metadata."""
    result: int | tuple[int, ...] | str

    if col_name not in columns:
        if isinstance(value, int):
            result = value
        else:
            try:
                result = int(value)
            except (ValueError, TypeError):
                result = str(value)
        return result

    col_info = columns[col_name]
    col_type = col_info.get("type", "") if isinstance(col_info, dict) else ""

    if col_type == "IpAddress" or "IpAddress" in col_type:
        if isinstance(value, str):
            try:
                result = tuple(int(p) for p in value.split("."))
            except (ValueError, AttributeError):
                result = str(value)
        else:
            result = value
    elif "Integer" in col_type or col_type in (
        "Integer32",
        "Integer64",
        "Unsigned32",
        "Gauge32",
        "Counter32",
        "Counter64",
    ):
        if isinstance(value, int):
            result = value
        else:
            try:
                result = int(value)
            except (ValueError, TypeError):
                result = str(value)
    else:
        result = str(value) if not isinstance(value, str) else value

    return result


def load_table_schema_context(
    table_oid: str,
    fallback_index_values: dict[str, Any],
    logger: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Load table schema context from the API, falling back to provided index values."""
    try:
        import httpx

        schema_response = httpx.get(
            "http://127.0.0.1:8800/table-schema",
            params={"oid": table_oid},
            timeout=5,
        )
        schema_response.raise_for_status()
        table_schema = schema_response.json()
        columns = table_schema.get("columns", {})
        index_columns = table_schema.get("index_columns", [])
        if isinstance(columns, dict) and isinstance(index_columns, list):
            return columns, [str(col) for col in index_columns]
    except Exception as exc:
        logger.warning(f"Could not fetch table schema: {exc}")

    return {}, [str(col) for col in fallback_index_values.keys()]


def build_instance_index_string(
    index_columns: list[str],
    request_index_values: dict[str, Any],
    columns: dict[str, Any],
    entry_oid: tuple[int, ...],
) -> str:
    """Build an instance index string from index column values."""
    index_oid = entry_oid + (1,)
    instance_index_str = ""

    for idx_col_name in index_columns:
        if idx_col_name not in request_index_values:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required index column: {idx_col_name}",
            )

        converted_val = convert_index_value(
            idx_col_name,
            request_index_values[idx_col_name],
            columns,
        )

        if isinstance(converted_val, tuple):
            index_oid = index_oid + converted_val
            instance_index_str += "." + ".".join(str(x) for x in converted_val)
        else:
            int_val = (
                int(converted_val)
                if isinstance(converted_val, (int, float))
                else int(str(converted_val))
            )
            index_oid = index_oid + (int_val,)
            instance_index_str += f".{int_val}"

    return instance_index_str.lstrip(".")


def find_table_and_entry(
    parts: tuple[int, ...],
    schemas: dict[str, Any],
) -> tuple[Any, Any, Any, Any, Any, list[tuple[str, tuple[int, ...]]]]:
    """Find table and entry information from schemas based on OID parts."""
    table_info = None
    table_name = None
    mib_name = None
    entry_info = None
    entry_name = None
    candidate_tables: list[tuple[str, tuple[int, ...]]] = []

    for mib, schema in schemas.items():
        objects = extract_schema_objects(schema)
        for obj_name, obj_data in objects.items():
            if not (isinstance(obj_data, dict) and "oid" in obj_data):
                continue

            obj_oid_t = tuple(obj_data["oid"])
            if obj_data.get("type") == "MibTable":
                candidate_tables.append((f"{mib}.{obj_name}", obj_oid_t))

            if obj_oid_t == parts and obj_data.get("type") == "MibTable":
                table_info = obj_data
                table_name = obj_name
                mib_name = mib
            elif (
                len(obj_oid_t) == len(parts) + 1
                and obj_oid_t[:-1] == parts
                and obj_oid_t[-1] == 1
                and obj_data.get("type") == "MibTableRow"
            ):
                entry_info = obj_data
                entry_name = obj_name

    return table_info, table_name, mib_name, entry_info, entry_name, candidate_tables


def collect_table_columns(
    schemas: dict[str, Any],
    entry_oid: tuple[int, ...],
    index_columns: list[str],
    foreign_keys: list[str],
) -> dict[str, Any]:
    """Collect all column metadata for a table from schemas."""
    columns: dict[str, Any] = {}
    for schema in schemas.values():
        objects = extract_schema_objects(schema)
        for obj_name, obj_data in objects.items():
            if not (isinstance(obj_data, dict) and "oid" in obj_data):
                continue
            obj_oid_t = tuple(obj_data["oid"])
            if len(obj_oid_t) > len(entry_oid) and obj_oid_t[: len(entry_oid)] == entry_oid:
                columns[obj_name] = {
                    "oid": list(obj_oid_t),
                    "type": obj_data.get("type", ""),
                    "access": obj_data.get("access", ""),
                    "is_index": obj_name in index_columns,
                    "is_foreign_key": obj_name in foreign_keys,
                    "default": obj_data.get("initial", ""),
                    "enums": obj_data.get("enums"),
                }
    return columns


def normalize_and_extract_instances(
    table_info: dict[str, Any],
    index_columns: list[str],
    columns: dict[str, Any],
    table_name: str,
    logger: Any,
) -> list[str]:
    """Normalize table rows and extract instance index strings."""
    rows_data = table_info.get("rows", [])
    instances: list[str] = []

    for row_data in rows_data:
        if not isinstance(row_data, dict):
            continue

        for idx_col in index_columns:
            if idx_col in row_data and idx_col in columns:
                idx_value = row_data[idx_col]
                col_info = columns[idx_col]
                col_type = col_info.get("type", "")
                should_fix_zero = False
                if col_type in ("InterfaceIndex", "InterfaceIndexOrZero"):
                    should_fix_zero = col_type == "InterfaceIndex"
                if should_fix_zero and idx_value == 0 and isinstance(idx_value, int):
                    row_data[idx_col] = 1
                    logger.debug(
                        "Fixed invalid index value 0 for column %s (%s) in %s; changed to 1",
                        idx_col,
                        col_type,
                        table_name,
                    )

        instance_parts = []
        for idx_col in index_columns:
            if idx_col in row_data:
                instance_parts.append(str(row_data[idx_col]))
        instances.append(".".join(instance_parts) if instance_parts else "1")

    return instances


def inject_virtual_index_columns(
    columns: dict[str, Any],
    instances: list[str],
    index_columns: list[str],
) -> list[str]:
    """Inject virtual index columns when no index columns are defined."""
    if index_columns:
        return index_columns

    max_parts = 1
    for inst in instances:
        max_parts = max(max_parts, len(str(inst).split(".")))

    virtual_index_cols = []
    for i in range(1, max_parts + 1):
        col_name = "__index__" if i == 1 else f"__index_{i}__"
        virtual_index_cols.append(col_name)
        columns[col_name] = {
            "oid": [],
            "type": "Integer32",
            "access": "read-write",
            "is_index": True,
            "default": "1" if i == 1 else "",
            "enums": None,
        }

    return virtual_index_cols
