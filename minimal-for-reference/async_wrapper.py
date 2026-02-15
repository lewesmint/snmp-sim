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
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Sequence, Tuple, Union

# PySNMP imports
from pysnmp.hlapi.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    set_cmd,
)

if TYPE_CHECKING:
    from pysnmp.hlapi.asyncio import CommunityData, UsmUserData
else:
    from pysnmp.hlapi.asyncio import CommunityData, UsmUserData


VarBinds = Sequence[ObjectType]
GetResult = Tuple[Any, Any, Any, Tuple[ObjectType, ...]]


class SnmpSyncError(RuntimeError):
    """Raised when SNMP get/set reports an errorIndication/errorStatus."""


class _LoopThread:
    """Dedicated event loop running in a background thread."""

    def __init__(self) -> None:
        self._loop_ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread = threading.Thread(target=self._run, name="pysnmp-sync-loop", daemon=True)
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
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("Background loop not initialised.")
        return self._loop

    def stop(self) -> None:
        loop = self.loop
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=2.0)


_GLOBAL_LOOP_THREAD: Optional[_LoopThread] = None
_GLOBAL_LOCK = threading.Lock()


def _get_global_loop_thread() -> _LoopThread:
    global _GLOBAL_LOOP_THREAD
    with _GLOBAL_LOCK:
        if _GLOBAL_LOOP_THREAD is None:
            _GLOBAL_LOOP_THREAD = _LoopThread()
        return _GLOBAL_LOOP_THREAD


