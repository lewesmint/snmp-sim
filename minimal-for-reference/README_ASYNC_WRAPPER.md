# Async Wrapper: Synchronous Interface to PySNMP 7.x Async HLAPI

A thin synchronous wrapper around PySNMP 7.x's asyncio-based HLAPI, making it easy to use async SNMP operations from synchronous code.

## Features

- **Simple API**: `get_sync()` and `set_sync()` functions mirror PySNMP's async interface
- **Thread-safe**: Automatically handles running from both sync and async contexts
- **Transparent threading**: Uses background event loop when called from async code to avoid blocking
- **Error handling**: Proper exception raising for SNMP errors and timeouts
- **Convenience class**: `SyncSnmpClient` for repeated operations

## Installation

Requires PySNMP 7.x:

```bash
pip install pysnmp
```

## Quick Start

### Basic GET

```python
from async_wrapper import get_sync, make_oid
from pysnmp.hlapi.asyncio import SnmpEngine, ObjectType, UdpTransportTarget
from pysnmp.hlapi import CommunityData

engine = SnmpEngine()
auth = CommunityData("public", mpModel=1)  # SNMPv2c
target = UdpTransportTarget(("127.0.0.1", 161), timeout=1.0)

oid = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))  # sysDescr.0
result = get_sync(engine, auth, target, [oid])

for vb in result:
    print(vb.prettyPrint())
```

### Using the Client Class

```python
from async_wrapper import SyncSnmpClient, make_oid
from pysnmp.hlapi.asyncio import SnmpEngine, ObjectType, UdpTransportTarget
from pysnmp.hlapi import CommunityData

client = SyncSnmpClient(
    engine=SnmpEngine(),
    auth=CommunityData("public", mpModel=1),
    target=UdpTransportTarget(("127.0.0.1", 161), timeout=1.0),
)

oid = ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))
result = client.get(oid)
```

### From Async Context

The wrapper automatically detects when it's called from an async context and uses a background thread's event loop:

```python
import asyncio
from async_wrapper import get_sync, make_oid

async def main():
    # Even though main() is async, get_sync() will work and not block the loop
    result = get_sync(engine, auth, target, [oid])
    print(result)

asyncio.run(main())
```

## API Reference

### Functions

#### `get_sync(engine, auth, target, var_binds, context=None) -> Tuple[ObjectType, ...]`

Synchronous SNMP GET operation.

**Parameters:**
- `engine`: SnmpEngine instance
- `auth`: CommunityData (SNMPv2c) or UsmUserData (SNMPv3)
- `target`: UdpTransportTarget configuration
- `var_binds`: Sequence of ObjectType instances to retrieve
- `context`: Optional ContextData (defaults to ContextData())

**Returns:** Tuple of ObjectType results

**Raises:** SnmpSyncError on SNMP errors or timeouts

#### `set_sync(engine, auth, target, var_binds, context=None) -> Tuple[ObjectType, ...]`

Synchronous SNMP SET operation.

Same parameters and behavior as `get_sync()`.

#### `run_sync(coro) -> Any`

Low-level function to run any coroutine synchronously.

**Parameters:**
- `coro`: The coroutine to execute

**Returns:** Result of the coroutine

#### `make_oid(oid_string: str) -> ObjectIdentity`

Helper to create ObjectIdentity from OID string.

```python
oid = make_oid("1.3.6.1.2.1.1.1.0")
```

#### `shutdown_sync_wrapper() -> None`

Explicitly shut down the background event loop thread.

Call this when you want to clean up resources in long-running programs.

### Classes

#### `SyncSnmpClient`

Convenience class holding engine, auth, target, and context.

```python
@dataclass
class SyncSnmpClient:
    engine: SnmpEngine
    auth: Union[CommunityData, UsmUserData]
    target: UdpTransportTarget
    context: ContextData = ContextData()
    
    def get(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Perform GET operation."""
        
    def set(self, *var_binds: ObjectType) -> Tuple[ObjectType, ...]:
        """Perform SET operation."""
```

#### `SnmpSyncError`

Exception raised on SNMP operation failures.

## Thread Safety & Event Loop Handling

The wrapper handles two scenarios:

### 1. Called from Synchronous Context (Normal Case)

```python
# Regular Python script
result = get_sync(...)  # Uses asyncio.run() internally
```

**What happens:**
- No event loop is running in the current thread
- `asyncio.run()` creates a new loop, runs the coroutine, and closes the loop
- Fully synchronous behavior from the caller's perspective

### 2. Called from Async Context

```python
async def my_async_function():
    result = get_sync(...)  # Still works!
```

**What happens:**
- An event loop is already running in the current thread
- Calling `asyncio.run()` would fail (can't create nested loops)
- Instead, the wrapper detects this and schedules the coroutine on a background thread's event loop
- Uses `asyncio.run_coroutine_threadsafe()` for safe inter-thread communication
- Returns when the background task completes

This allows `get_sync()` and `set_sync()` to be truly synchronous from the caller's perspective, even when called from async code.

## Error Handling

The wrapper distinguishes between two types of SNMP errors:

### Transport Errors

Network problems, timeouts, no route to host, etc.

```python
try:
    result = get_sync(engine, auth, target, [oid])
except SnmpSyncError as e:
    print(f"Network error: {e}")
```

### PDU Errors

SNMP protocol-level errors (noAccess, notWritable, no such object, etc.)

```python
try:
    result = set_sync(engine, auth, target, [oid_and_value])
except SnmpSyncError as e:
    # e.args[0] contains something like:
    # "notWritable at varbind index 0"
    print(f"SNMP error: {e}")
```

## Testing

Run the test suite:

```bash
cd minimal-for-reference
python -m pytest test_async_wrapper.py -v
```

Expected output: 17 passed

## Examples

See `example_usage.py` for complete working examples including:

1. Basic GET operation
2. Basic SET operation  
3. Using the SyncSnmpClient class
4. Calling from async context
5. Error handling

## Design Rationale

**Why not just use async/await?**

The wrapper is useful when:
- You have synchronous code that needs SNMP access
- You're integrating with libraries that expect sync interfaces
- You want a simpler API than dealing with asyncio directly
- You're prototyping/testing and don't need full async performance

**For production systems** that need high performance with many concurrent operations, using PySNMP's async API directly is recommended.

## Limitations

- Single GET/SET per call (not walking or bulk operations)
- Requires all PySNMP 7.x HLAPI objects be provided explicitly
- Background loop thread persists for process lifetime (or until `shutdown_sync_wrapper()`)

## Files

- `async_wrapper.py` - Main wrapper implementation
- `test_async_wrapper.py` - Comprehensive unit tests (17 tests, all passing)
- `example_usage.py` - Usage examples

## Future Enhancements

Potential additions:
- `walk_sync()` for SNMP table walks
- `bulk_get_sync()` for bulk operations
- Context manager interface for automatic cleanup
- Type stubs (.pyi) for better IDE support
