"""Table schema, values, and tree endpoints."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_shared import DecodedValue, JsonObject, JsonValue, as_oid_list
from app.api_state import logger, state
from app.api_table_helpers import (
    collect_table_columns,
    find_table_and_entry,
    inject_virtual_index_columns,
    load_all_agent_schemas,
    normalize_and_extract_instances,
)
from app.cli_load_model import load_all_schemas
from app.model_paths import AGENT_MODEL_DIR
from app.oid_utils import oid_str_to_tuple

router = APIRouter()

SCHEMA_DIR = str(AGENT_MODEL_DIR)


def _make_jsonable(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_make_jsonable(x) for x in v]
    try:
        return str(v)
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        return repr(v)


@router.get("/table-schema")
async def get_table_schema(oid: str) -> dict[str, object]:
    """Get schema information for a table OID."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        parts = oid_str_to_tuple(oid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid OID format") from None

    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_agent_schemas()

    table_info, table_name, mib_name, entry_info, entry_name, candidate_tables = (
        find_table_and_entry(parts, schemas)
    )

    if table_info is None:
        logger.debug(
            "/table-schema: requested OID %s - candidate tables found: %s",
            parts,
            candidate_tables,
        )

    if not table_info:
        raise HTTPException(status_code=404, detail="Table not found")

    entry_oid = (*parts, 1)
    index_columns = entry_info.get("indexes", []) if entry_info else []
    foreign_keys = entry_info.get("foreign_keys", []) if entry_info else []
    columns = collect_table_columns(schemas, entry_oid, index_columns, foreign_keys)

    logger.info("%s", f"/table-schema: columns found for {parts}: {list(columns.keys())}")

    instances = normalize_and_extract_instances(
        table_info=table_info,
        index_columns=index_columns,
        columns=columns,
        table_name=str(table_name),
        logger=logger,
    )

    oid_str = ".".join(str(x) for x in parts)
    if state.snmp_agent and oid_str in state.snmp_agent.table_instances:
        for instance_key in state.snmp_agent.table_instances[oid_str]:
            if instance_key not in instances:
                instances.append(instance_key)

    if state.snmp_agent:
        instances = [
            inst
            for inst in instances
            if f"{oid_str}.{inst}" not in state.snmp_agent.deleted_instances
        ]

    index_columns = inject_virtual_index_columns(columns, instances, index_columns)

    return {
        "name": table_name,
        "oid": parts,
        "mib": mib_name,
        "entry_oid": entry_oid,
        "entry_name": entry_name,
        "index_columns": index_columns,
        "foreign_keys": foreign_keys,
        "index_from": entry_info.get("index_from", []) if entry_info else [],
        "columns": columns,
        "instances": instances,
    }


