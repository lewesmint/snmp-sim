from fastapi import FastAPI, HTTPException
from app.app_logger import AppLogger
from pydantic import BaseModel
from typing import Optional, Any, Literal
from pathlib import Path
import json

from app.oid_utils import oid_str_to_tuple, oid_tuple_to_str
from app.trap_receiver import TrapReceiver
from app.value_links import get_link_manager, ValueLinkEndpoint

# Reference to the SNMPAgent instance will be set by main app
snmp_agent: Optional[Any] = None

# Global trap receiver instance
trap_receiver: Optional[TrapReceiver] = None

logger = AppLogger.get(__name__)
app = FastAPI()


class SysDescrUpdate(BaseModel):
    value: str


class LinkEndpoint(BaseModel):
    table_oid: Optional[str] = None
    column: str


class LinkRequest(BaseModel):
    id: Optional[str] = None
    scope: Literal["per-instance", "global"] = "per-instance"
    type: Literal["bidirectional"] = "bidirectional"
    match: Literal["shared-index"] = "shared-index"
    endpoints: list[LinkEndpoint]
    description: Optional[str] = None
    create_missing: bool = False


@app.get("/sysdescr")
def get_sysdescr() -> dict[str, Any]:
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    # sysDescr OID: (1,3,6,1,2,1,1,1,0)
    oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
    value = snmp_agent.get_scalar_value(oid)
    return {"oid": oid, "value": value}


@app.post("/sysdescr")
def set_sysdescr(update: SysDescrUpdate) -> dict[str, Any]:
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
    snmp_agent.set_scalar_value(oid, update.value)
    return {"status": "ok", "oid": oid, "new_value": update.value}


@app.get("/validate-types")
def validate_types() -> dict[str, Any]:
    """Validate the type registry JSON file."""
    from app.type_registry_validator import validate_type_registry_file

    is_valid, errors, type_count = validate_type_registry_file("data/types.json")

    if not is_valid:
        raise HTTPException(status_code=422, detail={"errors": errors, "valid": False})

    return {
        "valid": True,
        "type_count": type_count,
        "message": f"Type registry validated: {type_count} types found",
    }


@app.get("/type-info/{type_name}")
def get_type_info(type_name: str) -> dict[str, Any]:
    """Get information about a specific SNMP type."""
    from app.base_type_handler import BaseTypeHandler
    import json

    # Load type registry
    with open("data/types.json") as f:
        type_registry = json.load(f)

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


@app.get("/types")
def list_types() -> dict[str, Any]:
    """List all available SNMP types in the registry."""
    from app.base_type_handler import BaseTypeHandler
    import json

    # Load type registry
    with open("data/types.json") as f:
        type_registry = json.load(f)

    handler = BaseTypeHandler(type_registry=type_registry)
    all_types = list(handler.type_registry.keys())

    return {"count": len(all_types), "types": sorted(all_types)}


@app.get("/links")
def list_links() -> dict[str, Any]:
    """List all links (schema + state)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    link_manager = get_link_manager()
    return {"links": link_manager.export_links(include_schema=True)}


@app.post("/links")
def create_or_update_link(request: LinkRequest) -> dict[str, Any]:
    """Create or update a link (state-backed)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    if not request.endpoints or len(request.endpoints) < 2:
        raise HTTPException(status_code=400, detail="At least two endpoints are required")

    if request.scope == "per-instance":
        for endpoint in request.endpoints:
            if not endpoint.table_oid:
                raise HTTPException(
                    status_code=400,
                    detail="table_oid is required for per-instance links",
                )

    def _build_table_columns_map() -> dict[str, set[str]]:
        from app.cli_load_model import load_all_schemas
        import os

        table_columns: dict[str, set[str]] = {}
        schema_dir = "agent-model"
        if not os.path.exists(schema_dir):
            return table_columns

        schemas = load_all_schemas(schema_dir)
        for schema in schemas.values():
            objects = schema.get("objects", schema) if isinstance(schema, dict) else {}
            if not isinstance(objects, dict):
                continue

            # Map entry OID to table OID for this schema
            entry_to_table: dict[tuple[int, ...], str] = {}
            for obj_data in objects.values():
                if not isinstance(obj_data, dict):
                    continue
                if obj_data.get("type") == "MibTable":
                    table_oid_list = obj_data.get("oid", [])
                    if not table_oid_list:
                        continue
                    table_oid = ".".join(str(x) for x in table_oid_list)
                    entry_to_table[tuple(table_oid_list + [1])] = table_oid

            for obj_name, obj_data in objects.items():
                if not isinstance(obj_data, dict):
                    continue
                oid_list = obj_data.get("oid", [])
                if not isinstance(oid_list, list) or not oid_list:
                    continue
                oid_tuple = tuple(oid_list)
                # Column OID format: entry_oid + column_id
                for entry_oid, table_oid in entry_to_table.items():
                    if (
                        len(oid_tuple) == len(entry_oid) + 1
                        and oid_tuple[: len(entry_oid)] == entry_oid
                    ):
                        table_columns.setdefault(table_oid, set()).add(obj_name)
                        break

        return table_columns

    if request.scope == "per-instance":
        table_columns = _build_table_columns_map()
        for endpoint in request.endpoints:
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

    link_manager = get_link_manager()
    link_id = request.id or f"link_{len(link_manager.export_links(include_schema=True)) + 1}"

    # Prevent overwriting schema links
    existing = {l["id"]: l for l in link_manager.export_links(include_schema=True)}
    if link_id in existing and existing[link_id].get("source") != "state":
        raise HTTPException(status_code=400, detail="Cannot overwrite schema link")

    # Replace existing state link if needed
    link_manager.remove_link(link_id, source="state")

    link_manager.add_link(
        link_id,
        endpoints=[ValueLinkEndpoint(e.table_oid, e.column) for e in request.endpoints],
        scope=request.scope,
        match=request.match,
        source="state",
        description=request.description,
        create_missing=request.create_missing,
    )

    # Source-over-dest sync on creation: use first endpoint as source
    if request.scope == "per-instance" and request.match == "shared-index":
        source_ep = request.endpoints[0]
        source_table = source_ep.table_oid
        source_col = source_ep.column
        if source_table:
            source_instances = snmp_agent.table_instances.get(source_table, {})
            for instance_str, payload in source_instances.items():
                value = payload.get("column_values", {}).get(source_col)
                if value is None:
                    continue
                for target_ep in request.endpoints[1:]:
                    target_table = target_ep.table_oid
                    target_col = target_ep.column
                    if not target_table:
                        continue
                    if target_table not in snmp_agent.table_instances:
                        continue
                    if instance_str not in snmp_agent.table_instances[target_table]:
                        continue
                    snmp_agent._update_table_cell_values(
                        target_table,
                        instance_str,
                        {target_col: value},
                    )

    snmp_agent._save_mib_state()

    return {"status": "ok", "id": link_id}


