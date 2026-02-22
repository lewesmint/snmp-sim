# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
"""Optimized synchronous wrapper for PySNMP 7.x async HLAPI.

Provides two main client patterns:
  • StatelessSnmpClient: Fresh engine per call (simple, safe)
  • PersistentSnmpClient: Reused engine (efficient, for loops)

For direct use, the sync functions work with either pattern:
  • get_sync(..., use_persistent_loop=False)  # Fresh loop per call (default)
  • get_sync(..., use_persistent_loop=True)   # Persistent background loop
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Tuple, Union

# PySNMP imports
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    set_cmd,
    next_cmd,
)

VarBinds = Sequence[ObjectType]
GetResult = Tuple[Any, Any, Any, Tuple[ObjectType, ...]]


# ============================================================================
# Custom Exception
# ============================================================================


class SnmpSyncError(Exception):
    """Raised when SNMP operation (GET/SET/GET-NEXT) fails."""

    pass


# ============================================================================
# Background Thread Event Loop Management
# ============================================================================


class _LoopThread(threading.Thread):
    """Background thread with persistent event loop for reusable engine."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._stop_event = threading.Event()
        self.start()

    def run(self) -> None:
        """Run the background event loop."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self) -> None:
        """Stop the background loop."""
        self._stop_event.set()
        self.loop.call_soon_threadsafe(self.loop.stop)


_GLOBAL_LOOP_THREAD: Optional[_LoopThread] = None
_GLOBAL_LOCK = threading.Lock()


def _get_global_loop_thread() -> _LoopThread:
    """Get or create the global background loop thread."""
    global _GLOBAL_LOOP_THREAD
    with _GLOBAL_LOCK:
        if _GLOBAL_LOOP_THREAD is None:
            _GLOBAL_LOOP_THREAD = _LoopThread()
        return _GLOBAL_LOOP_THREAD


# ============================================================================
# Sync Runners
# ============================================================================


def run_sync(coro: Any) -> Any:
    """Run async coroutine: fresh loop per call.

    Each call creates and closes an event loop (slower for multiple ops).
    Use when you don't care about engine reuse.
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        return asyncio.run(coro)

    loop_thread = _get_global_loop_thread()
    future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, loop_thread.loop)
    return future.result()


def run_sync_persistent(coro: Any) -> Any:
    """Run async coroutine: persistent background loop.

    Reuses one event loop across all calls (better for engine reuse).
    Required for PersistentSnmpClient to work properly.
    """
    loop_thread = _get_global_loop_thread()
    future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, loop_thread.loop)
    return future.result()


# ============================================================================
# Internal Async Operations
# ============================================================================


async def _get_async(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
) -> GetResult:
    """Async GET operation."""
    if context is None:
        context = ContextData()
    target = await UdpTransportTarget.create(address, timeout=timeout, retries=retries)
    error_indication, error_status, error_index, result_var_binds = await get_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


async def _set_async(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
) -> GetResult:
    """Async SET operation."""
    if context is None:
        context = ContextData()
    target = await UdpTransportTarget.create(address, timeout=timeout, retries=retries)
    error_indication, error_status, error_index, result_var_binds = await set_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


async def _next_async(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
) -> GetResult:
    """Async GET-NEXT operation (for snmpwalk)."""
    if context is None:
        context = ContextData()
    target = await UdpTransportTarget.create(address, timeout=timeout, retries=retries)
    error_indication, error_status, error_index, result_var_binds = await next_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


def _raise_on_error(error_indication: Any, error_status: Any, error_index: Any) -> None:
    """Raise if SNMP operation failed."""
    if error_indication:
        raise SnmpSyncError(f"SNMP error: {error_indication}")
    if error_status:
        idx = int(error_index) if error_index else 0
        raise SnmpSyncError(f"{error_status.prettyPrint()} at varbind index {idx}")


# ============================================================================
# Public Sync Functions
# ============================================================================


