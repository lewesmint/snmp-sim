"""Table row management endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_shared import JsonValue  # noqa: TC001
from app.api_state import logger, state
from app.api_table_helpers import (
    build_instance_index_string,
    extract_instance_index_str,
    get_default_row_from_schemas,
    load_all_agent_schemas,
    load_table_schema_context,
    merge_column_defaults,
    parse_index_values,
)

router = APIRouter()


class CreateTableRowRequest(BaseModel):
    """Request to create a new table row."""

    table_oid: str
    index_values: dict[str, JsonValue]
    column_values: dict[str, JsonValue] = {}


@router.post("/table-row")
def create_table_row(request: CreateTableRowRequest) -> dict[str, object]:
    """Create a new instance in a table."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        schemas = load_all_agent_schemas()

        logger.info("%s", f"Creating table instance for {request.table_oid}")
        logger.info(
            "%s",
            f"  index_values: {request.index_values} (type: {type(request.index_values)})",
        )
        logger.info("%s", f"  column_values: {request.column_values}")

        if request.column_values:
            for col_name, col_val in request.column_values.items():
                logger.info("%s", f"    {col_name}: {col_val} (type: {type(col_val).__name__})")

        table_parts = (
            tuple(int(x) for x in request.table_oid.split(".")) if request.table_oid else ()
        )
        entry_oid = (*table_parts, 1)

        columns, index_columns = load_table_schema_context(
            request.table_oid,
            request.index_values,
            logger,
        )

        if not index_columns:
            index_str = extract_instance_index_str(request.index_values)
            parsed_index_values = parse_index_values(index_str)

            default_row = get_default_row_from_schemas(schemas, request.table_oid)
            incoming_values = request.column_values or {}
            merged_values_simple = merge_column_defaults(
                columns=columns,
                incoming_values=incoming_values,
                default_row=default_row,
                excluded_columns=set(parsed_index_values.keys()),
            )

            instance_oid = state.snmp_agent.add_table_instance(
                table_oid=request.table_oid,
                index_values=cast("dict[str, JsonValue]", parsed_index_values),
                column_values=merged_values_simple,
            )
            logger.info("Successfully created table instance: %s", instance_oid)
            return {
                "status": "ok",
                "table_oid": request.table_oid,
                "instance_index": index_str,
                "instance_oid": instance_oid,
                "columns_created": (
                    [str(col) for col in merged_values_simple] if merged_values_simple else []
                ),
            }

        instance_index_str = build_instance_index_string(
            index_columns=index_columns,
            request_index_values=request.index_values,
            columns=columns,
            entry_oid=entry_oid,
        )

        default_row = get_default_row_from_schemas(schemas, request.table_oid)
        incoming_values = request.column_values or {}
        merged_values = merge_column_defaults(
            columns=columns,
            incoming_values=incoming_values,
            default_row=default_row,
            excluded_columns=set(index_columns),
        )

        instance_oid = state.snmp_agent.add_table_instance(
            table_oid=request.table_oid,
            index_values=request.index_values,
            column_values=merged_values,
        )

        logger.info("Successfully created table instance: %s", instance_oid)

        return {
            "status": "ok",
            "table_oid": request.table_oid,
            "instance_index": instance_index_str,
            "instance_oid": instance_oid,
            "columns_created": ([str(col) for col in merged_values] if merged_values else []),
        }
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.exception("Failed to create table instance")
        raise HTTPException(status_code=500, detail=f"Failed to create instance: {e!s}") from e


@router.delete("/table-row")
def delete_table_row(request: CreateTableRowRequest) -> dict[str, object]:
    """Delete a table instance (soft delete, marks as deleted)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        index_values = request.index_values or {}
        index_str = extract_instance_index_str(index_values)
        parsed_index_values = parse_index_values(index_str)

        success = state.snmp_agent.delete_table_instance(
            table_oid=request.table_oid,
            index_values=cast("dict[str, JsonValue]", parsed_index_values),
        )

        if success:
            logger.info(
                "%s",
                f"Deleted table instance: {request.table_oid} with indices {request.index_values}",
            )
            return {
                "status": "deleted",
                "table_oid": request.table_oid,
                "index_values": index_values,
            }
        raise HTTPException(status_code=404, detail="Table instance not found")
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.exception("Failed to delete table instance")
        raise HTTPException(status_code=500, detail=f"Failed to delete instance: {e!s}") from e
