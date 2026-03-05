# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
"""Synchronous wrapper around the asyncio-based PySNMP 7.x HLAPI.

This module provides a synchronous interface to PySNMP's async HLAPI:
  - get_sync(...): synchronous SNMP GET
  - set_sync(...): synchronous SNMP SET
  - SyncSnmpClient: convenience class for repeated operations
  - make_oid(...): helper to create ObjectIdentity from OID strings

Thread Safety:
  - If called from a thread without a running event loop, creates a new loop via asyncio.run().
  - If called from a thread with a running loop (common in async contexts), uses a background
    thread event loop to avoid blocking.

Requirements:
  - PySNMP 7.x async HLAPI (SnmpEngine, ContextData, etc.)
  - Auth object (CommunityData for SNMPv2c, UsmUserData for SNMPv3)
  - Transport target (UdpTransportTarget)
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine, Sequence
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# PySNMP imports
from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    CommunityData,
    UsmUserData,
    get_cmd,
    next_cmd,
    set_cmd,
)


VarBinds = Sequence[ObjectType]


@runtime_checkable
class _PrettyPrintable(Protocol):
    def prettyPrint(self) -> str: ...  # noqa: N802


@runtime_checkable
class _IntLike(Protocol):
    def __int__(self) -> int: ...


type ErrorStatus = _PrettyPrintable | int | None
type ErrorIndex = _IntLike | int | None
GetResult = tuple[object | None, ErrorStatus, ErrorIndex, tuple[ObjectType, ...]]


class SnmpSyncError(RuntimeError):
    """Raised when SNMP get/set reports an errorIndication/errorStatus."""


class _LoopThread:
    """Dedicated event loop running in a background thread."""

    def __init__(self) -> None:
        self._loop_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(
            target=self._run, name="pysnmp-sync-loop", daemon=True
        )
        self._thread.start()
        self._loop_ready.wait()

    def _run(self) -> None:
        """Run the event loop in this thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            # Cancel pending tasks on shutdown
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            message = "Background loop not initialised."
            raise RuntimeError(message)
        return self._loop

    def stop(self) -> None:
        loop = self.loop
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=2.0)


_GLOBAL_LOCK = threading.Lock()


@dataclass(slots=True)
class _GlobalState:
    loop_thread: _LoopThread | None = None


_GLOBAL_STATE = _GlobalState()


def _get_global_loop_thread() -> _LoopThread:
    with _GLOBAL_LOCK:
        if _GLOBAL_STATE.loop_thread is None:
            _GLOBAL_STATE.loop_thread = _LoopThread()
        return _GLOBAL_STATE.loop_thread


def run_sync[T](coro: Coroutine[object, object, T], *, result_timeout: float | None = None) -> T:
    """Run an async coroutine synchronously."""
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        return asyncio.run(coro)  # creates/closes its own loop

    loop_thread = _get_global_loop_thread()
    future: Future[T] = asyncio.run_coroutine_threadsafe(coro, loop_thread.loop)
    return future.result(timeout=result_timeout)


def run_sync_persistent[T](
    coro: Coroutine[object, object, T], *, result_timeout: float | None = None
) -> T:
    """Run an async coroutine on the persistent background loop."""
    loop_thread = _get_global_loop_thread()
    future: Future[T] = asyncio.run_coroutine_threadsafe(coro, loop_thread.loop)
    return future.result(timeout=result_timeout)


async def _get_async(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    request_timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
) -> GetResult:
    """Perform an asynchronous SNMP GET command."""
    if context is None:
        context = ContextData()

    # Create transport target asynchronously (PySNMP 7.x requirement)
    target = await UdpTransportTarget.create(
        address, timeout=request_timeout, retries=retries
    )

    # get_cmd is a coroutine function that directly returns the result tuple
    error_indication, error_status, error_index, result_var_binds = await get_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


async def _set_async(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    request_timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
) -> GetResult:
    """Perform an asynchronous SNMP SET command."""
    if context is None:
        context = ContextData()

    # Create transport target asynchronously (PySNMP 7.x requirement)
    target = await UdpTransportTarget.create(
        address, timeout=request_timeout, retries=retries
    )

    # set_cmd is a coroutine function that directly returns the result tuple
    error_indication, error_status, error_index, result_var_binds = await set_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


async def _next_async(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    request_timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
) -> GetResult:
    """Perform an asynchronous SNMP GET-NEXT command."""
    if context is None:
        context = ContextData()

    # Create transport target asynchronously (PySNMP 7.x requirement)
    target = await UdpTransportTarget.create(
        address, timeout=request_timeout, retries=retries
    )

    # next_cmd is a coroutine function that directly returns the result tuple
    error_indication, error_status, error_index, result_var_binds = await next_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


def _raise_on_error(
    error_indication: object | None,
    error_status: ErrorStatus,
    error_index: ErrorIndex,
) -> None:
    """Raise an exception if an SNMP operation reports an error."""
    if error_indication:
        message = f"SNMP error: {error_indication}"
        raise SnmpSyncError(message)

    # error_status is truthy when there is a PDU-level error
    if error_status:
        idx = int(error_index) if error_index is not None else 0
        if isinstance(error_status, _PrettyPrintable):
            status_text = error_status.prettyPrint()
        else:
            status_text = str(error_status)
        message = f"{status_text} at varbind index {idx}"
        raise SnmpSyncError(message)


