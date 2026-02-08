from fastapi import FastAPI, HTTPException
from app.app_logger import AppLogger
from pydantic import BaseModel
from typing import Optional, Any

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
    from app.mib_metadata import MIB_METADATA

    mibs = list(MIB_METADATA.keys())
    return {"count": len(mibs), "mibs": sorted(mibs)}


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
        for obj_name, obj_data in schema.items():
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


@app.get("/value")
def get_oid_value(oid: str) -> dict[str, Any]:
    """Get the value for a specific OID string (dot separated)."""
    if snmp_agent is None:
        raise HTTPException(status_code=500, detail="SNMP agent not initialized")
    try:
        parts = tuple(int(x) for x in oid.split(".")) if oid else ()
    except ValueError as e:
        logger.error(f"Invalid OID format requested: {oid} - {e}")
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