@router.get("/value")
def get_oid_value(oid: str) -> dict[str, object]:
    """Get the value for a specific OID string (dot separated)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = oid_str_to_tuple(oid)
    except ValueError:
        logger.exception("Invalid OID format requested: %s", oid)
        raise HTTPException(status_code=400, detail="Invalid OID format") from None

    try:
        value = state.snmp_agent.get_scalar_value(parts)
    except ValueError:
        value = _try_get_table_cell_value(parts)
        if value is not None:
            return {"oid": parts, "value": value}
        logger.warning("OID not found (not scalar or table cell): %s", parts)
        raise HTTPException(
            status_code=404, detail=f"OID not settable: Scalar OID {parts} not found"
        ) from None
    except (AttributeError, LookupError, OSError, TypeError):
        logger.exception("Unexpected error fetching value for OID %s", parts)
        raise HTTPException(status_code=500, detail="Internal server error") from None

    serializable = _make_jsonable(value)
    logger.info("Fetched value for OID %s: %s", parts, serializable)
    return {"oid": parts, "value": serializable}


def _try_get_table_cell_value(parts: tuple[int, ...]) -> DecodedValue | None:
    if state.snmp_agent is None:
        return None

    schemas = load_all_agent_schemas()
    if not schemas:
        return None

    context = _resolve_table_cell_context(parts, schemas)
    if context is None:
        return None

    table_oid_str, table_parts, instance_str, column_name = context

    value = _try_table_instance_value(table_oid_str, instance_str, column_name, parts)
    if value is not None:
        return value

    return _try_schema_row_value(
        schemas=schemas,
        table_parts=table_parts,
        instance_str=instance_str,
        column_name=column_name,
        parts=parts,
    )


def _resolve_table_cell_context(  # noqa: C901, PLR0912
    parts: tuple[int, ...],
    schemas: dict[str, JsonValue],
) -> tuple[str, tuple[int, ...], str, str] | None:
    table_oid_str: str | None = None
    table_parts: tuple[int, ...] | None = None
    instance_str: str | None = None
    column_name: str | None = None

    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        for obj_data in objects.values():
            if not isinstance(obj_data, dict) or obj_data.get("type") != "MibTable":
                continue

            candidate_table_list = as_oid_list(obj_data.get("oid", []))
            if not candidate_table_list:
                continue
            candidate_table_parts = tuple(candidate_table_list)
            entry_oid = (*candidate_table_parts, 1)
            if not (
                len(parts) > len(candidate_table_parts) + 1
                and parts[: len(candidate_table_parts)] == candidate_table_parts
                and parts[len(candidate_table_parts)] == 1
            ):
                continue

            table_parts_local = candidate_table_parts
            table_oid_str = ".".join(str(x) for x in table_parts_local)
            column_num = parts[len(table_parts_local) + 1]
            instance_parts = parts[len(table_parts_local) + 2 :]
            instance_str = ".".join(str(x) for x in instance_parts) if instance_parts else "1"
            table_parts = table_parts_local

            for col_name, col_data in objects.items():
                if not isinstance(col_data, dict) or "oid" not in col_data:
                    continue
                col_oid_list = as_oid_list(col_data.get("oid", []))
                if not col_oid_list:
                    continue
                col_oid_t = tuple(col_oid_list)
                if col_oid_t == (*entry_oid, column_num):
                    column_name = col_name
                    break
            if table_oid_str:
                break
        if table_oid_str:
            break

    if not table_oid_str or not column_name or table_parts is None or instance_str is None:
        return None

    return table_oid_str, table_parts, instance_str, column_name


def _try_table_instance_value(
    table_oid_str: str,
    instance_str: str,
    column_name: str,
    parts: tuple[int, ...],
) -> JsonValue | None:
    if state.snmp_agent is None:
        return None
    if table_oid_str not in state.snmp_agent.table_instances:
        return None

    instances = state.snmp_agent.table_instances[table_oid_str]
    if instance_str not in instances:
        return None

    column_values = instances[instance_str].get("column_values", {})
    if column_name not in column_values:
        return None

    value = column_values[column_name]
    logger.info("Fetched table cell value from table_instances for OID %s: %s", parts, value)
    return value


def _row_matches_instance(row: JsonObject, index_columns: list[str], instance_str: str) -> bool:
    if not index_columns:
        return instance_str == "1"

    row_instance_parts = [str(row[idx_col]) for idx_col in index_columns if idx_col in row]
    row_instance_str = ".".join(row_instance_parts) if row_instance_parts else "1"
    return row_instance_str == instance_str


def _try_schema_row_value(  # noqa: C901, PLR0912
    schemas: dict[str, JsonValue],
    table_parts: tuple[int, ...],
    instance_str: str,
    column_name: str,
    parts: tuple[int, ...],
) -> JsonValue | None:
    entry_oid = (*table_parts, 1)

    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        table_obj: JsonObject | None = None
        entry_obj: JsonObject | None = None
        for obj_data in objects.values():
            if not isinstance(obj_data, dict):
                continue
            obj_oid_list = as_oid_list(obj_data.get("oid", []))
            if not obj_oid_list:
                continue
            obj_oid = tuple(obj_oid_list)
            if obj_data.get("type") == "MibTable" and obj_oid == table_parts:
                table_obj = obj_data
            if obj_data.get("type") == "MibTableRow" and obj_oid == entry_oid:
                entry_obj = obj_data

        if not table_obj or not entry_obj:
            continue

        raw_index_columns = entry_obj.get("indexes", [])
        index_column_names: list[str] = []
        if isinstance(raw_index_columns, list):
            index_column_names = [str(col) for col in raw_index_columns]
        rows = table_obj.get("rows", [])
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            row_obj = row
            if not _row_matches_instance(row_obj, index_column_names, instance_str):
                continue
            if column_name not in row_obj:
                continue
            value = row_obj[column_name]
            logger.info("Fetched table cell value from schema for OID %s: %s", parts, value)
            return value

    return None


@router.get("/values/bulk")
def get_all_values() -> dict[str, object]:
    """Get all OID values in bulk for efficient loading."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    all_oids = state.snmp_agent.get_all_oids()
    values = {}

    for oid_str in all_oids:
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            parts = oid_str_to_tuple(oid_str)
            value = state.snmp_agent.get_scalar_value(parts)
            values[oid_str] = _make_jsonable(value)

    logger.info("%s", f"Bulk fetched {len(values)} OID values")
    return {"count": len(values), "values": values}