def get_sync(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
    *,
    use_persistent_loop: bool = False,
) -> tuple[ObjectType, ...]:
    """Perform a synchronous SNMP GET operation."""
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _get_async(
            engine,
            auth,
            address,
            var_binds,
            request_timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


def set_sync(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
    *,
    use_persistent_loop: bool = False,
) -> tuple[ObjectType, ...]:
    """Perform a synchronous SNMP SET operation."""
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _set_async(
            engine,
            auth,
            address,
            var_binds,
            request_timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


def get_next_sync(
    engine: SnmpEngine,
    auth: CommunityData | UsmUserData,
    address: tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: ContextData | None = None,
    *,
    use_persistent_loop: bool = False,
) -> tuple[ObjectType, ...]:
    """Perform a synchronous SNMP GET-NEXT operation."""
    runner = run_sync_persistent if use_persistent_loop else run_sync
    error_indication, error_status, error_index, result_var_binds = runner(
        _next_async(
            engine,
            auth,
            address,
            var_binds,
            request_timeout=timeout,
            retries=retries,
            context=context,
        )
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


@dataclass(slots=True)
class SyncSnmpClient:
    """Provide synchronous methods over a pre-existing SNMP engine.

    ⚠️  WARNING: Do NOT reuse the same engine across multiple calls if using asyncio.run().
    Each call to get_sync/set_sync/get_next_sync with asyncio.run() creates and closes an
    event loop, leaving the engine in a broken state for the next call.

    Use StatelessSnmpClient (creates fresh engine per call) or PersistentSnmpClient
    (uses persistent background loop) instead.

    Example (if you know what you're doing):
        client = SyncSnmpClient(
            engine=SnmpEngine(),
            auth=CommunityData("public", mpModel=1),  # SNMPv2c
            address=("127.0.0.1", 161),
            timeout=1.0,
            retries=1,
        )

        vb = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
        res = client.get(vb)
    """

    engine: SnmpEngine
    auth: CommunityData | UsmUserData
    address: tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = field(default_factory=ContextData)

    def get(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform a GET request with the configured client settings."""
        return get_sync(
            engine=self.engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )

    def set(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform a SET request with the configured client settings."""
        return set_sync(
            engine=self.engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )

    def get_next(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform a GET-NEXT request with the configured client settings."""
        return get_next_sync(
            engine=self.engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )


@dataclass(slots=True)
class StatelessSnmpClient:
    """Create a fresh SNMP engine for every operation.

    ✓ Safe to use for any number of operations
    ✓ No engine reuse issues
    ✗ Slightly slower (creates fresh engine + loop each time)

    Example:
        client = StatelessSnmpClient(
            auth=CommunityData("public", mpModel=1),
            address=("127.0.0.1", 161),
            timeout=1.0,
            retries=1,
        )

        vb = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
        res = client.get(vb)  # Creates fresh engine internally
        res = client.get(vb)  # Creates another fresh engine

    """

    auth: CommunityData | UsmUserData
    address: tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = field(default_factory=ContextData)

    def get(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Create fresh engine, perform GET, discard engine."""
        engine = SnmpEngine()
        return get_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )

    def set(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Create fresh engine, perform SET, discard engine."""
        engine = SnmpEngine()
        return set_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )

    def get_next(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Create fresh engine, perform GET-NEXT, discard engine."""
        engine = SnmpEngine()
        return get_next_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )


@dataclass(slots=True)
class PersistentSnmpClient:
    """Reuse one engine on the persistent background event loop.

    ✓ Safe to reuse engine across unlimited operations
    ✓ Most efficient (engine + loop reused)
    ✓ Engine state preserved between calls
    ✗ Requires understanding of background loop internals
    ✗ Must call shutdown() when done if process needs cleanup

    Example:
        client = PersistentSnmpClient(
            auth=CommunityData("public", mpModel=1),
            address=("127.0.0.1", 161),
            timeout=1.0,
            retries=1,
        )

        vb = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
        res = client.get(vb)  # Uses persistent loop + engine
        res = client.get(vb)  # Reuses same loop + engine ✓

        # When done:
        client.shutdown()

    """

    auth: CommunityData | UsmUserData
    address: tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = field(default_factory=ContextData)
    _engine: SnmpEngine | None = None

    def _ensure_engine(self) -> SnmpEngine:
        """Lazily create engine on first use."""
        if self._engine is None:
            self._engine = SnmpEngine()
        return self._engine

    def get(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform GET using persistent engine + background loop."""
        engine = self._ensure_engine()
        return get_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
            use_persistent_loop=True,
        )

    def set(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform SET using persistent engine + background loop."""
        engine = self._ensure_engine()
        return set_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
            use_persistent_loop=True,
        )

    def get_next(self, *var_binds: ObjectType) -> tuple[ObjectType, ...]:
        """Perform GET-NEXT using persistent engine + background loop."""
        engine = self._ensure_engine()
        return get_next_sync(
            engine=engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
            use_persistent_loop=True,
        )

    def shutdown(self) -> None:
        """Clean up engine and background loop when done."""
        self._engine = None
        shutdown_sync_wrapper()


def make_oid(oid: str) -> ObjectIdentity:
    """Build an ObjectIdentity from an OID string."""
    return ObjectIdentity(oid)


# Optional: allow explicit shutdown of the background loop if your process needs it.
def shutdown_sync_wrapper() -> None:
    """Stop and clear the shared background loop thread."""
    with _GLOBAL_LOCK:
        if _GLOBAL_STATE.loop_thread is not None:
            _GLOBAL_STATE.loop_thread.stop()
            _GLOBAL_STATE.loop_thread = None


if __name__ == "__main__":
    # Minimal example (SNMPv2c GET sysDescr.0)
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    engine_ = SnmpEngine()
    auth_ = CommunityData("public", mpModel=1)
    address_ = ("127.0.0.1", 161)

    client = SyncSnmpClient(
        engine=engine_, auth=auth_, address=address_, timeout=1.0, retries=1
    )

    sys_descr = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
    try:
        result = client.get(sys_descr)
        for vb in result:
            logger.info(vb.prettyPrint())
    finally:
        shutdown_sync_wrapper()
