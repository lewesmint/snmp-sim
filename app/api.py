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