class OIDValueUpdate(BaseModel):
    """Request model for updating an OID value."""

    oid: str
    value: str


@router.post("/value")
def set_oid_value(update: OIDValueUpdate) -> dict[str, object]:
    """Set the value for a specific OID string (dot separated)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = tuple(int(x) for x in update.oid.split(".")) if update.oid else ()
    except ValueError:
        logger.exception("Invalid OID format requested: %s", update.oid)
        raise HTTPException(status_code=400, detail="Invalid OID format") from None

    try:
        state.snmp_agent.set_scalar_value(parts, update.value)
        logger.info("%s", f"Set value for OID {parts} to: {update.value}")
    except ValueError as e:
        logger.warning("Cannot set scalar OID: %s - %s", parts, e)
        raise HTTPException(status_code=404, detail=f"OID not settable: {e}") from e
    except (AttributeError, LookupError, OSError, TypeError):
        logger.exception("Unexpected error setting value for OID %s", parts)
        raise HTTPException(status_code=500, detail="Internal server error") from None
    return {"status": "ok", "oid": parts, "new_value": update.value}


@router.get("/tree/bulk")
def get_tree_bulk_data() -> dict[str, object]:  # noqa: C901, PLR0912, PLR0915
    """Get complete tree data including all table instances for efficient GUI loading."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        return {"tables": {}}

    schemas = load_all_schemas(schema_dir)

    tables_data: dict[str, Any] = {}

    index_source_map: dict[str, dict[str, str]] = {}

    for schema in schemas.values():
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        for _obj_data in objects.values():
            if isinstance(_obj_data, dict) and _obj_data.get("type") == "MibTableRow":
                index_from = _obj_data.get("index_from", [])
                if index_from and isinstance(index_from, list) and len(index_from) > 0:
                    source_info = index_from[0]
                    if not isinstance(source_info, dict):
                        continue
                    source_mib = source_info.get("mib")
                    source_column = source_info.get("column")
                    if not isinstance(source_mib, str) or not isinstance(source_column, str):
                        continue
                    table_oid_parts = _obj_data.get("oid", [])
                    if table_oid_parts and len(table_oid_parts) > 0 and table_oid_parts[-1] == 1:
                        table_oid = ".".join(str(x) for x in table_oid_parts[:-1])
                        index_source_map[table_oid] = {
                            "mib": source_mib,
                            "column": source_column,
                        }

    for schema in schemas.values():
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                table_oid = ".".join(str(x) for x in obj_data["oid"])

                entry_name = None
                entry_obj = {}
                table_oid_parts = obj_data["oid"]
                expected_entry_oid = [*table_oid_parts, 1]

                for other_name, other_data in objects.items():
                    if (
                        isinstance(other_data, dict)
                        and other_data.get("type") == "MibTableRow"
                        and list(other_data.get("oid", [])) == expected_entry_oid
                    ):
                        entry_name = other_name
                        entry_obj = other_data
                        break

                index_columns = entry_obj.get("indexes", [])

                instances: list[str] = []
                try:
                    if table_oid in index_source_map:
                        source_info = index_source_map[table_oid]
                        source_mib = source_info.get("mib", "")
                        source_column = source_info.get("column", "")

                        if table_oid.endswith(".31.1.1"):
                            logger.debug(
                                "Fetching parent instances for %s (%s) from %s.%s",
                                obj_name,
                                table_oid,
                                source_mib,
                                source_column,
                            )
                        if source_mib in schemas:
                            source_schema = schemas[source_mib]
                            source_objects: dict[str, Any] = {}
                            if isinstance(source_schema, dict):
                                candidate_source_objects = source_schema.get(
                                    "objects", source_schema
                                )
                                if isinstance(candidate_source_objects, dict):
                                    source_objects = candidate_source_objects
                            if not source_objects:
                                continue

                            parent_table_obj = None
                            if source_column in source_objects:
                                col_data = source_objects[source_column]
                                if isinstance(col_data, dict):
                                    col_oid = tuple(col_data.get("oid", []))
                                    if len(col_oid) > 1:
                                        entry_oid = col_oid[:-1]
                                        if len(entry_oid) > 0 and entry_oid[-1] == 1:
                                            table_oid_parts = entry_oid[:-1]
                                            for tbl_data in source_objects.values():
                                                if (
                                                    isinstance(tbl_data, dict)
                                                    and tbl_data.get("type") == "MibTable"
                                                    and list(tbl_data.get("oid", []))
                                                    == list(table_oid_parts)
                                                ):
                                                    parent_table_obj = tbl_data
                                                    break

                            if parent_table_obj:
                                source_rows = parent_table_obj.get("rows", [])
                                source_entry_obj = {}

                                source_entry_oid = [*list(parent_table_obj.get("oid", [])), 1]
                                for source_entry_data in source_objects.values():
                                    if (
                                        isinstance(source_entry_data, dict)
                                        and source_entry_data.get("type") == "MibTableRow"
                                        and list(source_entry_data.get("oid", []))
                                        == source_entry_oid
                                    ):
                                        source_entry_obj = source_entry_data
                                        break

                                source_indexes = source_entry_obj.get("indexes", [])

                                if isinstance(source_rows, list):
                                    for row in source_rows:
                                        if isinstance(row, dict):
                                            parts = []
                                            for idx_col in source_indexes:
                                                if idx_col in row:
                                                    val = row[idx_col]
                                                    col_meta = source_objects.get(idx_col, {})
                                                    if col_meta.get(
                                                        "type"
                                                    ) == "IpAddress" and isinstance(val, str):
                                                        parts.extend(val.split("."))
                                                    else:
                                                        parts.append(str(val))
                                            if parts:
                                                instances.append(".".join(parts))

                        if table_oid.endswith(".31.1.1"):
                            logger.debug(
                                "After fetching parent instances for %s: %s", obj_name, instances
                            )
                    else:
                        rows = obj_data.get("rows", [])
                        if isinstance(rows, list):
                            for row in rows:
                                if isinstance(row, dict):
                                    parts = []
                                    for idx_col in index_columns:
                                        if idx_col in row:
                                            val = row[idx_col]
                                            col_meta = objects.get(idx_col, {})
                                            if col_meta.get("type") == "IpAddress" and isinstance(
                                                val, str
                                            ):
                                                parts.extend(val.split("."))
                                            else:
                                                parts.append(str(val))
                                    if parts:
                                        instances.append(".".join(parts))

                    has_index_from = isinstance(entry_obj, dict) and bool(
                        entry_obj.get("index_from")
                    )
                    is_in_index_source = table_oid in index_source_map
                    is_augmented = has_index_from or is_in_index_source

                    if not is_augmented and table_oid in state.snmp_agent.table_instances:
                        for inst_key in state.snmp_agent.table_instances[table_oid]:
                            if inst_key not in instances:
                                instances.append(inst_key)
                except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                    logger.warning("Error getting instances for table %s: %s", obj_name, e)

                if instances:
                    tables_data[table_oid] = {
                        "table_name": obj_name,
                        "entry_name": entry_name,
                        "index_columns": index_columns,
                        "instances": instances,
                    }

    logger.info("%s", f"Bulk tree data: {len(tables_data)} tables with instances")

    return {"tables": tables_data}