@app.delete("/links/{link_id}")
def delete_link(link_id: str) -> dict[str, Any]:
    """Delete a link (state-backed only)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    link_manager = get_link_manager()
    existing = {l["id"]: l for l in link_manager.export_links(include_schema=True)}
    if link_id not in existing:
        raise HTTPException(status_code=404, detail="Link not found")
    if existing[link_id].get("source") != "state":
        raise HTTPException(status_code=400, detail="Cannot delete schema link")

    if not link_manager.remove_link(link_id, source="state"):
        raise HTTPException(status_code=404, detail="Link not found")

    snmp_agent._save_mib_state()
    return {"status": "deleted", "id": link_id}


@app.get("/ready")
def check_ready() -> dict[str, Any]:
    """Check if the SNMP agent is fully initialized and ready to serve requests."""
    if snmp_agent is None:
        raise HTTPException(status_code=503, detail="SNMP agent not initialized")

    # Check if mib_builder is initialized (indicates agent is fully ready)
    if not hasattr(snmp_agent, "mib_builder") or snmp_agent.mib_builder is None:
        raise HTTPException(status_code=503, detail="SNMP agent still initializing")

    # Try to get OID count to verify agent is fully operational
    try:
        oid_map = snmp_agent.get_all_oids()
        oid_count = len(oid_map)
    except Exception as e:
        logger.warning(f"Agent not ready: {e}")
        raise HTTPException(status_code=503, detail=f"SNMP agent not ready: {e}")

    return {"ready": True, "oid_count": oid_count}


@app.get("/mibs")
def list_mibs() -> dict[str, Any]:
    """List all MIBs implemented by the agent."""
    # Load all schema files from agent-model directory
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        return {"count": 0, "mibs": []}

    schemas = load_all_schemas(schema_dir)
    mibs = sorted(list(schemas.keys()))
    return {"count": len(mibs), "mibs": mibs}


@app.get("/mibs-with-dependencies")
def list_mibs_with_dependencies() -> dict[str, Any]:
    """List all MIBs with their dependency information."""
    from app.cli_load_model import load_all_schemas
    from app.mib_dependency_resolver import MibDependencyResolver
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
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
    mibs = sorted(list(schemas.keys()))

    # Resolve dependencies
    resolver = MibDependencyResolver()
    dependency_info = resolver.get_configured_mibs_with_deps(mibs)

    return {
        "count": len(mibs),
        "mibs": mibs,
        **dependency_info,
    }


@app.get("/mibs-dependencies-diagram")
def get_mibs_dependencies_diagram() -> dict[str, Any]:
    """Get a Mermaid diagram showing MIB dependencies."""
    from app.cli_load_model import load_all_schemas
    from app.mib_dependency_resolver import MibDependencyResolver
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
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
    mibs = sorted(list(schemas.keys()))

    # Generate Mermaid diagram
    resolver = MibDependencyResolver()
    diagram_data = resolver.generate_mermaid_diagram_json(mibs)

    return diagram_data


@app.get("/oids")
def list_oids() -> dict[str, Any]:
    """List all OIDs implemented by the agent, including tables from schemas."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Get OIDs registered with pysnmp
    oid_map = snmp_agent.get_all_oids()

    # Also include table OIDs from schema files
    # (tables are not registered with pysnmp to avoid index/registration errors,
    #  but they should still appear in the OID tree)
    import os
    from app.cli_load_model import load_all_schemas

    schema_dir = "agent-model"
    if os.path.exists(schema_dir):
        schemas = load_all_schemas(schema_dir)

        for mib_name, schema in schemas.items():
            # Handle both old flat and new {"objects": ..., "traps": ...} structure
            if "objects" in schema:
                objects = schema["objects"]
            else:
                objects = schema

            # Extract table OIDs
            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict):
                    obj_type = obj_data.get("type", "")
                    oid_list = obj_data.get("oid", [])

                    # Include MibTable objects (and their entries) in the OID list
                    if obj_type == "MibTable" and oid_list:
                        oid_tuple = tuple(oid_list)
                        # Use object name as key (matching pysnmp symbol names)
                        oid_map[obj_name] = oid_tuple
                    elif obj_type == "MibTableRow" and oid_list:
                        oid_tuple = tuple(oid_list)
                        # Use object name as key
                        oid_map[obj_name] = oid_tuple

    return {"count": len(oid_map), "oids": oid_map}


@app.get("/oid-metadata")
def get_oid_metadata() -> dict[str, Any]:
    """Get full metadata for all OIDs from schema files."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schema files from agent-model directory
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Build metadata map: OID string -> metadata
    metadata_map: dict[str, dict[str, Any]] = {}

    for mib_name, schema in schemas.items():
        # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
        if isinstance(schema, dict):
            if "objects" in schema:
                # New structure
                objects = schema["objects"]
            else:
                # Old flat structure
                objects = schema

            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict) and "oid" in obj_data:
                    # Convert OID list to dot-notation string
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


@app.get("/table-schema")
def get_table_schema(oid: str) -> dict[str, Any]:
    """Get schema information for a table OID."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        parts = oid_str_to_tuple(oid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid OID format")

    # Load all schemas
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Find the table in schemas
    table_info = None
    table_name = None
    mib_name = None
    entry_info = None
    entry_name = None

    # For debugging: collect candidate tables that look like the requested OID
    candidate_tables: list[tuple[str, tuple[int, ...]]] = []

    for mib, schema in schemas.items():
        # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
        if isinstance(schema, dict):
            if "objects" in schema:
                # New structure
                objects = schema["objects"]
            else:
                # Old flat structure
                objects = schema

            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict) and "oid" in obj_data:
                    obj_oid = obj_data["oid"]
                    obj_oid_t = tuple(obj_oid)
                    # Save candidate MibTable objects for debug logging
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

    # Debug: if we didn't find a table, log candidates for diagnostic purposes
    if table_info is None:
        logger.debug(
            "/table-schema: requested OID %s - candidate tables found: %s",
            parts,
            candidate_tables,
        )

    if not table_info:
        raise HTTPException(status_code=404, detail="Table not found")

    # Get entry OID (usually table_oid + .1)
    entry_oid = parts + (1,)

    # Get index columns from entry
    index_columns = entry_info.get("indexes", []) if entry_info else []

    # Get foreign key columns (if this table augments another)
    foreign_keys = entry_info.get("foreign_keys", []) if entry_info else []

    # Find columns
    columns = {}
    for mib, schema in schemas.items():
        # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
        if "objects" in schema:
            # New structure
            objects = schema["objects"]
        else:
            # Old flat structure
            objects = schema

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and "oid" in obj_data:
                # Normalize oid to tuple for reliable comparison
                obj_oid = obj_data["oid"]
                obj_oid_t = tuple(obj_oid)
                if len(obj_oid_t) > len(entry_oid) and obj_oid_t[: len(entry_oid)] == entry_oid:
                    # This is a column in the table
                    col_name = obj_name
                    is_index = col_name in index_columns
                    is_foreign_key = col_name in foreign_keys
                    columns[col_name] = {
                        "oid": list(obj_oid_t),
                        "type": obj_data.get("type", ""),
                        "access": obj_data.get("access", ""),
                        "is_index": is_index,
                        "is_foreign_key": is_foreign_key,
                        "default": obj_data.get("initial", ""),
                        "enums": obj_data.get("enums"),
                    }

    logger.info(f"/table-schema: columns found for {parts}: {list(columns.keys())}")

    # Get row instances from table_info
    rows_data = table_info.get("rows", []) if table_info else []
    instances = []
    for row_data in rows_data:
        if isinstance(row_data, dict):
            # Validate and fix index columns; ensure they don't have invalid
            # values (like 0 for InterfaceIndex).
            # Only fix if the column type has constraints that exclude 0
            for idx_col in index_columns:
                if idx_col in row_data and idx_col in columns:
                    idx_value = row_data[idx_col]
                    col_info = columns[idx_col]
                    col_type = col_info.get("type", "")

                    # Only fix 0 values for types that have constraints excluding 0
                    # (like InterfaceIndex which requires min value of 1)
                    should_fix_zero = False
                    if col_type in ("InterfaceIndex", "InterfaceIndexOrZero"):
                        # InterfaceIndex must be > 0
                        should_fix_zero = col_type == "InterfaceIndex"

                    if should_fix_zero and idx_value == 0 and isinstance(idx_value, int):
                        row_data[idx_col] = 1
                        logger.debug(
                            "Fixed invalid index value 0 for column %s (%s) in %s; changed to 1",
                            idx_col,
                            col_type,
                            table_name,
                        )

            # Build instance identifier from index columns
            instance_parts = []
            for idx_col in index_columns:
                if idx_col in row_data:
                    idx_value = row_data[idx_col]
                    instance_parts.append(str(idx_value))
            instances.append(".".join(instance_parts) if instance_parts else "1")

    # Add dynamically-created instances from the persisted state file
    oid_str = ".".join(str(x) for x in parts)
    if snmp_agent and oid_str in snmp_agent.table_instances:
        for instance_key in snmp_agent.table_instances[oid_str].keys():
            if instance_key not in instances:
                instances.append(instance_key)

    # Remove deleted instances
    if snmp_agent:
        instances = [
            inst for inst in instances if f"{oid_str}.{inst}" not in snmp_agent.deleted_instances
        ]

    # For no-index tables, add virtual __index__ columns to support multi-part indexes
    if not index_columns:
        # Analyze instances to determine how many __index__ parts we need
        max_parts = 1
        for inst in instances:
            parts_count = len(str(inst).split("."))
            max_parts = max(max_parts, parts_count)

        # Add virtual __index__ columns
        virtual_index_cols = []
        for i in range(1, max_parts + 1):
            col_name = "__index__" if i == 1 else f"__index_{i}__"
            virtual_index_cols.append(col_name)
            columns[col_name] = {
                "oid": [],  # Virtual column has no real OID
                "type": "Integer32",
                "access": "read-write",  # Allow editing
                "is_index": True,
                "default": "1" if i == 1 else "",
                "enums": None,
            }

        index_columns = virtual_index_cols

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


