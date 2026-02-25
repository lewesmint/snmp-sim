"""System and type registry endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_state import logger, state
from app.base_type_handler import BaseTypeHandler
from app.model_paths import TYPE_REGISTRY_FILE
from app.type_registry_validator import validate_type_registry_file

router = APIRouter()


def _load_type_registry_json() -> dict[str, dict[str, Any]]:
    """Load type registry JSON, tolerating trailing garbage bytes.

    Some environments can leave trailing NULs or stale bytes after writes.
    Prefer strict parsing first, then fall back to decoding the first valid
    JSON object from the file content.
    """
    raw_text = TYPE_REGISTRY_FILE.read_text(encoding="utf-8", errors="ignore")
    try:
        loaded = json.loads(raw_text)
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        cleaned = raw_text.rstrip("\x00 \t\r\n")
        decoder = json.JSONDecoder()
        loaded, _ = decoder.raw_decode(cleaned)
        return loaded if isinstance(loaded, dict) else {}


class SysDescrUpdate(BaseModel):
    """Request model for updating the system description (sysDescr) value."""

    value: str


@router.get("/sysdescr")
def get_sysdescr() -> dict[str, object]:
    """Get the current system description (sysDescr) value."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
    value = state.snmp_agent.get_scalar_value(oid)
    return {"oid": oid, "value": value}


@router.post("/sysdescr")
def set_sysdescr(update: SysDescrUpdate) -> dict[str, object]:
    """Update the system description (sysDescr) value."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
    state.snmp_agent.set_scalar_value(oid, update.value)
    return {"status": "ok", "oid": oid, "new_value": update.value}


@router.get("/validate-types")
def validate_types() -> dict[str, object]:
    """Validate the type registry JSON file."""
    is_valid, errors, type_count = validate_type_registry_file(str(TYPE_REGISTRY_FILE))

    if not is_valid:
        raise HTTPException(status_code=422, detail={"errors": errors, "valid": False})

    return {
        "valid": True,
        "type_count": type_count,
        "message": f"Type registry validated: {type_count} types found",
    }


@router.get("/type-info/{type_name}")
def get_type_info(type_name: str) -> dict[str, object]:
    """Get information about a specific SNMP type."""
    type_registry = _load_type_registry_json()

    handler = BaseTypeHandler(type_registry=type_registry)
    type_info = handler.get_type_info(type_name)

    if not type_info:
        raise HTTPException(status_code=404, detail=f"Type '{type_name}' not found in registry")

    base_type = handler.resolve_to_base_type(type_name)
    default_value = handler.get_default_value(type_name)

    return {
        "type_name": type_name,
        "base_asn1_type": base_type,
        "default_value": default_value,
        "type_info": type_info,
    }


@router.get("/types")
def list_types() -> dict[str, object]:
    """List all available SNMP types in the registry."""
    type_registry = _load_type_registry_json()

    handler = BaseTypeHandler(type_registry=type_registry)
    all_types = list(handler.type_registry.keys())

    return {"count": len(all_types), "types": sorted(all_types)}


@router.get("/ready")
def check_ready() -> dict[str, object]:
    """Check if the SNMP agent is fully initialized and ready to serve requests."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=503, detail="SNMP agent not initialized")

    if not hasattr(state.snmp_agent, "mib_builder") or state.snmp_agent.mib_builder is None:
        raise HTTPException(status_code=503, detail="SNMP agent still initializing")

    try:
        oid_map = state.snmp_agent.get_all_oids()
        oid_count = len(oid_map)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.warning("Agent not ready: %s", e)
        raise HTTPException(status_code=503, detail=f"SNMP agent not ready: {e}") from e

    return {"ready": True, "oid_count": oid_count}
