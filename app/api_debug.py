"""SNMP operation debug log — for integration test harnesses only.

Exposes a small in-memory ring buffer of SNMP operations that the agent
has processed.  The test harness can query this buffer over HTTP to verify
that the agent actually acted on a GET/SET rather than relying solely on
the manager-side response.

Endpoints:
  GET    /debug/snmp-operations  - return all buffered operations as JSON
  DELETE /debug/snmp-operations  - clear the buffer (call at test start)

The buffer is intentionally lightweight: a thread-safe deque capped at
``_MAX_OPS`` entries.  It is NOT persistent across restarts.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter

router = APIRouter()

_MAX_OPS: int = 200
_ops_lock = threading.Lock()
_ops_log: deque[dict[str, Any]] = deque(maxlen=_MAX_OPS)


def record_snmp_operation(op_type: str, oid: str, value: str | None = None) -> None:
    """Append one operation entry to the debug ring buffer.

    Called from the MIB instrumentation hooks; safe to call from any thread.

    Args:
        op_type: "GET", "GETNEXT", or "SET".
        oid:     Dotted-decimal OID string.
        value:   Pretty-printed value for SET operations; None for reads.

    """
    entry: dict[str, Any] = {
        "type": op_type,
        "oid": oid,
        "timestamp": time.time(),
    }
    if value is not None:
        entry["value"] = value
    with _ops_lock:
        _ops_log.append(entry)


@router.get("/debug/snmp-operations")
def get_snmp_operations() -> dict[str, Any]:
    """Return all SNMP operations recorded since the last clear."""
    with _ops_lock:
        ops = list(_ops_log)
    return {"count": len(ops), "operations": ops}


@router.delete("/debug/snmp-operations")
def clear_snmp_operations() -> dict[str, str]:
    """Clear the SNMP operation debug log."""
    with _ops_lock:
        _ops_log.clear()
    return {"status": "cleared"}