@app.get("/value")
def get_oid_value(oid: str) -> dict[str, Any]:
    """Get the value for a specific OID string (dot separated)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = oid_str_to_tuple(oid)
    except ValueError:
        logger.error(f"Invalid OID format requested: {oid}")
        raise HTTPException(status_code=400, detail="Invalid OID format")

    # Try to get as scalar first
    try:
        value = snmp_agent.get_scalar_value(parts)
    except ValueError:
        # Scalar not found - try as table cell
        value = _try_get_table_cell_value(oid, parts)
        if value is not None:
            return {"oid": parts, "value": value}
        # Not a scalar or table cell
        logger.warning(f"OID not found (not scalar or table cell): {parts}")
        raise HTTPException(
            status_code=404, detail=f"OID not settable: Scalar OID {parts} not found"
        )
    except Exception:
        # Unexpected errors should be logged with traceback and return 500
        logger.exception(f"Unexpected error fetching value for OID {parts}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Ensure returned value is JSON-serializable; fall back to string representation
    def _make_jsonable(v: Any) -> Any:
        # Primitive JSON-friendly types
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (list, tuple)):
            return [_make_jsonable(x) for x in v]
        try:
            return str(v)
        except Exception:
            return repr(v)

    serializable = _make_jsonable(value)
    logger.info(f"Fetched value for OID {parts}: {serializable}")
    return {"oid": parts, "value": serializable}


def _try_get_table_cell_value(oid: str, parts: tuple[int, ...]) -> Any | None:
    """Try to get value as a table cell from table_instances.

    Args:
        oid: OID as string
        parts: OID as tuple

    Returns:
        The cell value if found, None otherwise
    """
    if snmp_agent is None:
        return None

    # Try to parse as table cell OID: table.entry.column.instance
    # Example: 1.3.6.1.4.1.99998.1.3.1.3.192.168.1.1.60
    #          table=1.3.6.1.4.1.99998.1.3, entry=1, column=3, instance=192.168.1.1.60

    # We need to find the table by trying progressively shorter prefixes
    # and checking if they exist in table_instances
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        return None

    schemas = load_all_schemas(schema_dir)

    # First, identify which table this OID belongs to by checking schemas
    # Format: table_parts + (1,) + (column_num,) + instance_parts
    table_oid_str = None
    table_parts = None
    column_num = None
    instance_str = None
    column_name = None

    for mib, schema in schemas.items():
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        for obj_name, obj_data in objects.items():
            if not isinstance(obj_data, dict) or obj_data.get("type") != "MibTable":
                continue
            candidate_table_parts = tuple(obj_data.get("oid", []))
            entry_oid = candidate_table_parts + (1,)

            # Check if OID starts with table_oid + .1 (entry)
            if (
                len(parts) > len(candidate_table_parts) + 1
                and parts[: len(candidate_table_parts)] == candidate_table_parts
                and parts[len(candidate_table_parts)] == 1
            ):
                # This could be a cell in this table
                table_parts = candidate_table_parts
                table_oid_str = ".".join(str(x) for x in table_parts)
                column_num = parts[len(table_parts) + 1]
                instance_parts = parts[len(table_parts) + 2 :]
                instance_str = ".".join(str(x) for x in instance_parts) if instance_parts else "1"

                # Look up column name
                for col_name, col_data in objects.items():
                    if isinstance(col_data, dict) and "oid" in col_data:
                        col_oid_t = tuple(col_data["oid"])
                        if col_oid_t == entry_oid + (column_num,):
                            column_name = col_name
                            break
                break
        if table_oid_str:
            break

    if not table_oid_str or not column_name or table_parts is None:
        return None

    # Now check table_instances for this specific table
    if table_oid_str in snmp_agent.table_instances:
        instances = snmp_agent.table_instances[table_oid_str]
        if instance_str in instances:
            column_values = instances[instance_str].get("column_values", {})
            if column_name in column_values:
                value = column_values[column_name]
                logger.info(
                    f"Fetched table cell value from table_instances for OID {parts}: {value}"
                )
                return value

    # Fall back to schema rows for static instances
    for mib, schema in schemas.items():
        objects = schema.get("objects", schema)
        if not isinstance(objects, dict):
            continue

        # Find the table and entry objects
        table_obj = None
        entry_obj = None
        entry_oid = table_parts + (1,)

        for obj_name, obj_data in objects.items():
            if not isinstance(obj_data, dict):
                continue
            if obj_data.get("type") == "MibTable":
                obj_oid = tuple(obj_data.get("oid", []))
                if obj_oid == table_parts:
                    table_obj = obj_data
            elif obj_data.get("type") == "MibTableRow":
                obj_oid = tuple(obj_data.get("oid", []))
                if obj_oid == entry_oid:
                    entry_obj = obj_data

        if not table_obj or not entry_obj:
            continue

        index_columns = entry_obj.get("indexes", [])
        if not isinstance(index_columns, list):
            index_columns = []

        rows = table_obj.get("rows", [])
        if not isinstance(rows, list):
            continue

        # Build instance string from OID for matching
        instance_str_from_oid = instance_str if instance_str else "1"

        for row in rows:
            if not isinstance(row, dict):
                continue

            # For tables with no index columns (implied instance)
            if not index_columns:
                if instance_str_from_oid != "1":
                    continue
                if column_name in row:
                    value = row[column_name]
                    logger.info(f"Fetched table cell value from schema for OID {parts}: {value}")
                    return value
                continue

            # For tables with explicit index columns
            row_instance_parts: list[str] = []
            for idx_col in index_columns:
                if idx_col in row:
                    row_instance_parts.append(str(row[idx_col]))
            row_instance_str = ".".join(row_instance_parts) if row_instance_parts else "1"
            if row_instance_str != instance_str_from_oid:
                continue
            if column_name in row:
                value = row[column_name]
                logger.info(f"Fetched table cell value from schema for OID {parts}: {value}")
                return value

    return None


@app.get("/values/bulk")
def get_all_values() -> dict[str, Any]:
    """Get all OID values in bulk for efficient loading."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Helper to make values JSON-serializable
    def _make_jsonable(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (list, tuple)):
            return [_make_jsonable(x) for x in v]
        try:
            return str(v)
        except Exception:
            return repr(v)

    # Get all registered OIDs
    all_oids = snmp_agent.get_all_oids()
    values = {}

    # Fetch value for each OID
    for oid_str in all_oids.keys():
        try:
            parts = oid_str_to_tuple(oid_str)
            value = snmp_agent.get_scalar_value(parts)
            values[oid_str] = _make_jsonable(value)
        except Exception:
            # Skip OIDs that can't be fetched (e.g., tables, containers)
            pass

    logger.info(f"Bulk fetched {len(values)} OID values")
    return {"count": len(values), "values": values}


class OIDValueUpdate(BaseModel):
    oid: str
    value: str


