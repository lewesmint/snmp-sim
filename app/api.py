from fastapi import FastAPI, HTTPException
from app.app_logger import AppLogger
from pydantic import BaseModel
from typing import Optional, Any, Literal
from pathlib import Path

# Reference to the SNMPAgent instance will be set by main app
snmp_agent: Optional[Any] = None

logger = AppLogger.get("__name__")
app = FastAPI()


class SysDescrUpdate(BaseModel):
    value: str


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
        raise HTTPException(
            status_code=404, detail=f"Type '{type_name}' not found in registry"
        )

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


@app.get("/ready")
def check_ready() -> dict[str, Any]:
    """Check if the SNMP agent is fully initialized and ready to serve requests."""
    if snmp_agent is None:
        raise HTTPException(status_code=503, detail="SNMP agent not initialized")

    # Check if mib_builder is initialized (indicates agent is fully ready)
    if not hasattr(snmp_agent, 'mib_builder') or snmp_agent.mib_builder is None:
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
    # Load all schema files from mock-behaviour directory
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "mock-behaviour"
    if not os.path.exists(schema_dir):
        return {"count": 0, "mibs": []}

    schemas = load_all_schemas(schema_dir)
    mibs = sorted(list(schemas.keys()))
    return {"count": len(mibs), "mibs": mibs}


@app.get("/oids")
def list_oids() -> dict[str, Any]:
    """List all OIDs implemented by the agent."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    oid_map = snmp_agent.get_all_oids()
    return {"count": len(oid_map), "oids": oid_map}


@app.get("/oid-metadata")
def get_oid_metadata() -> dict[str, Any]:
    """Get full metadata for all OIDs including access, type, syntax, status, description from schema files."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schema files from mock-behaviour directory
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "mock-behaviour"
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
                    oid_str = ".".join(str(x) for x in oid_tuple)

                    metadata_map[oid_str] = {
                        "oid": oid_tuple,
                        "oid_str": oid_str,
                        "name": obj_name,
                        "type": obj_data.get("type", ""),
                        "access": obj_data.get("access", ""),
                        "mib": mib_name,
                        "initial": obj_data.get("initial"),
                        "enums": obj_data.get("enums"),
                        "dynamic_function": obj_data.get("dynamic_function")
                    }

    return {"count": len(metadata_map), "metadata": metadata_map}


@app.get("/table-schema")
def get_table_schema(oid: str) -> dict[str, Any]:
    """Get schema information for a table OID."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    try:
        parts = tuple(int(x) for x in oid.split(".")) if oid else ()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid OID format")

    # Load all schemas
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "mock-behaviour"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Find the table in schemas
    table_info = None
    table_name = None
    mib_name = None
    entry_info = None
    entry_name = None

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
                    if obj_oid == parts and obj_data.get("type") == "MibTable":
                        table_info = obj_data
                        table_name = obj_name
                        mib_name = mib
                    elif len(obj_oid) == len(parts) + 1 and obj_oid[:-1] == parts and obj_oid[-1] == 1 and obj_data.get("type") == "MibTableRow":
                        entry_info = obj_data
                        entry_name = obj_name

    if not table_info:
        raise HTTPException(status_code=404, detail="Table not found")

    # Get entry OID (usually table_oid + .1)
    entry_oid = parts + (1,)

    # Get index columns from entry
    index_columns = entry_info.get("indexes", []) if entry_info else []

    # Find columns
    columns = {}
    for mib, schema in schemas.items():
        # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
        if isinstance(schema, dict):
            if "objects" in schema:
                # New structure
                objects = schema["objects"]
            else:
                # Old flat structure
                objects = schema
        else:
            continue  # type: ignore[unreachable]

        for obj_name, obj_data in objects.items():
            if isinstance(obj_data, dict) and "oid" in obj_data:
                obj_oid = obj_data["oid"]
                if len(obj_oid) > len(entry_oid) and obj_oid[:len(entry_oid)] == entry_oid:
                    # This is a column in the table
                    col_name = obj_name
                    is_index = col_name in index_columns
                    columns[col_name] = {
                        "oid": obj_oid,
                        "type": obj_data.get("type", ""),
                        "access": obj_data.get("access", ""),
                        "is_index": is_index,
                        "default": obj_data.get("initial", ""),
                        "enums": obj_data.get("enums")
                    }

    return {
        "name": table_name,
        "oid": parts,
        "mib": mib_name,
        "entry_oid": entry_oid,
        "entry_name": entry_name,
        "index_columns": index_columns,
        "columns": columns
    }


@app.get("/value")
def get_oid_value(oid: str) -> dict[str, Any]:
    """Get the value for a specific OID string (dot separated)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = tuple(int(x) for x in oid.split(".")) if oid else ()
    except ValueError:
        logger.error(f"Invalid OID format requested: {oid}")
        raise HTTPException(status_code=400, detail="Invalid OID format")

    try:
        value = snmp_agent.get_scalar_value(parts)
    except ValueError as e:
        # Expected: scalar not found for this OID — return 404 without full traceback
        logger.warning(f"Scalar OID not found: {parts} - {e}")
        raise HTTPException(status_code=404, detail=f"OID not found: {e}")
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
            return [ _make_jsonable(x) for x in v ]
        try:
            return str(v)
        except Exception:
            return repr(v)

    serializable = _make_jsonable(value)
    logger.info(f"Fetched value for OID {parts}: {serializable}")
    return {"oid": parts, "value": serializable}


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