def get_sync(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
    use_persistent_loop: bool = False,
) -> Tuple[ObjectType, ...]:
    """Synchronous SNMP GET.

    Args:
        engine: SnmpEngine instance
        auth: CommunityData (v2c) or UsmUserData (v3)
        address: (hostname, port) tuple
        var_binds: [ObjectType(...), ...]
        timeout: seconds (default 1.0)
        retries: count (default 5)
        context: ContextData or None
        use_persistent_loop: Use persistent background loop (for engine reuse)

    Returns:
        Tuple of ObjectType results

    Raises:
        SnmpSyncError: If operation fails
    """
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _get_async(
            engine,
            auth,
            address,
            var_binds,
            timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


def set_sync(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
    use_persistent_loop: bool = False,
) -> Tuple[ObjectType, ...]:
    """Synchronous SNMP SET.

    Args:
        engine: SnmpEngine instance
        auth: CommunityData (v2c) or UsmUserData (v3)
        address: (hostname, port) tuple
        var_binds: [ObjectType(ObjectIdentity(...), value), ...]
        timeout: seconds (default 1.0)
        retries: count (default 5)
        context: ContextData or None
        use_persistent_loop: Use persistent background loop (for engine reuse)

    Returns:
        Tuple of ObjectType results

    Raises:
        SnmpSyncError: If operation fails
    """
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _set_async(
            engine,
            auth,
            address,
            var_binds,
            timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


def get_next_sync(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
    use_persistent_loop: bool = False,
) -> Tuple[ObjectType, ...]:
    """Synchronous SNMP GET-NEXT (for snmpwalk).

    Args:
        engine: SnmpEngine instance
        auth: CommunityData (v2c) or UsmUserData (v3)
        address: (hostname, port) tuple
        var_binds: [ObjectType(...), ...]
        timeout: seconds (default 1.0)
        retries: count (default 5)
        context: ContextData or None
        use_persistent_loop: Use persistent background loop (for engine reuse)

    Returns:
        Tuple of ObjectType results

    Raises:
        SnmpSyncError: If operation fails
    """
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _next_async(
            engine,
            auth,
            address,
            var_binds,
            timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


# ============================================================================
# Client Classes
# ============================================================================


@dataclass(slots=True)
class StatelessSnmpClient:
    """SNMP client: creates fresh engine per operation.

    ✓ Simplest, safest, no state issues
    ✓ Each call is independent
    ✗ ~0.02s overhead per call (creates event loop)

    Example:
        client = StatelessSnmpClient(
            auth=CommunityData("public", mpModel=1),
            address=("192.168.1.1", 161),
        )
        result = client.get(ObjectType(make_oid("1.3.6.1.2.1.1.1.0")))
    """

    auth: Union[CommunityData, UsmUserData]
    address: Tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = field(default_factory=ContextData)

    def get(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous GET (fresh engine)."""
        engine = SnmpEngine()
        return get_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
        )

    def set(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous SET (fresh engine)."""
        engine = SnmpEngine()
        return set_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
        )

    def get_next(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous GET-NEXT (fresh engine)."""
        engine = SnmpEngine()
        return get_next_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
        )


@dataclass(slots=True)
class PersistentSnmpClient:
    """SNMP client: reuses engine + persistent background loop.

    ✓ Fastest for repeated operations
    ✓ Engine state preserved across calls
    ✓ Perfect for snmpwalk loops
    ✗ Must call shutdown() when done
    ✗ Slightly more complex

    Example:
        client = PersistentSnmpClient(
            auth=CommunityData("public", mpModel=1),
            address=("192.168.1.1", 161),
        )

        # Loop through OIDs
        current_oid = ObjectType(make_oid("1.3.6.1.4.1.1"))
        for i in range(10):
            result = client.get_next(current_oid)
            print(result[0])
            current_oid = result[0]

        client.shutdown()
    """

    auth: Union[CommunityData, UsmUserData]
    address: Tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = field(default_factory=ContextData)
    _engine: Optional[SnmpEngine] = field(default=None, init=False, repr=False)

    def _ensure_engine(self) -> SnmpEngine:
        """Lazily create engine on first use."""
        if self._engine is None:
            self._engine = SnmpEngine()
        return self._engine

    def get(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous GET (reused engine + persistent loop)."""
        engine = self._ensure_engine()
        return get_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
            use_persistent_loop=True,
        )

    def set(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous SET (reused engine + persistent loop)."""
        engine = self._ensure_engine()
        return set_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
            use_persistent_loop=True,
        )

    def get_next(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Synchronous GET-NEXT (reused engine + persistent loop)."""
        engine = self._ensure_engine()
        return get_next_sync(
            engine,
            self.auth,
            self.address,
            var_binds,
            self.timeout,
            self.retries,
            self.context,
            use_persistent_loop=True,
        )

    def shutdown(self) -> None:
        """Cleanup: call when completely done."""
        self._engine = None
        shutdown_sync_wrapper()


# ============================================================================
# Utility Functions
# ============================================================================


def make_oid(oid: str) -> ObjectIdentity:
    """Create ObjectIdentity from OID string. Example: make_oid("1.3.6.1.2.1.1.1.0")"""
    return ObjectIdentity(oid)


def shutdown_sync_wrapper() -> None:
    """Optional: shutdown background loop (required for process cleanup)."""
    global _GLOBAL_LOOP_THREAD
    with _GLOBAL_LOCK:
        if _GLOBAL_LOOP_THREAD is not None:
            _GLOBAL_LOOP_THREAD.stop()
            _GLOBAL_LOOP_THREAD = None