def run_sync(coro: Any) -> Any:
    """Run an async coroutine synchronously.

    Handles two cases:
      1. No event loop in current thread: uses asyncio.run() with a fresh loop.
      2. Event loop already running: schedules coroutine on a background thread's loop
         to avoid blocking the current loop.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        return asyncio.run(coro)  # creates/closes its own loop

    loop_thread = _get_global_loop_thread()
    future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, loop_thread.loop)
    return future.result()


async def _get_async(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
) -> GetResult:
    """Execute SNMP GET command asynchronously.

    Args:
        engine: SNMP engine instance
        auth: Authentication (CommunityData or UsmUserData)
        address: Tuple of (hostname, port) for SNMP agent
        var_binds: Variable bindings to get
        timeout: Timeout in seconds (default 1.0)
        retries: Number of retries (default 5)
        context: Optional SNMP context (defaults to ContextData())

    Returns:
        Tuple of (error_indication, error_status, error_index, result_var_binds)
    """
    if context is None:
        context = ContextData()

    # Create transport target asynchronously (PySNMP 7.x requirement)
    target = await UdpTransportTarget.create(address, timeout=timeout, retries=retries)

    # get_cmd is a coroutine function that directly returns the result tuple
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
    """Execute SNMP SET command asynchronously.

    Args:
        engine: SNMP engine instance
        auth: Authentication (CommunityData or UsmUserData)
        address: Tuple of (hostname, port) for SNMP agent
        var_binds: Variable bindings to set
        timeout: Timeout in seconds (default 1.0)
        retries: Number of retries (default 5)
        context: Optional SNMP context (defaults to ContextData())

    Returns:
        Tuple of (error_indication, error_status, error_index, result_var_binds)
    """
    if context is None:
        context = ContextData()

    # Create transport target asynchronously (PySNMP 7.x requirement)
    target = await UdpTransportTarget.create(address, timeout=timeout, retries=retries)

    # set_cmd is a coroutine function that directly returns the result tuple
    error_indication, error_status, error_index, result_var_binds = await set_cmd(
        engine, auth, target, context, *var_binds
    )
    return error_indication, error_status, error_index, result_var_binds


def _raise_on_error(error_indication: Any, error_status: Any, error_index: Any) -> None:
    """Raise SnmpSyncError if SNMP operation reported an error.

    Args:
        error_indication: Transport/engine error (if present, operation failed)
        error_status: PDU error status (e.g., noAccess, notWritable)
        error_index: Index of the variable binding that caused the error

    Raises:
        SnmpSyncError: If error_indication or error_status is set.
    """
    if error_indication:
        raise SnmpSyncError(f"SNMP error: {error_indication}")

    # error_status is truthy when there is a PDU-level error
    if error_status:
        idx = int(error_index) if error_index else 0
        raise SnmpSyncError(f"{error_status.prettyPrint()} at varbind index {idx}")


def get_sync(
    engine: SnmpEngine,
    auth: Union[CommunityData, UsmUserData],
    address: Tuple[str, int],
    var_binds: VarBinds,
    timeout: float = 1.0,
    retries: int = 5,
    context: Optional[ContextData] = None,
) -> Tuple[ObjectType, ...]:
    """Synchronous SNMP GET operation.

    Blocks until the GET response is received and processed.
    Handles async UdpTransportTarget creation internally.

    Args:
        engine: SNMP engine instance
        auth: Authentication (CommunityData for v2c, UsmUserData for v3)
        address: Tuple of (hostname, port) for SNMP agent, e.g. ('192.168.1.1', 161)
        var_binds: Variable bindings to retrieve
        timeout: Timeout in seconds (default 1.0)
        retries: Number of retries (default 5)
        context: Optional SNMP context (defaults to ContextData())

    Returns:
        Tuple of ObjectType results from the GET operation.

    Raises:
        SnmpSyncError: If the operation fails at transport or PDU level.

    Example:
        >>> engine = SnmpEngine()
        >>> auth = CommunityData('public', mpModel=1)
        >>> oid = ObjectType(make_oid('1.3.6.1.2.1.1.1.0'))
        >>> result = get_sync(engine, auth, ('192.168.1.1', 161), [oid])
    """
    error_indication, error_status, error_index, result_var_binds = run_sync(
        _get_async(engine, auth, address, var_binds, timeout=timeout, retries=retries, context=context)
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
) -> Tuple[ObjectType, ...]:
    """Synchronous SNMP SET operation.

    Blocks until the SET response is received and processed.
    Handles async UdpTransportTarget creation internally.

    Args:
        engine: SNMP engine instance
        auth: Authentication (CommunityData for v2c, UsmUserData for v3)
        address: Tuple of (hostname, port) for SNMP agent, e.g. ('192.168.1.1', 161)
        var_binds: Variable bindings to set
        timeout: Timeout in seconds (default 1.0)
        retries: Number of retries (default 5)
        context: Optional SNMP context (defaults to ContextData())

    Returns:
        Tuple of ObjectType results from the SET operation.

    Raises:
        SnmpSyncError: If the operation fails at transport or PDU level.

    Example:
        >>> engine = SnmpEngine()
        >>> auth = CommunityData('private', mpModel=1)
        >>> oid = ObjectType(make_oid('1.3.6.1.2.1.1.4.0'), 'admin@example.com')
        >>> result = set_sync(engine, auth, ('192.168.1.1', 161), [oid])
    """
    error_indication, error_status, error_index, result_var_binds = run_sync(
        _set_async(engine, auth, address, var_binds, timeout=timeout, retries=retries, context=context)
    )
    _raise_on_error(error_indication, error_status, error_index)
    return tuple(result_var_binds)


@dataclass(slots=True)
class SyncSnmpClient:
    """
    Convenience client that holds engine/auth/address/timeout/retries/context and exposes get/set.

    Example:
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
    auth: Union[CommunityData, UsmUserData]
    address: Tuple[str, int]
    timeout: float = 1.0
    retries: int = 5
    context: ContextData = ContextData()

    def get(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        return get_sync(
            engine=self.engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )

    def set(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        return set_sync(
            engine=self.engine,
            auth=self.auth,
            address=self.address,
            var_binds=var_binds,
            timeout=self.timeout,
            retries=self.retries,
            context=self.context,
        )


def make_oid(oid: str) -> ObjectIdentity:
    """
    Small helper so callers can do make_oid("1.3.6.1.2.1.1.5.0").
    """
    return ObjectIdentity(oid)


# Optional: allow explicit shutdown of the background loop if your process needs it.
def shutdown_sync_wrapper() -> None:
    global _GLOBAL_LOOP_THREAD
    with _GLOBAL_LOCK:
        if _GLOBAL_LOOP_THREAD is not None:
            _GLOBAL_LOOP_THREAD.stop()
            _GLOBAL_LOOP_THREAD = None


if __name__ == "__main__":
    # Minimal example (SNMPv2c GET sysDescr.0)
    engine_ = SnmpEngine()
    auth_ = CommunityData("public", mpModel=1)
    address_ = ("127.0.0.1", 161)

    client = SyncSnmpClient(engine=engine_, auth=auth_, address=address_, timeout=1.0, retries=1)

    sys_descr = ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
    try:
        result = client.get(sys_descr)
        for vb in result:
            print(vb.prettyPrint())
    finally:
        shutdown_sync_wrapper()