@app.get("/traps")
def list_traps() -> dict[str, Any]:
    """List all available SNMP traps/notifications from all loaded MIBs."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schema files
    from app.cli_load_model import load_all_schemas
    import os

    schema_dir = "mock-behaviour"
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


# In-memory storage for trap overrides (in production, this would be persisted)
trap_overrides: dict[str, dict[str, str]] = {}


@app.get("/trap-overrides/{trap_name}")
def get_trap_overrides(trap_name: str) -> dict[str, Any]:
    """Get stored overrides for a specific trap."""
    return {"trap_name": trap_name, "overrides": trap_overrides.get(trap_name, {})}


@app.post("/trap-overrides/{trap_name}")
def set_trap_overrides(trap_name: str, overrides: dict[str, str]) -> dict[str, Any]:
    """Set overrides for a specific trap."""
    trap_overrides[trap_name] = overrides
    return {"status": "ok", "trap_name": trap_name, "overrides": overrides}


@app.delete("/trap-overrides/{trap_name}")
def clear_trap_overrides(trap_name: str) -> dict[str, Any]:
    """Clear all overrides for a specific trap."""
    if trap_name in trap_overrides:
        del trap_overrides[trap_name]
    return {"status": "ok", "trap_name": trap_name}


class TrapSendRequest(BaseModel):
    trap_name: str
    trap_type: Literal["trap", "inform"] = "trap"
    dest_host: Optional[str] = "localhost"
    dest_port: Optional[int] = 162
    community: Optional[str] = "public"


@app.post("/send-trap")
def send_trap(request: TrapSendRequest) -> dict[str, Any]:
    """Send an SNMP trap/notification."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")

    # Load all schemas to find the trap
    from app.cli_load_model import load_all_schemas
    from app.trap_sender import TrapSender
    import os

    schema_dir = "mock-behaviour"
    if not os.path.exists(schema_dir):
        raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")

    schemas = load_all_schemas(schema_dir)

    # Find the trap in schemas
    trap_info = None
    trap_mib = None

    for mib_name, schema in schemas.items():
        if isinstance(schema, dict) and "traps" in schema:
            if request.trap_name in schema["traps"]:
                trap_info = schema["traps"][request.trap_name]
                trap_mib = mib_name
                break

    if not trap_info:
        raise HTTPException(status_code=404, detail=f"Trap '{request.trap_name}' not found")

    # Get trap OID
    trap_oid = tuple(trap_info["oid"])

    try:
        # Create trap sender
        sender = TrapSender(
            mib_builder=snmp_agent.mib_builder,
            dest=(request.dest_host or "localhost", request.dest_port or 162),
            community=request.community or "public",
            mib_name=str(trap_mib or "__MY_MIB"),
            logger=logger,
        )

        # Send the trap
        # For now, send with a simple value - in future we could populate varbinds from trap_info["objects"]
        sender.send_trap(trap_oid, "Trap triggered from GUI", trap_type=request.trap_type)

        logger.info(f"Sent {request.trap_type} for trap {request.trap_name} (OID: {trap_oid})")
        
        return {
            "status": "ok",
            "trap_name": request.trap_name,
            "trap_oid": trap_oid,
            "trap_type": request.trap_type,
            "destination": f"{request.dest_host}:{request.dest_port}",
            "objects": trap_info.get("objects", []),
        }
    except Exception as e:
        logger.exception(f"Failed to send trap {request.trap_name}")
        raise HTTPException(status_code=500, detail=f"Failed to send trap: {str(e)}")


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
        # Parse table OID
        table_parts = tuple(int(x) for x in request.table_oid.split(".")) if request.table_oid else ()
        entry_oid = table_parts + (1,)
        
        # Get the first index value to create the instance OID
        if not request.index_values:
            raise HTTPException(status_code=400, detail="No index values provided")
        
        # Extract first index value
        first_index_value = list(request.index_values.values())[0]
        
        # Set the index value first
        index_oid = entry_oid + (1, int(first_index_value))
        try:
            snmp_agent.set_scalar_value(index_oid, first_index_value)
            logger.info(f"Created table instance: {index_oid}")
        except Exception as e:
            logger.warning(f"Could not set index value: {e}")
        
        # Set other column values if provided
        created_columns = [str(index_oid)]
        
        # Load schemas to find column OIDs
        from app.cli_load_model import load_all_schemas
        import os
        
        schema_dir = "mock-behaviour"
        if not os.path.exists(schema_dir):
            raise HTTPException(status_code=500, detail=f"Schema directory not found: {schema_dir}")
        
        schemas = load_all_schemas(schema_dir)
        
        # Set each column value
        for col_name, col_value in request.column_values.items():
            # Find the column OID in schemas
            for mib, schema in schemas.items():
                if isinstance(schema, dict):
                    if "objects" in schema:
                        objects = schema["objects"]
                    else:
                        objects = schema
                else:
                    continue  # type: ignore[unreachable]

                if col_name in objects:
                    col_data = objects[col_name]
                    if isinstance(col_data, dict) and "oid" in col_data:
                        col_oid = tuple(col_data["oid"])
                        # Create instance OID for this column
                        instance_col_oid = col_oid + (int(first_index_value),)
                        try:
                            snmp_agent.set_scalar_value(instance_col_oid, col_value)
                            created_columns.append(str(instance_col_oid))
                            logger.info(f"Set {col_name} for instance {first_index_value}")
                        except Exception as e:
                            logger.warning(f"Could not set {col_name}: {e}")
                        break
        
        return {
            "status": "ok",
            "table_oid": request.table_oid,
            "instance_index": first_index_value,
            "instance_oid": f"{request.table_oid}.1.{first_index_value}",
            "columns_created": created_columns
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating table row: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create table row: {str(e)}")


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