@app.post("/value")
def set_oid_value(update: OIDValueUpdate) -> dict[str, Any]:
    """Set the value for a specific OID string (dot separated)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = tuple(int(x) for x in update.oid.split(".")) if update.oid else ()
    except ValueError as e:
        logger.error(f"Invalid OID format requested: {update.oid} - {e}")
        raise HTTPException(status_code=400, detail="Invalid OID format")

    try:
        snmp_agent.set_scalar_value(parts, update.value)
        logger.info(f"Set value for OID {parts} to: {update.value}")
        return {"status": "ok", "oid": parts, "new_value": update.value}
    except ValueError as e:
        # Expected: scalar not found or not writable for this OID
        logger.warning(f"Cannot set scalar OID: {parts} - {e}")
        raise HTTPException(status_code=404, detail=f"OID not settable: {e}")
    except Exception:
        # Unexpected errors should be logged with traceback and return 500
        logger.exception(f"Unexpected error setting value for OID {parts}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/tree/bulk")
def get_tree_bulk_data() -> dict[str, Any]:
    """Get complete tree data including all table instances for efficient GUI loading."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        return {"tables": {}}

    schemas = load_all_schemas(schema_dir)

    # Get all table instances with their full data
    tables_data: dict[str, Any] = {}

    # Build a map of parent column sources for tables with index_from
    # This helps identify which table rows to use for instances
    index_source_map: dict[str, dict[str, Any]] = {}  # table_oid -> {source_mib, source_column}

    # First pass: identify tables and their index sources
    for mib_name, schema in schemas.items():
        if "objects" in schema:
            objects = schema["objects"]
        else:
            objects = schema

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and obj_data.get("type") == "MibTableRow":
                # Check if this entry has index_from
                index_from = obj_data.get("index_from", [])
                if index_from and isinstance(index_from, list) and len(index_from) > 0:
                    # Store the source info for this table row
                    table_oid_parts = obj_data.get("oid", [])
                    # Table OID is entry OID minus the .1
                    if table_oid_parts and len(table_oid_parts) > 0 and table_oid_parts[-1] == 1:
                        table_oid = ".".join(str(x) for x in table_oid_parts[:-1])
                        index_source_map[table_oid] = index_from[0]  # Store first index source

    # Second pass: process all tables
    for mib_name, schema in schemas.items():
        if "objects" in schema:
            objects = schema["objects"]
        else:
            objects = schema

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                table_oid = ".".join(str(x) for x in obj_data["oid"])

                # Find the entry object
                entry_name = None
                entry_obj = {}
                table_oid_parts = obj_data["oid"]
                expected_entry_oid = list(table_oid_parts) + [1]

                for other_name, other_data in objects.items():
                    if isinstance(other_data, dict) and other_data.get("type") == "MibTableRow":
                        if list(other_data.get("oid", [])) == expected_entry_oid:
                            entry_name = other_name
                            entry_obj = other_data
                            break

                index_columns = entry_obj.get("indexes", [])

                # Get instances for this table
                instances: list[str] = []
                try:
                    # Check if this table has entries that reference another table for indexes
                    if table_oid in index_source_map:
                        # This table's instances come from a parent table
                        source_info = index_source_map[table_oid]
                        source_mib = source_info.get("mib", "")
                        source_column = source_info.get("column", "")

                        # Debug log for augmented tables
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
                            if "objects" in source_schema:
                                source_objects = source_schema["objects"]
                            else:
                                source_objects = source_schema

                            # First find which table contains the source column
                            # The source_column is a column object; find its parent
                            # entry's parent table.
                            parent_table_obj = None
                            if source_column in source_objects:
                                col_data = source_objects[source_column]
                                if isinstance(col_data, dict):
                                    col_oid = tuple(col_data.get("oid", []))
                                    # The parent entry OID is all but the last segment
                                    if len(col_oid) > 1:
                                        entry_oid = col_oid[:-1]
                                        # Find the table OID (all but the last entry "1")
                                        if len(entry_oid) > 0 and entry_oid[-1] == 1:
                                            table_oid_parts = entry_oid[:-1]
                                            # Now find the table with this OID
                                            for (
                                                tbl_name,
                                                tbl_data,
                                            ) in source_objects.items():
                                                if (
                                                    isinstance(tbl_data, dict)
                                                    and tbl_data.get("type") == "MibTable"
                                                    and list(tbl_data.get("oid", []))
                                                    == list(table_oid_parts)
                                                ):
                                                    parent_table_obj = tbl_data
                                                    break

                            # Extract instances from the parent table only
                            if parent_table_obj:
                                source_rows = parent_table_obj.get("rows", [])
                                source_entry_obj = {}

                                # Find the entry for the parent table
                                source_entry_oid = list(parent_table_obj.get("oid", [])) + [1]
                                for (
                                    source_entry_name,
                                    source_entry_data,
                                ) in source_objects.items():
                                    if (
                                        isinstance(source_entry_data, dict)
                                        and source_entry_data.get("type") == "MibTableRow"
                                        and list(source_entry_data.get("oid", []))
                                        == source_entry_oid
                                    ):
                                        source_entry_obj = source_entry_data
                                        break

                                source_indexes = source_entry_obj.get("indexes", [])

                                # Extract instances from source table's rows
                                if isinstance(source_rows, list):
                                    for row in source_rows:
                                        if isinstance(row, dict):
                                            # Build instance string from source table's indexes
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

                        # Debug log after fetching parent instances
                        if table_oid.endswith(".31.1.1"):
                            logger.debug(
                                f"After fetching parent instances for {obj_name}: {instances}"
                            )
                    else:
                        # Get instances from actual rows in this table
                        rows = obj_data.get("rows", [])
                        if isinstance(rows, list):
                            for row in rows:
                                if isinstance(row, dict):
                                    # Build instance string from index columns
                                    parts = []
                                    for idx_col in index_columns:
                                        if idx_col in row:
                                            val = row[idx_col]
                                            # Handle IpAddress expansion
                                            col_meta = objects.get(idx_col, {})
                                            if col_meta.get("type") == "IpAddress" and isinstance(
                                                val, str
                                            ):
                                                parts.extend(val.split("."))
                                            else:
                                                parts.append(str(val))
                                    if parts:
                                        instances.append(".".join(parts))

                    # Also add any dynamic instances from snmp_agent.table_instances
                    # BUT: Skip this for augmented tables (those with
                    # index_from) because they should only use parent table
                    # instances.
                    # Check both entry_obj and index_source_map to detect augmented tables
                    has_index_from = isinstance(entry_obj, dict) and bool(
                        entry_obj.get("index_from")
                    )
                    is_in_index_source = table_oid in index_source_map
                    is_augmented = has_index_from or is_in_index_source

                    if not is_augmented and table_oid in snmp_agent.table_instances:
                        for inst_key in snmp_agent.table_instances[table_oid].keys():
                            if inst_key not in instances:
                                instances.append(inst_key)
                except Exception as e:
                    logger.warning(f"Error getting instances for table {obj_name}: {e}")

                if instances:
                    tables_data[table_oid] = {
                        "table_name": obj_name,
                        "entry_name": entry_name,
                        "index_columns": index_columns,
                        "instances": instances,
                    }

    logger.info(f"Bulk tree data: {len(tables_data)} tables with instances")

    return {"tables": tables_data}


