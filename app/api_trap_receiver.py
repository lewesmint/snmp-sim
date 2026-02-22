"""Trap receiver endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_state import logger, set_trap_receiver, state
from app.trap_receiver import TrapReceiver

router = APIRouter()


class TrapReceiverConfig(BaseModel):
    """Configuration for trap receiver."""

    port: int = 16662
    community: str = "public"


@router.post("/trap-receiver/start")
def start_trap_receiver(config: TrapReceiverConfig | None = None) -> dict[str, object]:
    """Start the trap receiver."""
    if state.trap_receiver and state.trap_receiver.is_running():
        return {
            "status": "already_running",
            "port": state.trap_receiver.port,
            "message": "Trap receiver is already running",
        }

    port = config.port if config else 16662
    community = config.community if config else "public"

    try:
        receiver = TrapReceiver(
            port=port,
            community=community,
            logger=logger,
        )
        receiver.start()
        set_trap_receiver(receiver)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.exception("Failed to start trap receiver")
        raise HTTPException(status_code=500, detail=f"Failed to start trap receiver: {e!s}") from e
    else:
        return {
            "status": "started",
            "port": port,
            "community": community,
            "message": f"Trap receiver started on port {port}",
        }


@router.post("/trap-receiver/stop")
def stop_trap_receiver() -> dict[str, object]:
    """Stop the trap receiver."""
    if not state.trap_receiver or not state.trap_receiver.is_running():
        return {"status": "not_running", "message": "Trap receiver is not running"}

    try:
        state.trap_receiver.stop()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.exception("Failed to stop trap receiver")
        raise HTTPException(status_code=500, detail=f"Failed to stop trap receiver: {e!s}") from e
    else:
        return {"status": "stopped", "message": "Trap receiver stopped"}


@router.get("/trap-receiver/status")
def get_trap_receiver_status() -> dict[str, object]:
    """Get trap receiver status."""
    if not state.trap_receiver:
        return {"running": False, "port": None, "trap_count": 0}

    return {
        "running": state.trap_receiver.is_running(),
        "port": state.trap_receiver.port,
        "community": state.trap_receiver.community,
        "trap_count": len(state.trap_receiver.received_traps),
    }


@router.get("/trap-receiver/traps")
def get_received_traps(limit: int | None = None) -> dict[str, object]:
    """Get received traps."""
    if not state.trap_receiver:
        return {"count": 0, "traps": []}

    traps = state.trap_receiver.get_received_traps(limit=limit)
    return {"count": len(traps), "traps": traps}


@router.delete("/trap-receiver/traps")
def clear_received_traps() -> dict[str, object]:
    """Clear all received traps."""
    if not state.trap_receiver:
        return {"status": "ok", "message": "No trap receiver active"}

    state.trap_receiver.clear_traps()
    return {"status": "ok", "message": "All received traps cleared"}
