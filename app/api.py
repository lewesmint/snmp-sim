"""FastAPI application for SNMP simulator management and control."""

from __future__ import annotations

from fastapi import FastAPI

from app.api_config import router as config_router
from app.api_links import router as links_router
from app.api_mibs import router as mibs_router
from app.api_state import logger, set_snmp_agent, set_trap_receiver, state
from app.api_system import router as system_router
from app.api_table_views import router as table_views_router
from app.api_tables import router as tables_router
from app.api_trap_receiver import router as trap_receiver_router
from app.api_traps import router as traps_router

app = FastAPI()

app.include_router(system_router)
app.include_router(links_router)
app.include_router(mibs_router)
app.include_router(table_views_router)
app.include_router(tables_router)
app.include_router(traps_router)
app.include_router(trap_receiver_router)
app.include_router(config_router)

__all__ = [
    "app",
    "logger",
    "set_snmp_agent",
    "set_trap_receiver",
    "state",
]