@app.get("/traps")
def list_traps() -> dict[str, Any]:
    """List all available SNMP traps/notifications from all loaded MIBs."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schema files
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Collect traps from all schemas
    all_traps: dict[str, Any] = {}

    for mib_name, schema in schemas.items():
        # Check if schema has new structure with "objects" and "traps" keys
        if isinstance(schema, dict):
            if "traps" in schema and isinstance(schema["traps"], dict):
                # New structure
                for trap_name, trap_data in schema["traps"].items():
                    trap_info = {
                        **trap_data,
                        "mib": mib_name,
                        "full_name": f"{mib_name}::{trap_name}",
                    }
                    all_traps[trap_name] = trap_info

    return {"count": len(all_traps), "traps": all_traps}


def _load_trap_overrides_from_data() -> dict[str, dict[str, Any]]:
    """Load trap overrides from data/trap_overrides.json if present."""
    overrides_path = Path("data/trap_overrides.json")
    try:
        if overrides_path.exists():
            import json

            with open(overrides_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning(f"Failed to load trap overrides from data: {exc}")
    return {}


def _save_trap_overrides_to_data(overrides: dict[str, dict[str, Any]]) -> None:
    """Persist trap overrides to data/trap_overrides.json."""
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    overrides_path = data_dir / "trap_overrides.json"
    try:
        pruned_overrides: dict[str, dict[str, Any]] = {}
        for name, data in overrides.items():
            cleaned: dict[str, Any] = {}
            for oid_name, entry in data.items():
                if isinstance(entry, dict):
                    enabled = bool(entry.get("enabled"))
                    value = str(entry.get("value", ""))
                    if enabled or value:
                        cleaned[oid_name] = {"value": value, "enabled": enabled}
                else:
                    if entry not in (None, ""):
                        cleaned[oid_name] = str(entry)
            if cleaned:
                pruned_overrides[name] = cleaned

        with open(overrides_path, "w", encoding="utf-8") as f:
            json.dump(pruned_overrides, f, indent=2)
    except Exception as exc:
        logger.warning(f"Failed to save trap overrides to data: {exc}")


# In-memory storage for trap overrides (hydrated from data)
trap_overrides: dict[str, dict[str, Any]] = _load_trap_overrides_from_data()


@app.get("/trap-overrides/{trap_name}")
def get_trap_overrides(trap_name: str) -> dict[str, Any]:
    """Get stored overrides for a specific trap."""
    return {"trap_name": trap_name, "overrides": trap_overrides.get(trap_name, {})}


@app.post("/trap-overrides/{trap_name}")
def set_trap_overrides(trap_name: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Set overrides for a specific trap."""
    trap_overrides[trap_name] = overrides
    _save_trap_overrides_to_data(trap_overrides)
    return {"status": "ok", "trap_name": trap_name, "overrides": overrides}


@app.get("/trap-varbinds/{trap_name}")
def get_trap_varbinds(trap_name: str) -> dict[str, Any]:
    """Get detailed varbind metadata for a specific trap.

    Returns information about each varbind including:
    - Whether it's an index column
    - The parent table (if applicable)
    - Available instances for multi-index tables
    - Type information
    """
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schema files
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Find the trap
    trap_info = None
    mib_name = None

    for candidate_mib_name, schema in schemas.items():
        if isinstance(schema, dict) and "traps" in schema:
            if trap_name in schema["traps"]:
                trap_info = schema["traps"][trap_name]
                mib_name = candidate_mib_name
                break

    if not trap_info or mib_name is None:
        raise HTTPException(status_code=404, detail=f"Trap '{trap_name}' not found")

    # Get varbind objects
    varbind_objects = trap_info.get("objects", [])

    # Build detailed varbind metadata
    varbinds_metadata = []
    parent_table_oid = None
    parent_table_name = None
    index_columns = []
    instances = []
    columns_meta = {}

    for varbind_obj in varbind_objects:
        obj_mib = varbind_obj.get("mib", "")
        obj_name = varbind_obj.get("name", "")

        # Find the object in the schema
        obj_schema = schemas.get(obj_mib, {})
        if isinstance(obj_schema, dict) and "objects" in obj_schema:
            obj_data = obj_schema["objects"].get(obj_name, {})
        else:
            obj_data = obj_schema.get(obj_name, {})

        if not obj_data:
            # Object not found in schema
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

        # Check if this is a table column by looking at parent OID
        is_index = False
        parent_table = None

        if len(obj_oid) > 2:
            # Get parent OID (table row)
            parent_oid = tuple(obj_oid[:-1])

            # Find the parent in the schema
            for check_name, check_data in obj_schema.get("objects", {}).items():
                if isinstance(check_data, dict) and tuple(check_data.get("oid", [])) == parent_oid:
                    # Found the parent (table row)
                    if check_data.get("type") == "MibTableRow":
                        # This is a table column
                        # Get the table (parent of row)
                        if len(parent_oid) > 0:
                            table_oid = tuple(parent_oid[:-1])

                            # Find the table and get index columns from the row entry
                            for table_name, table_data in obj_schema.get("objects", {}).items():
                                if (
                                    isinstance(table_data, dict)
                                    and tuple(table_data.get("oid", [])) == table_oid
                                ):
                                    if table_data.get("type") == "MibTable":
                                        # Get index columns from the table row
                                        # entry (not the table itself)
                                        table_index_cols = check_data.get("indexes", [])
                                        parent_table = {
                                            "name": table_name,
                                            "oid": list(table_oid),
                                            "index_columns": table_index_cols,
                                        }

                                        # Check if this column is an index
                                        if obj_name in table_index_cols:
                                            is_index = True

                                        # Store table info for later (only once)
                                        if parent_table_oid is None:
                                            parent_table_oid = list(table_oid)
                                            parent_table_name = table_name
                                            index_columns = table_index_cols
                                            instances = table_data.get("instances", [])

                                            # Get all columns metadata from the table
                                            for col_name, col_data in obj_schema.get(
                                                "objects", {}
                                            ).items():
                                                if isinstance(col_data, dict):
                                                    col_oid = tuple(col_data.get("oid", []))
                                                    # Check if this column belongs to this table
                                                    if (
                                                        len(col_oid) > len(parent_oid)
                                                        and col_oid[: len(parent_oid)] == parent_oid
                                                    ):
                                                        columns_meta[col_name] = {
                                                            "oid": list(col_oid),
                                                            "type": col_data.get("type", "Unknown"),
                                                            "access": col_data.get(
                                                                "access", "unknown"
                                                            ),
                                                        }

                                        break
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


@app.delete("/trap-overrides/{trap_name}")
def clear_trap_overrides(trap_name: str) -> dict[str, Any]:
    """Clear all overrides for a specific trap."""
    if trap_name in trap_overrides:
        del trap_overrides[trap_name]
        _save_trap_overrides_to_data(trap_overrides)
    return {"status": "ok", "trap_name": trap_name}


# ============================================================================
# Trap Destinations Endpoints
# ============================================================================


class TrapDestination(BaseModel):
    """Model for a trap destination."""

    host: str
    port: int


@app.get("/trap-destinations")
def get_trap_destinations() -> dict[str, Any]:
    """Get all configured trap destinations from app config."""
    from app.app_config import AppConfig

    try:
        config = AppConfig()
        destinations = config.get("trap_destinations", [])

        # Convert to list of dicts if needed
        dest_list = []
        for dest in destinations:
            if isinstance(dest, dict):
                dest_list.append(
                    {
                        "host": dest.get("host", "localhost"),
                        "port": dest.get("port", 162),
                    }
                )
            else:
                # Handle legacy format if any
                dest_list.append({"host": "localhost", "port": 162})

        return {"status": "ok", "destinations": dest_list}
    except Exception as e:
        logger.exception("Failed to get trap destinations")
        raise HTTPException(status_code=500, detail=f"Failed to get trap destinations: {str(e)}")


@app.post("/trap-destinations")
def add_trap_destination(destination: TrapDestination) -> dict[str, Any]:
    """Add a new trap destination to app config."""
    from app.app_config import AppConfig
    import yaml

    try:
        config = AppConfig()
        config_file = Path("data/agent_config.yaml")

        # Read current config
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        # Get current destinations
        destinations = config_data.get("trap_destinations", [])

        # Add new destination
        new_dest = {"host": destination.host, "port": destination.port}
        if new_dest not in destinations:
            destinations.append(new_dest)
            config_data["trap_destinations"] = destinations

            # Write back to file
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            # Reload config
            config.reload()

            return {
                "status": "ok",
                "destination": new_dest,
                "destinations": destinations,
            }
        else:
            return {
                "status": "ok",
                "message": "Destination already exists",
                "destinations": destinations,
            }
    except Exception as e:
        logger.exception("Failed to add trap destination")
        raise HTTPException(status_code=500, detail=f"Failed to add trap destination: {str(e)}")


