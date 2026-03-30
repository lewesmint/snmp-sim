"""Trap and notification endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    NotificationType,
    ObjectIdentity,
    SnmpEngine,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.smi import view
from pysnmp.smi.error import MibNotFoundError, SmiError

from app.api_shared import MIN_PARENT_OID_LEN, JsonObject
from app.api_state import logger, state
from app.cli_load_model import load_all_schemas
from app.model_paths import AGENT_MODEL_DIR, CONFIG_DIR, TRAP_OVERRIDES_FILE

router = APIRouter()

SCHEMA_DIR = str(AGENT_MODEL_DIR)


@router.get("/traps")
def list_traps() -> dict[str, object]:
    """List all available SNMP traps/notifications from all loaded MIBs."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    all_traps: dict[str, object] = {}

    for mib_name, schema in schemas.items():
        if isinstance(schema, dict) and isinstance(schema.get("traps"), dict):
            traps_obj = schema.get("traps", {})
            if not isinstance(traps_obj, dict):
                continue
            for trap_name, trap_data in traps_obj.items():
                if not isinstance(trap_data, dict):
                    continue
                trap_info = {
                    **trap_data,
                    "mib": mib_name,
                    "full_name": f"{mib_name}::{trap_name}",
                }
                all_traps[trap_name] = trap_info

    return {"count": len(all_traps), "traps": all_traps}


def _load_trap_overrides_from_data() -> dict[str, JsonObject]:
    overrides_path = TRAP_OVERRIDES_FILE
    try:
        if overrides_path.exists():
            with overrides_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to load trap overrides from config: %s", exc)
    return {}


