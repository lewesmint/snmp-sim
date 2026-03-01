"""MIB and OID metadata endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException

from app.api_state import state
from app.cli_load_model import load_all_schemas
from app.mib_dependency_resolver import MermaidDiagramResult, MibDependencyResolver
from app.model_paths import AGENT_MODEL_DIR
from app.oid_utils import oid_tuple_to_str

router = APIRouter()

SCHEMA_DIR = str(AGENT_MODEL_DIR)
_MIN_COLUMN_OID_LEN = 2  # Minimum OID length to be considered a table column


def _iter_schema_objects(
    schemas: Mapping[str, object],
) -> list[tuple[str, str, dict[str, object]]]:
    items: list[tuple[str, str, dict[str, object]]] = []
    for mib_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue
        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and "oid" in obj_data:
                items.append((mib_name, obj_name, obj_data))
    return items


def _build_table_oid_map(
    objects: list[tuple[str, str, dict[str, object]]],
) -> dict[tuple[int, ...], tuple[str, str]]:
    table_oid_map: dict[tuple[int, ...], tuple[str, str]] = {}
    for mib_name, obj_name, obj_data in objects:
        if obj_data.get("type", "") != "MibTable":
            continue
        oid_list = obj_data.get("oid", [])
        if isinstance(oid_list, list):
            table_oid_map[tuple(oid_list)] = (obj_name, mib_name)
    return table_oid_map


def _get_parent_info(
    obj_type: str,
    oid_tuple: tuple[int, ...],
    table_oid_map: dict[tuple[int, ...], tuple[str, str]],
) -> tuple[str | None, str | None]:
    if obj_type == "MibTableRow":
        parent_tuple = oid_tuple[:-1]
        if parent_tuple in table_oid_map:
            return oid_tuple_to_str(parent_tuple), "MibTable"

    if len(oid_tuple) >= _MIN_COLUMN_OID_LEN:
        potential_table = oid_tuple[:-2]
        if potential_table in table_oid_map:
            return oid_tuple_to_str(potential_table), "MibTable"

    return None, None


@router.get("/mibs")
def list_mibs() -> dict[str, object]:
    """List all MIBs implemented by the agent."""
    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        return {"count": 0, "mibs": []}

    schemas = load_all_schemas(schema_dir)
    mibs = sorted(schemas)
    return {"count": len(mibs), "mibs": mibs}


@router.get("/mibs-with-dependencies")
def list_mibs_with_dependencies() -> dict[str, object]:
    """List all MIBs with their dependency information."""
    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        return {
            "count": 0,
            "mibs": [],
            "configured_mibs": [],
            "transitive_dependencies": [],
            "tree": {},
            "summary": {
                "configured_count": 0,
                "transitive_count": 0,
                "total_count": 0,
            },
        }

    schemas = load_all_schemas(schema_dir)
    mibs = sorted(schemas)

    resolver = MibDependencyResolver()
    dependency_info = resolver.get_configured_mibs_with_deps(mibs)

    return {
        "count": len(mibs),
        "mibs": mibs,
        **dependency_info,
    }


@router.get("/mibs-dependencies-diagram")
def get_mibs_dependencies_diagram() -> MermaidDiagramResult:
    """Get a Mermaid diagram showing MIB dependencies."""
    schema_dir = SCHEMA_DIR
    if not Path(schema_dir).exists():
        return {
            "mermaid_code": "graph TD\n    Empty[No MIBs configured]",
            "configured_mibs": [],
            "transitive_dependencies": [],
            "summary": {
                "configured_count": 0,
                "transitive_count": 0,
                "total_count": 0,
            },
        }

    schemas = load_all_schemas(schema_dir)
    mibs = sorted(schemas)

    resolver = MibDependencyResolver()
    return resolver.generate_mermaid_diagram_json(mibs)


@router.get("/oids")
def list_oids() -> dict[str, object]:
    """List all OIDs implemented by the agent, including tables from schemas."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    oid_map = state.snmp_agent.get_all_oids()

    schema_dir = SCHEMA_DIR
    if Path(schema_dir).exists():
        schemas = load_all_schemas(schema_dir)

        for schema in schemas.values():
            objects = schema.get("objects", schema)
            if not isinstance(objects, dict):
                continue

            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict):
                    obj_type = obj_data.get("type", "")
                    oid_list = obj_data.get("oid", [])

                    if obj_type in ("MibTable", "MibTableRow") and oid_list:
                        oid_tuple = tuple(oid_list)
                        oid_map[obj_name] = oid_tuple

    return {"count": len(oid_map), "oids": oid_map}


@router.get("/oid-metadata")
async def get_oid_metadata() -> dict[str, object]:
    """Get full metadata for all OIDs from schema files."""
    if state.snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    schema_dir = SCHEMA_DIR
    if not await anyio.Path(schema_dir).exists():
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)
    schema_objects = _iter_schema_objects(schemas)
    metadata_map: dict[str, dict[str, object]] = {}
    table_oid_map = _build_table_oid_map(schema_objects)

    for mib_name, obj_name, obj_data in schema_objects:
        oid_value = obj_data.get("oid", [])
        if not isinstance(oid_value, list):
            continue
        oid_tuple = tuple(oid_value)
        oid_str = oid_tuple_to_str(oid_tuple)
        obj_type = str(obj_data.get("type", ""))
        parent_oid, parent_type = _get_parent_info(obj_type, oid_tuple, table_oid_map)

        metadata_map[oid_str] = {
            "oid": oid_tuple,
            "oid_str": oid_str,
            "name": obj_name,
            "type": obj_type,
            "access": obj_data.get("access", ""),
            "mib": mib_name,
            "parent_oid": parent_oid,
            "parent_type": parent_type,
            "initial": obj_data.get("initial"),
            "enums": obj_data.get("enums"),
            "dynamic_function": obj_data.get("dynamic_function"),
        }

    return {"count": len(metadata_map), "metadata": metadata_map}