@app.delete("/trap-destinations")
def remove_trap_destination(destination: TrapDestination) -> dict[str, Any]:
    """Remove a trap destination from app config."""
    from app.app_config import AppConfig
    import yaml

    try:
        config = AppConfig()
        config_file = Path("data/agent_config.yaml")

        # Read current config
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        # Get current destinations
        destinations = config_data.get("trap_destinations", [])

        # Remove destination
        dest_to_remove = {"host": destination.host, "port": destination.port}
        if dest_to_remove in destinations:
            destinations.remove(dest_to_remove)

            # Ensure at least one destination remains
            if not destinations:
                destinations = [{"host": "localhost", "port": 162}]

            config_data["trap_destinations"] = destinations

            # Write back to file
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            # Reload config
            config.reload()

            return {
                "status": "ok",
                "removed": dest_to_remove,
                "destinations": destinations,
            }
        else:
            return {
                "status": "ok",
                "message": "Destination not found",
                "destinations": destinations,
            }
    except Exception as e:
        logger.exception("Failed to remove trap destination")
        raise HTTPException(status_code=500, detail=f"Failed to remove trap destination: {str(e)}")


class TrapSendRequest(BaseModel):
    trap_name: str
    trap_type: Literal["trap", "inform"] = "trap"
    dest_host: Optional[str] = "localhost"
    dest_port: Optional[int] = 162
    community: Optional[str] = "public"


@app.post("/send-trap")
async def send_trap(request: TrapSendRequest) -> dict[str, Any]:
    """Send an SNMP trap/notification.

    Uses PySNMP NotificationType, so mandatory SNMPv2 varbinds (sysUpTime.0 and
    snmpTrapOID.0) are generated automatically.
    """
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schemas to find which MIB defines this trap
    from app.cli_load_model import load_all_schemas
    import os

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

    schema_dir = "agent-model"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    trap_info = None
    mib_name = None

    for candidate_mib_name, schema in schemas.items():
        if isinstance(schema, dict) and "traps" in schema:
            if request.trap_name in schema["traps"]:
                trap_info = schema["traps"][request.trap_name]
                mib_name = candidate_mib_name
                break

    if not trap_info or mib_name is None:
        raise HTTPException(status_code=404, detail=f"Trap '{request.trap_name}' not found")

    # Use the agent's SnmpEngine so traps have the correct uptime
    snmp_engine = getattr(snmp_agent, "snmpEngine", None)
    if snmp_engine is None:
        raise HTTPException(status_code=500, detail="SNMP agent engine not initialized")

    mib_builder = snmp_engine.get_mib_builder()
    mib_view = view.MibViewController(mib_builder)

    try:
        mib_builder.load_modules(mib_name)
    except MibNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"MIB module not found: {mib_name}. {exc}")

    try:
        notif = NotificationType(ObjectIdentity(mib_name, request.trap_name)).resolve_with_mib(
            mib_view
        )
    except (SmiError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to resolve notification {mib_name}::{request.trap_name}. {exc}",
        )

    # No need to manually set sysUpTime - the agent's engine already has it via readGet wrapper

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
    except Exception as exc:
        logger.exception("Failed to send trap")
        raise HTTPException(status_code=500, detail=f"Failed to send trap: {exc}")

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


class CreateTableRowRequest(BaseModel):
    """Request to create a new table row."""

    table_oid: str  # e.g., "1.3.6.1.2.1.2.2" for ifTable
    index_values: dict[str, Any]  # e.g., {"ifIndex": "2"}
    column_values: dict[str, Any] = {}  # e.g., {"ifName": "eth0", "ifType": "6"}


class ConfigData(BaseModel):
    host: str
    port: str
    trap_destinations: list[dict[str, Any]]
    selected_trap: str
    trap_index: str
    trap_overrides: dict[str, Any]


