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
