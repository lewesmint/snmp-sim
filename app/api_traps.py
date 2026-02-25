"""Trap and notification endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    NotificationType,
    ObjectIdentity,
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


@router.get("/trap-varbinds/{trap_name}")
def get_trap_varbinds(trap_name: str) -> dict[str, object]:
    """Get detailed varbind metadata for a specific trap."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    trap_info = None
    mib_name = None

    for candidate_mib_name, schema in schemas.items():
        if isinstance(schema, dict) and isinstance(schema.get("traps"), dict):
            traps_obj = schema.get("traps", {})
            if not isinstance(traps_obj, dict):
                continue
            if trap_name in traps_obj:
                trap_candidate = traps_obj[trap_name]
                if not isinstance(trap_candidate, dict):
                    continue
                trap_info = trap_candidate
                mib_name = candidate_mib_name
                break

    if not trap_info or mib_name is None:
        raise HTTPException(status_code=404, detail=f"Trap '{trap_name}' not found")

    varbind_objects = trap_info.get("objects", [])

    varbinds_metadata = []
    parent_table_oid = None
    parent_table_name = None
    index_columns = []
    instances = []
    columns_meta = {}

    for varbind_obj in varbind_objects:
        obj_mib = varbind_obj.get("mib", "")
        obj_name = varbind_obj.get("name", "")

        obj_schema = schemas.get(obj_mib, {})
        schema_objects: dict[str, Any] = {}
        if isinstance(obj_schema, dict):
            schema_objects_candidate = obj_schema.get("objects", obj_schema)
            if isinstance(schema_objects_candidate, dict):
                schema_objects = schema_objects_candidate

        obj_data = schema_objects.get(obj_name, {})

        if not obj_data:
            varbinds_metadata.append(
                {
                    "mib": obj_mib,
                    "name": obj_name,
                    "oid": [],
                    "type": "Unknown",
                    "access": "unknown",
                    "is_index": False,
                    "parent_table": None,
                }
            )
            continue

        obj_oid = obj_data.get("oid", [])
        obj_type = obj_data.get("type", "Unknown")
        obj_access = obj_data.get("access", "unknown")

        is_index = False
        parent_table = None

        if len(obj_oid) > MIN_PARENT_OID_LEN:
            parent_oid = tuple(obj_oid[:-1])

            for check_data in schema_objects.values():
                if (
                    isinstance(check_data, dict)
                    and tuple(check_data.get("oid", [])) == parent_oid
                    and check_data.get("type") == "MibTableRow"
                ):
                    if parent_oid:
                        table_oid = tuple(parent_oid[:-1])

                        for table_name, table_data in schema_objects.items():
                            if (
                                isinstance(table_data, dict)
                                and tuple(table_data.get("oid", [])) == table_oid
                                and table_data.get("type") == "MibTable"
                            ):
                                table_index_cols = check_data.get("indexes", [])
                                parent_table = {
                                    "name": table_name,
                                    "oid": list(table_oid),
                                    "index_columns": table_index_cols,
                                }

                                if obj_name in table_index_cols:
                                    is_index = True

                                if parent_table_oid is None:
                                    parent_table_oid = list(table_oid)
                                    parent_table_name = table_name
                                    index_columns = table_index_cols
                                    instances = table_data.get("instances", [])

                                    for col_name, col_data in schema_objects.items():
                                        if isinstance(col_data, dict):
                                            col_oid = tuple(col_data.get("oid", []))
                                            if (
                                                len(col_oid) > len(parent_oid)
                                                and col_oid[: len(parent_oid)] == parent_oid
                                            ):
                                                columns_meta[col_name] = {
                                                    "oid": list(col_oid),
                                                    "type": col_data.get("type", "Unknown"),
                                                    "access": col_data.get("access", "unknown"),
                                                }
                    break

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


@router.post("/send-trap")
async def send_trap(request: TrapSendRequest) -> dict[str, object]:
    """Send an SNMP trap/notification."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    trap_info = None
    mib_name = None

    for candidate_mib_name, schema in schemas.items():
        if isinstance(schema, dict) and isinstance(schema.get("traps"), dict):
            traps_obj = schema.get("traps", {})
            if not isinstance(traps_obj, dict):
                continue
            if request.trap_name in traps_obj:
                trap_candidate = traps_obj[request.trap_name]
                if not isinstance(trap_candidate, dict):
                    continue
                trap_info = trap_candidate
                mib_name = candidate_mib_name
                break

    if not trap_info or mib_name is None:
        raise HTTPException(status_code=404, detail=f"Trap '{request.trap_name}' not found")

    snmp_engine = getattr(state.snmp_agent, "snmp_engine", None)
    if snmp_engine is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")

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
        notif = NotificationType(ObjectIdentity(mib_name, request.trap_name)).resolve_with_mib(
            mib_view
        )
    except (SmiError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to resolve notification {mib_name}::{request.trap_name}. {exc}",
        ) from exc

    try:
        error_indication, error_status, error_index, _ = await send_notification(
            snmp_engine,
            CommunityData(request.community or "public"),
            await UdpTransportTarget.create(
                (request.dest_host or "localhost", request.dest_port or 162)
            ),
            ContextData(),
            request.trap_type,
            notif,
        )
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
        logger.exception("Failed to send trap")
        raise HTTPException(status_code=500, detail=f"Failed to send trap: {exc}") from exc

    if error_indication:
        raise HTTPException(status_code=502, detail=f"SNMP send error: {error_indication}")

    if error_status:
        raise HTTPException(
            status_code=502, detail=f"SNMP send error: {error_status} at {error_index}"
        )

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

    snmp_engine = getattr(state.snmp_agent, "snmp_engine", None)
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