@app.post("/table-row")
def create_table_row(request: CreateTableRowRequest) -> dict[str, Any]:
    """Create a new instance in a table."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        # Load schemas for default row lookup
        from app.cli_load_model import load_all_schemas

        schema_dir = "agent-model"
        schemas = load_all_schemas(schema_dir)

        logger.info(f"Creating table instance for {request.table_oid}")
        logger.info(f"  index_values: {request.index_values} (type: {type(request.index_values)})")
        logger.info(f"  column_values: {request.column_values}")

        # Log each column value's type
        if request.column_values:
            for col_name, col_val in request.column_values.items():
                logger.info(f"    {col_name}: {col_val} (type: {type(col_val).__name__})")

        # Parse table OID
        table_parts = (
            tuple(int(x) for x in request.table_oid.split(".")) if request.table_oid else ()
        )
        entry_oid = table_parts + (1,)

        # Fetch table schema to get index column types
        try:
            import httpx

            schema_response = httpx.get(
                "http://127.0.0.1:8800/table-schema",
                params={"oid": request.table_oid},
                timeout=5,
            )
            schema_response.raise_for_status()
            table_schema = schema_response.json()
            columns = table_schema.get("columns", {})
            index_columns = table_schema.get("index_columns", [])
        except Exception as e:
            logger.warning(f"Could not fetch table schema: {e}")
            # Fall back to simple integer conversion
            columns = {}
            index_columns = list(request.index_values.keys())

        def _get_default_row(table_oid: str) -> dict[str, Any]:
            """Get default row values from schema rows, if available."""
            parts = tuple(int(x) for x in table_oid.split(".")) if table_oid else ()
            for mib, schema in schemas.items():
                objects = schema.get("objects", schema) if isinstance(schema, dict) else {}
                for obj_data in objects.values():
                    if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                        obj_oid = tuple(obj_data.get("oid", []))
                        if obj_oid == parts:
                            rows = obj_data.get("rows", [])
                            if rows and isinstance(rows[0], dict):
                                return rows[0]
            return {}

        def _should_use_default(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str) and val.strip().lower() == "unset":
                return True
            return False

        def _extract_index_str(values: dict[str, Any]) -> str:
            """Extract instance string from index values, supporting multi-part __index__."""
            # Handle multi-part __index__ (__index__, __index_2__, __index_3__, etc.)
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

            # Legacy fallbacks
            if "index" in values:
                return str(values["index"])
            if "instance" in values:
                return str(values["instance"])
            if not values:
                return "1"
            return ".".join(str(v) for v in values.values())

        if not index_columns:
            index_str = _extract_index_str(request.index_values)
            # Parse multi-part index string into separate __index__ values
            # E.g., "1.2.3" → {"__index__": "1", "__index_2__": "2", "__index_3__": "3"}
            index_parts = index_str.split(".")
            parsed_index_values = {}
            for i, part in enumerate(index_parts, 1):
                key = "__index__" if i == 1 else f"__index_{i}__"
                parsed_index_values[key] = part

            # Merge defaults for missing or "unset" columns
            default_row = _get_default_row(request.table_oid)
            merged_values_simple: dict[str, Any] = {}
            incoming_values = request.column_values or {}
            for col_name, col_meta in columns.items():
                if col_name in parsed_index_values:
                    continue
                if col_name in incoming_values and not _should_use_default(
                    incoming_values[col_name]
                ):
                    merged_values_simple[col_name] = incoming_values[col_name]
                    continue
                if col_name in default_row:
                    merged_values_simple[col_name] = default_row[col_name]
                    continue
                default_val = col_meta.get("default", "")
                if default_val != "":
                    merged_values_simple[col_name] = default_val

            instance_oid = snmp_agent.add_table_instance(
                table_oid=request.table_oid,
                index_values=parsed_index_values,
                column_values=merged_values_simple,
            )
            logger.info(f"Successfully created table instance: {instance_oid}")
            return {
                "status": "ok",
                "table_oid": request.table_oid,
                "instance_index": index_str,
                "instance_oid": instance_oid,
                "columns_created": [str(col) for col in merged_values_simple.keys()]
                if merged_values_simple
                else [],
            }

        # Helper function to convert index value based on column type
        def convert_index_value(col_name: str, value: str | int) -> int | tuple[int, ...] | str:
            """Convert index value to appropriate format based on column type."""
            if col_name not in columns:
                # Try to parse as int, otherwise keep as string
                if isinstance(value, int):
                    return value
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return str(value)

            col_info = columns[col_name]
            col_type = col_info.get("type", "")

            # Convert based on type
            if col_type == "IpAddress" or "IpAddress" in col_type:
                # Convert "192.168.1.1" to (192, 168, 1, 1)
                if isinstance(value, str):
                    try:
                        parts = tuple(int(p) for p in value.split("."))
                        return parts
                    except (ValueError, AttributeError):
                        return str(value)
                return value
            elif "Integer" in col_type or col_type in (
                "Integer32",
                "Integer64",
                "Unsigned32",
                "Gauge32",
                "Counter32",
                "Counter64",
            ):
                # Integer types
                if isinstance(value, int):
                    return value
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return str(value)
            else:
                # String or unknown types - keep as-is
                return str(value) if not isinstance(value, str) else value

        # Convert all index values
        converted_indices = {}
        for col_name in index_columns:
            if col_name in request.index_values:
                converted_indices[col_name] = convert_index_value(
                    col_name, request.index_values[col_name]
                )

        # Build the instance OID from ALL converted index values (not just the first)
        # OID format: entry_oid + (1,) + <first_index_components> + <second_index_components> + ...
        index_oid = entry_oid + (1,)  # Start with column index 1
        instance_index_str = ""

        # Append each index value to the OID in order
        for idx_col_name in index_columns:
            if idx_col_name not in request.index_values:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required index column: {idx_col_name}",
                )

            converted_val = converted_indices.get(idx_col_name)
            if converted_val is None:
                converted_val = convert_index_value(
                    idx_col_name, request.index_values[idx_col_name]
                )

            if isinstance(converted_val, tuple):
                # For IpAddress and similar tuple types, expand the tuple into the OID
                index_oid = index_oid + converted_val
                instance_index_str += "." + ".".join(str(x) for x in converted_val)
            else:
                # For single values
                int_val = (
                    int(converted_val)
                    if isinstance(converted_val, (int, float))
                    else int(str(converted_val))
                )
                index_oid = index_oid + (int_val,)
                instance_index_str += f".{int_val}"

        # Merge defaults for missing or "unset" columns
        default_row = _get_default_row(request.table_oid)
        merged_values: dict[str, Any] = {}
        incoming_values = request.column_values or {}
        for col_name, col_meta in columns.items():
            if col_name in index_columns:
                continue
            if col_name in incoming_values and not _should_use_default(incoming_values[col_name]):
                merged_values[col_name] = incoming_values[col_name]
                continue
            if col_name in default_row:
                merged_values[col_name] = default_row[col_name]
                continue
            default_val = col_meta.get("default", "")
            if default_val != "":
                merged_values[col_name] = default_val

        # Persist the table instance to disk
        instance_oid = snmp_agent.add_table_instance(
            table_oid=request.table_oid,
            index_values=request.index_values,
            column_values=merged_values,
        )

        logger.info(f"Successfully created table instance: {instance_oid}")

        return {
            "status": "ok",
            "table_oid": request.table_oid,
            "instance_index": instance_index_str.lstrip("."),
            "instance_oid": instance_oid,
            "columns_created": [str(col) for col in merged_values.keys()] if merged_values else [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create table instance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create instance: {str(e)}")


@app.delete("/table-row")
def delete_table_row(request: CreateTableRowRequest) -> dict[str, Any]:
    """Delete a table instance (soft delete, marks as deleted)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:

        def _extract_index_str(values: dict[str, Any]) -> str:
            """Extract instance string from index values, supporting multi-part __index__."""
            # Handle multi-part __index__ (__index__, __index_2__, __index_3__, etc.)
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

            # Legacy fallbacks
            if "index" in values:
                return str(values["index"])
            if "instance" in values:
                return str(values["instance"])
            if not values:
                return "1"
            return ".".join(str(v) for v in values.values())

        index_values = request.index_values or {}
        index_str = _extract_index_str(index_values)

        # Parse multi-part index string into separate __index__ values
        # E.g., "1.2.3" → {"__index__": "1", "__index_2__": "2", "__index_3__": "3"}
        index_parts = index_str.split(".")
        parsed_index_values = {}
        for i, part in enumerate(index_parts, 1):
            key = "__index__" if i == 1 else f"__index_{i}__"
            parsed_index_values[key] = part

        # Delete the instance
        success = snmp_agent.delete_table_instance(
            table_oid=request.table_oid, index_values=parsed_index_values
        )

        if success:
            logger.info(
                f"Deleted table instance: {request.table_oid} with indices {request.index_values}"
            )
            return {
                "status": "deleted",
                "table_oid": request.table_oid,
                "index_values": index_values,
            }
        else:
            raise HTTPException(status_code=404, detail="Table instance not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete table instance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete instance: {str(e)}")


@app.get("/config")
def get_config() -> dict[str, Any]:
    """Get GUI configuration from server."""
    try:
        config_path = Path("data/gui_config.yaml")
        if config_path.exists():
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config_path = Path("data/gui_config.json")
            if config_path.exists():
                import json

                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {}

        return config
    except Exception:
        logger.exception("Failed to load config")
        return {}


@app.post("/config")
def save_config(config: ConfigData) -> dict[str, Any]:
    """Save GUI configuration to server."""
    try:
        data_dir = Path("data")
        data_dir.mkdir(parents=True, exist_ok=True)

        config_dict = config.dict()

        try:
            import yaml

            config_path = data_dir / "gui_config.yaml"
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_dict, f)
        except ImportError:
            # Fallback to JSON if PyYAML not available
            config_path = data_dir / "gui_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                import json

                json.dump(config_dict, f, indent=2)

        return {"status": "ok", "message": "Configuration saved"}
    except Exception as e:
        logger.exception("Failed to save config")
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


# ============================================================================
# Trap Receiver Endpoints
# ============================================================================


class TrapReceiverConfig(BaseModel):
    """Configuration for trap receiver."""

    port: int = 16662
    community: str = "public"


@app.post("/trap-receiver/start")
def start_trap_receiver(config: Optional[TrapReceiverConfig] = None) -> dict[str, Any]:
    """Start the trap receiver."""
    global trap_receiver

    if trap_receiver and trap_receiver.is_running():
        return {
            "status": "already_running",
            "port": trap_receiver.port,
            "message": "Trap receiver is already running",
        }

    # Use provided config or defaults
    port = config.port if config else 16662
    community = config.community if config else "public"

    try:
        trap_receiver = TrapReceiver(
            port=port,
            community=community,
            logger=logger,
        )
        trap_receiver.start()

        return {
            "status": "started",
            "port": port,
            "community": community,
            "message": f"Trap receiver started on port {port}",
        }
    except Exception as e:
        logger.exception("Failed to start trap receiver")
        raise HTTPException(status_code=500, detail=f"Failed to start trap receiver: {str(e)}")


@app.post("/trap-receiver/stop")
def stop_trap_receiver() -> dict[str, Any]:
    """Stop the trap receiver."""
    global trap_receiver

    if not trap_receiver or not trap_receiver.is_running():
        return {"status": "not_running", "message": "Trap receiver is not running"}

    try:
        trap_receiver.stop()
        return {"status": "stopped", "message": "Trap receiver stopped"}
    except Exception as e:
        logger.exception("Failed to stop trap receiver")
        raise HTTPException(status_code=500, detail=f"Failed to stop trap receiver: {str(e)}")


@app.get("/trap-receiver/status")
def get_trap_receiver_status() -> dict[str, Any]:
    """Get trap receiver status."""
    global trap_receiver

    if not trap_receiver:
        return {"running": False, "port": None, "trap_count": 0}

    return {
        "running": trap_receiver.is_running(),
        "port": trap_receiver.port,
        "community": trap_receiver.community,
        "trap_count": len(trap_receiver.received_traps),
    }


