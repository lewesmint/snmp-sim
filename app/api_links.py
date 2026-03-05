"""Value link endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_shared import MIN_LINK_ENDPOINTS, JsonValue, as_oid_list
from app.api_state import state
from app.api_table_helpers import load_all_agent_schemas
from app.value_links import ValueLinkEndpoint, get_link_manager

router = APIRouter()


class LinkEndpoint(BaseModel):
    """Endpoint definition for a value link between table columns."""

    table_oid: str | None = None
    column: str
    is_base: bool = False  # Mark which endpoint is the BASE (UI metadata)


class LinkRequest(BaseModel):
    """Request model for creating or managing value links between table columns."""

    id: str | None = None
    scope: Literal["per-instance", "global"] = "per-instance"
    type: Literal["bidirectional"] = "bidirectional"
    match: Literal["shared-index", "same"] = "shared-index"
    endpoints: list[LinkEndpoint]
    description: str | None = None
    create_missing: bool = False


@router.get("/links")
def list_links() -> dict[str, object]:
    """List all links (schema + state)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    link_manager = get_link_manager()
    return {"links": link_manager.export_links(include_schema=True)}


def _build_table_columns_map_from_schemas(
    schemas: dict[str, JsonValue],
) -> dict[str, set[str]]:
    table_columns: dict[str, set[str]] = {}

    for schema in schemas.values():
        objects = schema.get("objects", schema) if isinstance(schema, dict) else {}
        if not isinstance(objects, dict):
            continue

        entry_to_table: dict[tuple[int, ...], str] = {}
        for obj_data in objects.values():
            if not isinstance(obj_data, dict):
                continue
            if obj_data.get("type") != "MibTable":
                continue
            table_oid_list = as_oid_list(obj_data.get("oid", []))
            if not table_oid_list:
                continue
            table_oid = ".".join(str(x) for x in table_oid_list)
            entry_to_table[(*table_oid_list, 1)] = table_oid

        for obj_name, obj_data in objects.items():
            if not isinstance(obj_data, dict):
                continue
            oid_list = as_oid_list(obj_data.get("oid", []))
            if not oid_list:
                continue
            oid_tuple = tuple(oid_list)
            for entry_oid, table_oid in entry_to_table.items():
                entry_len = len(entry_oid)
                if len(oid_tuple) == entry_len + 1 and oid_tuple[:entry_len] == entry_oid:
                    table_columns.setdefault(table_oid, set()).add(obj_name)
                    break

    return table_columns


def _validate_per_instance_link_endpoints(endpoints: list[LinkEndpoint]) -> None:
    if any(not endpoint.table_oid for endpoint in endpoints):
        raise HTTPException(
            status_code=400,
            detail="table_oid is required for per-instance links",
        )

    schemas = load_all_agent_schemas()
    table_columns = _build_table_columns_map_from_schemas(schemas)
    for endpoint in endpoints:
        columns = table_columns.get(endpoint.table_oid or "")
        if not columns:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown table OID: {endpoint.table_oid}",
            )
        if endpoint.column not in columns:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown column '{endpoint.column}' for table {endpoint.table_oid}",
            )


def _sync_link_targets_on_create(request: LinkRequest) -> None:
    if state.snmp_agent is None:
        return
    if request.scope != "per-instance" or request.match != "shared-index":
        return

    source_ep = request.endpoints[0]
    source_table = source_ep.table_oid
    source_col = source_ep.column
    if not source_table:
        return

    source_instances = state.snmp_agent.table_instances.get(source_table, {})
    for instance_str, payload in source_instances.items():
        value = payload.get("column_values", {}).get(source_col)
        if value is None:
            continue
        for target_ep in request.endpoints[1:]:
            target_table = target_ep.table_oid
            target_col = target_ep.column
            if not target_table:
                continue
            if target_table not in state.snmp_agent.table_instances:
                continue
            if instance_str not in state.snmp_agent.table_instances[target_table]:
                continue
            state.snmp_agent.update_table_cell_values(
                target_table,
                instance_str,
                {target_col: value},
            )


@router.post("/links")
def create_or_update_link(request: LinkRequest) -> dict[str, object]:
    """Create or update a link (state-backed)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    if not request.endpoints or len(request.endpoints) < MIN_LINK_ENDPOINTS:
        raise HTTPException(status_code=400, detail="At least two endpoints are required")

    if request.scope == "per-instance":
        _validate_per_instance_link_endpoints(request.endpoints)

    link_manager = get_link_manager()
    link_id = request.id or f"link_{len(link_manager.export_links(include_schema=True)) + 1}"

    existing = {link["id"]: link for link in link_manager.export_links(include_schema=True)}
    if link_id in existing and existing[link_id].get("source") != "state":
        raise HTTPException(status_code=400, detail="Cannot overwrite schema link")

    link_manager.remove_link(link_id, source="state")

    link_manager.add_link(
        link_id,
        endpoints=[ValueLinkEndpoint(e.table_oid, e.column, e.is_base) for e in request.endpoints],
        scope=request.scope,
        match=request.match,
        source="state",
        description=request.description,
        create_missing=request.create_missing,
    )

    _sync_link_targets_on_create(request)

    state.snmp_agent.save_mib_state()

    return {"status": "ok", "id": link_id}


@router.delete("/links/{link_id}")
def delete_link(link_id: str) -> dict[str, object]:
    """Delete a link (state-backed only)."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    link_manager = get_link_manager()
    existing = {link["id"]: link for link in link_manager.export_links(include_schema=True)}
    if link_id not in existing:
        raise HTTPException(status_code=404, detail="Link not found")
    if existing[link_id].get("source") != "state":
        raise HTTPException(status_code=400, detail="Cannot delete schema link")

    if not link_manager.remove_link(link_id, source="state"):
        raise HTTPException(status_code=404, detail="Link not found")

    state.snmp_agent.save_mib_state()
    return {"status": "deleted", "id": link_id}
