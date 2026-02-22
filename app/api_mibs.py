"""MIB and OID metadata endpoints."""

from __future__ import annotations

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException

from app.api_state import state
from app.cli_load_model import load_all_schemas
from app.mib_dependency_resolver import MibDependencyResolver
from app.model_paths import AGENT_MODEL_DIR
from app.oid_utils import oid_tuple_to_str

router = APIRouter()

SCHEMA_DIR = str(AGENT_MODEL_DIR)


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
def get_mibs_dependencies_diagram() -> dict[str, object]:
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

    metadata_map: dict[str, dict[str, object]] = {}

    for mib_name, schema in schemas.items():
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and "oid" in obj_data:
                oid_tuple = obj_data["oid"]
                oid_str = oid_tuple_to_str(tuple(oid_tuple))

                metadata_map[oid_str] = {
                    "oid": oid_tuple,
                    "oid_str": oid_str,
                    "name": obj_name,
                    "type": obj_data.get("type", ""),
                    "access": obj_data.get("access", ""),
                    "mib": mib_name,
                    "initial": obj_data.get("initial"),
                    "enums": obj_data.get("enums"),
                    "dynamic_function": obj_data.get("dynamic_function"),
                }

    return {"count": len(metadata_map), "metadata": metadata_map}