@app.get("/trap-receiver/traps")
def get_received_traps(limit: Optional[int] = None) -> dict[str, Any]:
    """Get received traps."""
    global trap_receiver

    if not trap_receiver:
        return {"count": 0, "traps": []}

    traps = trap_receiver.get_received_traps(limit=limit)
    return {"count": len(traps), "traps": traps}


@app.delete("/trap-receiver/traps")
def clear_received_traps() -> dict[str, Any]:
    """Clear all received traps."""
    global trap_receiver

    if not trap_receiver:
        return {"status": "ok", "message": "No trap receiver active"}

    trap_receiver.clear_traps()
    return {"status": "ok", "message": "All received traps cleared"}


class TestTrapRequest(BaseModel):
    dest_host: str = "localhost"
    dest_port: int = 16662
    community: str = "public"


@app.post("/send-test-trap")
async def send_test_trap(request: TestTrapRequest) -> dict[str, Any]:
    """Send a test trap to the specified destination."""
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

    # Choose a test notification that actually exists in a MIB
    # If you have a custom TEST-MIB, use that here instead.
    test_mib = "SNMPv2-MIB"
    test_notification = "coldStart"

    # Use the agent's SnmpEngine so traps have the correct uptime
    snmp_engine = getattr(snmp_agent, "snmpEngine", None)
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
        )

    try:
        notif = NotificationType(ObjectIdentity(test_mib, test_notification)).resolve_with_mib(
            mib_view
        )
    except (SmiError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve test notification: {exc}",
        )

    # No need to manually set sysUpTime - the agent's engine already has it via readGet wrapper

    try:
        error_indication, error_status, error_index, _ = await send_notification(
            snmp_engine,
            CommunityData(request.community),
            await UdpTransportTarget.create((request.dest_host, request.dest_port)),
            ContextData(),
            "trap",
            notif,
        )
    except Exception as exc:
        logger.exception("Failed to send test trap")
        raise HTTPException(status_code=500, detail=str(exc))

    if error_indication:
        raise HTTPException(status_code=502, detail=str(error_indication))

    if error_status:
        raise HTTPException(
            status_code=502,
            detail=f"{error_status} at {error_index}",
        )

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


# ============================================================================
# Baking and Preset Management Endpoints
# ============================================================================


def _write_empty_state(state_file: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {"deleted_instances": [], "scalars": {}, "tables": {}}
    with state_file.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


@app.post("/bake-state")
def bake_state() -> dict[str, Any]:
    """
    Bake current MIB state into agent-model schema files.

    This endpoint:
    1. Backs up existing agent-model directory
    2. Reads current state from data/mib_state.json
    3. Merges state values into schema files as initial_value
    """
    from app.cli_bake_state import (
        backup_schemas,
        load_mib_state,
        bake_state_into_schemas,
    )
    from pathlib import Path

    schema_dir = Path("agent-model")
    state_file = Path("data/mib_state.json")
    backup_base = Path("agent-model-backups")

    try:
        # Backup existing schemas
        backup_dir = backup_schemas(schema_dir, backup_base)

        # Load current state
        state = load_mib_state(state_file)

        # Bake state into schemas
        baked_count = bake_state_into_schemas(schema_dir, state)

        # Clear the state file now that values have been baked into schemas
        _write_empty_state(state_file)

        # Clear the agent's in-memory state as well
        if snmp_agent is not None:
            snmp_agent.overrides = {}
            snmp_agent.table_instances = {}
            snmp_agent.deleted_instances = []
            try:
                snmp_agent._save_mib_state()
            except Exception:
                pass

        return {
            "status": "ok",
            "baked_count": baked_count,
            "backup_dir": str(backup_dir),
            "message": f"Successfully baked {baked_count} value(s) into schemas and cleared state",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bake state: {e}")


@app.post("/state/reset")
def reset_state() -> dict[str, Any]:
    """Clear mib_state.json (scalars, tables, deletions)."""
    from pathlib import Path

    state_file = Path("data/mib_state.json")

    try:
        _write_empty_state(state_file)

        if snmp_agent is not None:
            snmp_agent.overrides = {}
            snmp_agent.table_instances = {}
            snmp_agent.deleted_instances = []
            try:
                snmp_agent._save_mib_state()
            except Exception:
                pass

        return {"status": "ok", "message": "State reset"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset state: {e}")


@app.post("/state/fresh")
def fresh_state() -> dict[str, Any]:
    """Regenerate schemas and clear mib_state.json."""
    from app.cli_bake_state import backup_schemas
    from app.app_config import AppConfig
    from app.generator import BehaviourGenerator

    schema_dir = Path("agent-model")
    backup_base = Path("agent-model-backups")
    state_file = Path("data/mib_state.json")

    try:
        backup_dir = backup_schemas(schema_dir, backup_base)

        config = AppConfig()
        mibs = config.get("mibs", [])
        generator = BehaviourGenerator(output_dir=str(schema_dir))

        regenerated = 0
        for mib in mibs:
            compiled_path = Path("compiled-mibs") / f"{mib}.py"
            if not compiled_path.exists():
                continue
            generator.generate(str(compiled_path), mib_name=mib, force_regenerate=True)
            regenerated += 1

        _write_empty_state(state_file)

        if snmp_agent is not None:
            snmp_agent.overrides = {}
            snmp_agent.table_instances = {}
            snmp_agent.deleted_instances = []
            try:
                snmp_agent._save_mib_state()
            except Exception:
                pass

        return {
            "status": "ok",
            "backup_dir": str(backup_dir),
            "regenerated": regenerated,
            "message": "Fresh state complete",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run fresh state: {e}")


class PresetRequest(BaseModel):
    preset_name: str


@app.get("/presets")
def list_presets() -> dict[str, Any]:
    """List all available agent-model presets."""
    from app.cli_preset_manager import list_presets
    from pathlib import Path

    preset_base = Path("agent-model-presets")
    presets = list_presets(preset_base)

    return {
        "presets": presets,
        "count": len(presets),
    }


@app.post("/presets/save")
def save_preset(request: PresetRequest) -> dict[str, Any]:
    """Save current agent-model as a preset."""
    from app.cli_preset_manager import save_preset
    from pathlib import Path
    import sys
    from io import StringIO

    schema_dir = Path("agent-model")
    preset_base = Path("agent-model-presets")

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = save_preset(schema_dir, preset_base, request.preset_name)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to save preset: {output}")

        return {
            "status": "ok",
            "preset_name": request.preset_name,
            "message": f"Preset '{request.preset_name}' saved successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to save preset: {e}")


@app.post("/presets/load")
def load_preset(request: PresetRequest) -> dict[str, Any]:
    """Load a preset to replace current agent-model."""
    from app.cli_preset_manager import load_preset as load_preset_impl
    from pathlib import Path
    import sys
    from io import StringIO

    schema_dir = Path("agent-model")
    preset_base = Path("agent-model-presets")
    backup_base = Path("agent-model-backups")

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = load_preset_impl(
            schema_dir, preset_base, request.preset_name, backup_base, no_backup=False
        )
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to load preset: {output}")

        # Clear state after loading preset
        try:
            _write_empty_state(Path("data/mib_state.json"))
            if snmp_agent is not None:
                snmp_agent.overrides = {}
                snmp_agent.table_instances = {}
                snmp_agent.deleted_instances = []
                try:
                    snmp_agent._save_mib_state()
                except Exception:
                    pass
        except Exception:
            pass

        return {
            "status": "ok",
            "preset_name": request.preset_name,
            "message": (
                f"Preset '{request.preset_name}' loaded successfully. "
                "Restart agent to apply changes."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to load preset: {e}")


@app.delete("/presets/{preset_name}")
def delete_preset(preset_name: str) -> dict[str, Any]:
    """Delete a preset."""
    from app.cli_preset_manager import delete_preset as delete_preset_impl
    from pathlib import Path
    import sys
    from io import StringIO

    preset_base = Path("agent-model-presets")

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = delete_preset_impl(preset_base, preset_name)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to delete preset: {output}")

        return {
            "status": "ok",
            "preset_name": preset_name,
            "message": f"Preset '{preset_name}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to delete preset: {e}")