def _save_trap_overrides_to_data(overrides: dict[str, JsonObject]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    overrides_path = TRAP_OVERRIDES_FILE
    try:
        pruned_overrides: dict[str, JsonObject] = {}
        for name, data in overrides.items():
            cleaned: JsonObject = {}
            for oid_name, entry in data.items():
                if isinstance(entry, dict):
                    enabled = bool(entry.get("enabled"))
                    value = str(entry.get("value", ""))
                    if enabled or value:
                        cleaned[oid_name] = {"value": value, "enabled": enabled}
                elif entry not in (None, ""):
                    cleaned[oid_name] = str(entry)
            if cleaned:
                pruned_overrides[name] = cleaned

        with overrides_path.open("w", encoding="utf-8") as f:
            json.dump(pruned_overrides, f, indent=2)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to save trap overrides to config: %s", exc)


trap_overrides: dict[str, JsonObject] = _load_trap_overrides_from_data()


@router.get("/trap-overrides/{trap_name}")
def get_trap_overrides(trap_name: str) -> dict[str, object]:
    """Get stored overrides for a specific trap."""
    return {"trap_name": trap_name, "overrides": trap_overrides.get(trap_name, {})}


@router.post("/trap-overrides/{trap_name}")
def set_trap_overrides(trap_name: str, overrides: JsonObject) -> dict[str, object]:
    """Set overrides for a specific trap."""
    trap_overrides[trap_name] = overrides
    _save_trap_overrides_to_data(trap_overrides)
    return {"status": "ok", "trap_name": trap_name, "overrides": overrides}


@router.delete("/trap-overrides/{trap_name}")
def clear_trap_overrides(trap_name: str) -> dict[str, object]:
    """Clear all overrides for a specific trap."""
    if trap_name in trap_overrides:
        del trap_overrides[trap_name]
        _save_trap_overrides_to_data(trap_overrides)
    return {"status": "ok", "trap_name": trap_name}


def _find_trap_definition(
    schemas: dict[str, Any],
    trap_name: str,
) -> tuple[dict[str, Any], str] | None:
    for candidate_mib_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        traps_obj = schema.get("traps", {})
        if not isinstance(traps_obj, dict):
            continue
        trap_candidate = traps_obj.get(trap_name)
        if isinstance(trap_candidate, dict):
            return trap_candidate, candidate_mib_name
    return None


def _get_schema_objects(schemas: dict[str, Any], mib_name: str) -> dict[str, Any]:
    obj_schema = schemas.get(mib_name, {})
    if not isinstance(obj_schema, dict):
        return {}
    schema_objects_candidate = obj_schema.get("objects", obj_schema)
    if not isinstance(schema_objects_candidate, dict):
        return {}
    return schema_objects_candidate


def _unknown_varbind_metadata(obj_mib: str, obj_name: str) -> dict[str, object]:
    return {
        "mib": obj_mib,
        "name": obj_name,
        "oid": [],
        "type": "Unknown",
        "access": "unknown",
        "is_index": False,
        "parent_table": None,
    }


def _find_row_data_for_parent_oid(
    schema_objects: dict[str, Any],
    parent_oid: tuple[int, ...],
) -> dict[str, Any] | None:
    for check_data in schema_objects.values():
        if (
            isinstance(check_data, dict)
            and tuple(check_data.get("oid", [])) == parent_oid
            and check_data.get("type") == "MibTableRow"
        ):
            return check_data
    return None


def _find_table_data_for_row_oid(
    schema_objects: dict[str, Any],
    table_oid: tuple[int, ...],
) -> tuple[str, dict[str, Any]] | None:
    for table_name, table_data in schema_objects.items():
        if (
            isinstance(table_data, dict)
            and tuple(table_data.get("oid", [])) == table_oid
            and table_data.get("type") == "MibTable"
        ):
            return table_name, table_data
    return None


def _collect_row_columns_meta(
    schema_objects: dict[str, Any],
    row_oid: tuple[int, ...],
) -> dict[str, dict[str, object]]:
    columns_meta: dict[str, dict[str, object]] = {}
    for col_name, col_data in schema_objects.items():
        if not isinstance(col_data, dict):
            continue
        col_oid = tuple(col_data.get("oid", []))
        if len(col_oid) > len(row_oid) and col_oid[: len(row_oid)] == row_oid:
            columns_meta[col_name] = {
                "oid": list(col_oid),
                "type": col_data.get("type", "Unknown"),
                "access": col_data.get("access", "unknown"),
            }
    return columns_meta


def _resolve_parent_table_details(
    schema_objects: dict[str, Any],
    obj_oid: list[int],
    obj_name: str,
) -> tuple[dict[str, object] | None, bool, dict[str, object] | None]:
    if len(obj_oid) <= MIN_PARENT_OID_LEN:
        return None, False, None

    row_oid = tuple(obj_oid[:-1])
    row_data = _find_row_data_for_parent_oid(schema_objects, row_oid)
    if row_data is None:
        return None, False, None

    if not row_oid:
        return None, False, None

    table_oid = tuple(row_oid[:-1])
    table_info = _find_table_data_for_row_oid(schema_objects, table_oid)
    if table_info is None:
        return None, False, None

    table_name, table_data = table_info
    table_index_cols = row_data.get("indexes", [])
    if not isinstance(table_index_cols, list):
        table_index_cols = []

    parent_table: dict[str, object] = {
        "name": table_name,
        "oid": list(table_oid),
        "index_columns": table_index_cols,
    }

    context: dict[str, object] = {
        "parent_table_oid": list(table_oid),
        "parent_table_name": table_name,
        "index_columns": table_index_cols,
        "instances": table_data.get("instances", []),
        "columns_meta": _collect_row_columns_meta(schema_objects, row_oid),
    }
    return parent_table, obj_name in table_index_cols, context


@router.get("/trap-varbinds/{trap_name}")
def get_trap_varbinds(trap_name: str) -> dict[str, object]:
    """Get detailed varbind metadata for a specific trap."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    trap_found = _find_trap_definition(schemas, trap_name)
    if trap_found is None:
        raise HTTPException(status_code=404, detail=f"Trap '{trap_name}' not found")

    trap_info, mib_name = trap_found

    varbind_objects = trap_info.get("objects", [])

    varbinds_metadata = []
    parent_table_oid: list[int] | None = None
    parent_table_name: str | None = None
    index_columns: list[str] = []
    instances: list[object] = []
    columns_meta: dict[str, dict[str, object]] = {}

    for varbind_obj in varbind_objects:
        obj_mib = varbind_obj.get("mib", "")
        obj_name = varbind_obj.get("name", "")

        schema_objects = _get_schema_objects(schemas, obj_mib)

        obj_data = schema_objects.get(obj_name, {})

        if not obj_data:
            varbinds_metadata.append(_unknown_varbind_metadata(obj_mib, obj_name))
            continue

        obj_oid = obj_data.get("oid", [])
        obj_type = obj_data.get("type", "Unknown")
        obj_access = obj_data.get("access", "unknown")
        if not isinstance(obj_oid, list):
            obj_oid = []

        parent_table, is_index, context = _resolve_parent_table_details(
            schema_objects,
            obj_oid,
            obj_name,
        )
        if context is not None and parent_table_oid is None:
            context_parent_oid = context.get("parent_table_oid")
            if isinstance(context_parent_oid, list):
                parent_table_oid = context_parent_oid

            context_parent_name = context.get("parent_table_name")
            if isinstance(context_parent_name, str):
                parent_table_name = context_parent_name

            context_index_columns = context.get("index_columns")
            if isinstance(context_index_columns, list):
                index_columns = [item for item in context_index_columns if isinstance(item, str)]

            context_instances = context.get("instances")
            if isinstance(context_instances, list):
                instances = context_instances

            context_columns_meta = context.get("columns_meta")
            if isinstance(context_columns_meta, dict):
                columns_meta = {
                    key: value
                    for key, value in context_columns_meta.items()
                    if isinstance(key, str) and isinstance(value, dict)
                }

        varbinds_metadata.append(
            {
                "mib": obj_mib,
                "name": obj_name,
                "oid": obj_oid,
                "type": obj_type,
                "access": obj_access,
                "is_index": is_index,
                "parent_table": parent_table,
            }
        )

    return {
        "trap_name": trap_name,
        "mib": mib_name,
        "varbinds": varbinds_metadata,
        "parent_table_oid": parent_table_oid,
        "parent_table_name": parent_table_name,
        "index_columns": index_columns,
        "instances": instances,
        "columns_meta": columns_meta,
    }


class TrapSendRequest(BaseModel):
    """Request model for sending an SNMP trap or inform."""

    trap_name: str
    trap_type: Literal["trap", "inform"] = "trap"
    dest_host: str | None = "localhost"
    dest_port: int | None = 162
    community: str | None = "public"


def _apply_trap_object_values(
    *,
    schemas: dict[str, Any],
    trap_name: str,
    values_by_object: dict[str, str | int],
) -> list[dict[str, object]]:
    """Apply scalar values for named trap objects before sending a notification."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    trap_found = _find_trap_definition(schemas, trap_name)
    if trap_found is None:
        raise HTTPException(status_code=404, detail=f"Trap '{trap_name}' not found")

    trap_info, _ = trap_found
    trap_objects = trap_info.get("objects", [])
    if not isinstance(trap_objects, list):
        raise HTTPException(status_code=500, detail=f"Trap '{trap_name}' objects are invalid")

    applied: list[dict[str, object]] = []

    for trap_obj in trap_objects:
        if not isinstance(trap_obj, dict):
            continue
        obj_name = trap_obj.get("name")
        obj_mib = trap_obj.get("mib")
        if not isinstance(obj_name, str) or not isinstance(obj_mib, str):
            continue
        if obj_name not in values_by_object:
            continue

        schema_objects = _get_schema_objects(schemas, obj_mib)
        obj_data = schema_objects.get(obj_name)
        if not isinstance(obj_data, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Object metadata not found: {obj_mib}::{obj_name}",
            )

        oid_raw = obj_data.get("oid", [])
        if not isinstance(oid_raw, list) or not all(isinstance(part, int) for part in oid_raw):
            raise HTTPException(
                status_code=400,
                detail=f"Object OID invalid: {obj_mib}::{obj_name}",
            )

        value = values_by_object[obj_name]
        try:
            state.snmp_agent.set_scalar_value(tuple(oid_raw), str(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to set {obj_mib}::{obj_name}: {exc}",
            ) from exc
        except (AttributeError, LookupError, OSError, TypeError) as exc:
            logger.exception("Failed applying trap object override for %s::%s", obj_mib, obj_name)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set {obj_mib}::{obj_name}",
            ) from exc

        applied.append(
            {
                "mib": obj_mib,
                "name": obj_name,
                "oid": oid_raw,
                "value": value,
            }
        )

    return applied


async def _send_named_trap(request: TrapSendRequest) -> dict[str, object]:
    """Shared send flow used by generic and script-oriented trap endpoints."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    trap_found = _find_trap_definition(schemas, request.trap_name)
    if trap_found is None:
        raise HTTPException(status_code=404, detail=f"Trap '{request.trap_name}' not found")
    trap_info, mib_name = trap_found

    snmp_engine = _get_snmp_engine_or_raise()
    notif = _resolve_notification_or_raise(snmp_engine, mib_name, request.trap_name)
    error_indication, error_status, error_index, _ = await _send_notification_or_raise(
        snmp_engine=snmp_engine,
        request=request,
        notification=notif,
    )
    _raise_if_send_failed(error_indication, error_status, error_index)

    trap_oid = tuple(trap_info["oid"])

    logger.info(
        "Sent %s for trap %s (%s::%s, OID: %s) to %s:%s",
        request.trap_type,
        request.trap_name,
        mib_name,
        request.trap_name,
        trap_oid,
        request.dest_host,
        request.dest_port,
    )

    return {
        "status": "ok",
        "trap_name": request.trap_name,
        "trap_oid": trap_oid,
        "trap_type": request.trap_type,
        "destination": f"{request.dest_host}:{request.dest_port}",
        "mib": mib_name,
        "objects": trap_info.get("objects", []),
    }


class CompletionCommandRequest(BaseModel):
    """Script-friendly request for completionTrap notifications."""

    completion_source: str = "CLI"
    completion_code: int = 0
    dest_host: str = "localhost"
    dest_port: int = 162
    community: str = "public"
    trap_type: Literal["trap", "inform"] = "trap"


class EventCommandRequest(BaseModel):
    """Script-friendly request for eventTrap notifications."""

    event_severity: int = Field(default=2, ge=0, le=5)
    event_text: str = "Equipment event"
    dest_host: str = "localhost"
    dest_port: int = 162
    community: str = "public"
    trap_type: Literal["trap", "inform"] = "trap"


def _get_snmp_engine_or_raise() -> SnmpEngine:
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")
    snmp_engine = state.snmp_agent.snmp_engine
    if snmp_engine is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")
    return snmp_engine


def _resolve_notification_or_raise(
    snmp_engine: SnmpEngine,
    mib_name: str,
    trap_name: str,
) -> NotificationType:
    mib_builder = snmp_engine.get_mib_builder()
    mib_view = view.MibViewController(mib_builder)

    try:
        mib_builder.load_modules(mib_name)
    except MibNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"MIB module not found: {mib_name}. {exc}",
        ) from exc

    try:
        return NotificationType(ObjectIdentity(mib_name, trap_name)).resolve_with_mib(mib_view)
    except (SmiError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to resolve notification {mib_name}::{trap_name}. {exc}",
        ) from exc


async def _send_notification_or_raise(
    *,
    snmp_engine: SnmpEngine,
    request: TrapSendRequest,
    notification: NotificationType,
) -> tuple[object, object, object, object]:
    try:
        result = await send_notification(
            snmp_engine,
            CommunityData(request.community or "public"),
            await UdpTransportTarget.create(
                (request.dest_host or "localhost", request.dest_port or 162)
            ),
            ContextData(),
            request.trap_type,
            notification,
        )
        return cast("tuple[object, object, object, object]", result)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
        logger.exception("Failed to send trap")
        raise HTTPException(status_code=500, detail=f"Failed to send trap: {exc}") from exc


def _raise_if_send_failed(
    error_indication: object,
    error_status: object,
    error_index: object,
) -> None:
    if error_indication:
        raise HTTPException(status_code=502, detail=f"SNMP send error: {error_indication}")

    if error_status:
        raise HTTPException(
            status_code=502, detail=f"SNMP send error: {error_status} at {error_index}"
        )


@router.post("/send-trap")
async def send_trap(request: TrapSendRequest) -> dict[str, object]:
    """Send an SNMP trap/notification."""
    return await _send_named_trap(request)


@router.post("/commands/completion")
async def send_completion_command(request: CompletionCommandRequest) -> dict[str, object]:
    """Set completion varbind values and send completionTrap in one scriptable request."""
    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")
    schemas = load_all_schemas(schema_dir)

    applied = _apply_trap_object_values(
        schemas=schemas,
        trap_name="completionTrap",
        values_by_object={
            "completionSource": request.completion_source,
            "completionCode": request.completion_code,
        },
    )

    send_result = await _send_named_trap(
        TrapSendRequest(
            trap_name="completionTrap",
            trap_type=request.trap_type,
            dest_host=request.dest_host,
            dest_port=request.dest_port,
            community=request.community,
        )
    )
    send_result["applied_values"] = applied
    return send_result


@router.post("/commands/event")
async def send_event_command(request: EventCommandRequest) -> dict[str, object]:
    """Set event varbind values and send eventTrap in one scriptable request."""
    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")
    schemas = load_all_schemas(schema_dir)

    applied = _apply_trap_object_values(
        schemas=schemas,
        trap_name="eventTrap",
        values_by_object={
            "eventSeverity": request.event_severity,
            "eventText": request.event_text,
        },
    )

    send_result = await _send_named_trap(
        TrapSendRequest(
            trap_name="eventTrap",
            trap_type=request.trap_type,
            dest_host=request.dest_host,
            dest_port=request.dest_port,
            community=request.community,
        )
    )
    send_result["applied_values"] = applied
    return send_result


class TestTrapRequest(BaseModel):
    """Request model for sending a test SNMP trap."""

    dest_host: str = "localhost"
    dest_port: int = 16662
    community: str = "public"


@router.post("/send-test-trap")
async def send_test_trap(request: TestTrapRequest) -> dict[str, object]:
    """Send a test trap to the specified destination."""
    test_mib = "SNMPv2-MIB"
    test_notification = "coldStart"

    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")
    snmp_engine = state.snmp_agent.snmp_engine
    if snmp_engine is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")

    mib_builder = snmp_engine.get_mib_builder()
    mib_view = view.MibViewController(mib_builder)

    try:
        mib_builder.load_modules(test_mib)
    except MibNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load MIB {test_mib}: {exc}",
        ) from exc

    try:
        notif = NotificationType(ObjectIdentity(test_mib, test_notification)).resolve_with_mib(
            mib_view
        )
    except (SmiError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve test notification: {exc}",
        ) from exc

    try:
        error_indication, error_status, error_index, _ = await send_notification(
            snmp_engine,
            CommunityData(request.community),
            await UdpTransportTarget.create((request.dest_host, request.dest_port)),
            ContextData(),
            "trap",
            notif,
        )
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
        logger.exception("Failed to send test trap")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if error_indication:
        raise HTTPException(status_code=502, detail=str(error_indication))

    if error_status:
        raise HTTPException(status_code=502, detail=f"{error_status} at {error_index}")

    logger.info(
        "Sent test trap %s::%s to %s:%s",
        test_mib,
        test_notification,
        request.dest_host,
        request.dest_port,
    )

    return {
        "status": "ok",
        "mib": test_mib,
        "notification": test_notification,
        "destination": f"{request.dest_host}:{request.dest_port}",
    }
