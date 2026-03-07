"""Shared API state for the FastAPI app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.app_logger import AppLogger

if TYPE_CHECKING:
    from app.snmp_agent import SNMPAgent
    from snmp_traps.trap_receiver import TrapReceiver


@dataclass
class ApiState:
    """In-memory references shared across API modules."""

    snmp_agent: SNMPAgent | None = None
    trap_receiver: TrapReceiver | None = None

    def __setattr__(self, name: str, value: object) -> None:
        """Enforce state invariants before assigning attributes."""
        if name == "snmp_agent" and value is not None:
            snmp_engine = None
            if isinstance(value, HasSnmpEngine):
                snmp_engine = value.snmp_engine
            if snmp_engine is None:
                msg = "snmp_agent must expose a non-None 'snmp_engine'"
                raise ValueError(msg)
        super().__setattr__(name, value)


@runtime_checkable
class HasSnmpEngine(Protocol):
    """Protocol for objects exposing an SNMP engine reference."""

    snmp_engine: object | None


state = ApiState()
logger = AppLogger.get(__name__)


def set_snmp_agent(agent: SNMPAgent | None) -> None:
    """Set the global SNMP agent reference used by API handlers."""
    state.snmp_agent = agent


def set_trap_receiver(receiver: TrapReceiver | None) -> None:
    """Set the global trap receiver reference used by API handlers."""
    state.trap_receiver = receiver
