# PySnmp v7+ Type Imports from pysnmp.proto.rfc1902

## Overview

PySnmp v7+ provides direct access to SNMP type classes through `pysnmp.proto.rfc1902`. This module contains all the standard SNMP types defined in RFC 1902, making it straightforward to construct SNMP values without awkward workarounds or dynamic type resolution.

## Available Types

All of these types can be imported directly from `pysnmp.proto.rfc1902`:

- **Integer Types**
  - `Integer` - Basic integer
  - `Integer32` - 32-bit signed integer (-2^31 to 2^31-1)
  - `Gauge32` - 32-bit unsigned integer (0 to 2^32-1)
  - `Counter32` - 32-bit counter (monotonically increasing)
  - `Counter64` - 64-bit counter
  - `Unsigned32` - 32-bit unsigned integer

- **String/Data Types**
  - `OctetString` - Byte string (most common for text and binary data)
  - `Opaque` - Opaque data (rarely used)
  - `Bits` - Bit string

- **Network Types**
  - `IpAddress` - IPv4 address
  - `TimeTicks` - Time in hundredths of a second

- **Object Identifier Types**
  - `ObjectIdentifier` - OID value
  - `ObjectName` - OID reference (type alias)

- **Syntax Base Types**
  - `Null` - Null value
  - `SimpleSyntax` - Base class for simple types
  - `ObjectSyntax` - Base class for object types
  - `ApplicationSyntax` - Base class for application types

## Usage Examples

### Basic Type Construction

```python
from pysnmp.proto.rfc1902 import (
    OctetString, Integer32, Counter32, Gauge32, 
    IpAddress, TimeTicks, ObjectIdentifier
)

# String values
hostname = OctetString("example.com")
description = OctetString("SNMP Agent")

# Integer values
sys_uptime = TimeTicks(100000)  # 100,000 hundredths of a second
packet_count = Counter32(1024)
cpu_usage = Gauge32(75)
interface_index = Integer32(1)
port_number = Integer32(161)

# Network address
agent_ip = IpAddress("192.168.1.1")

# Object identifier
oid_value = ObjectIdentifier("1.3.6.1.2.1.1.1.0")
```

### In SNMP Operations

#### GET Operations
```python
from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd
)
from pysnmp.proto.rfc1902 import OctetString

async def snmp_get():
    iterator = get_cmd(
        SnmpEngine(),
        CommunityData('public'),
        await UdpTransportTarget.create(('192.168.1.1', 161)),
        ContextData(),
        ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0'))
    )
    return await iterator.__anext__()
```

#### SET Operations
```python
from pysnmp.hlapi.asyncio import set_cmd
from pysnmp.proto.rfc1902 import OctetString

async def snmp_set():
    new_value = OctetString("New System Description")
    iterator = set_cmd(
        SnmpEngine(),
        CommunityData('private'),
        await UdpTransportTarget.create(('192.168.1.1', 161)),
        ContextData(),
        ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0'), new_value)
    )
    return await iterator.__anext__()
```

#### Trap/Notification Sending
```python
from pysnmp.hlapi.asyncio import send_notification
from pysnmp.proto.rfc1902 import OctetString, Integer32

async def send_trap():
    error_indication, _, _, _ = await send_notification(
        SnmpEngine(),
        CommunityData('public'),
        await UdpTransportTarget.create(('192.168.1.254', 162)),
        ContextData(),
        'trap',
        ObjectType(
            ObjectIdentity('1.3.6.1.6.3.1.1.5.1'),  # coldStart trap OID
            OctetString("Trap details")
        )
    )
    return error_indication
```

## Benefits Over Alternative Approaches

### Problem: Dynamic Type Resolution
```python
# ❌ Old/awkward approach - dynamic type lookup
type_map = {'OctetString': OctetString, 'Integer32': Integer32}
type_class = type_map.get(type_name)
value = type_class(data)  # Creates type at runtime
```

### Solution: Direct Imports
```python
# ✅ Clean approach - direct import
from pysnmp.proto.rfc1902 import OctetString, Integer32

value = OctetString(data)  # Type known at parse time
integer_val = Integer32(42)  # Type checker sees full type info
```

## Type Checking and IDE Support

Direct imports provide excellent IDE support and static type checking:

```python
from pysnmp.proto.rfc1902 import OctetString

# Type checker knows OctetString is a class
value: OctetString = OctetString("test")

# IDE autocomplete works for methods on OctetString
# Mypy can verify the correct usage
```

## Migration Guide

### Before (Indirect/Awkward)
```python
# Type retrieved from some registry or string lookup
type_class = get_type_from_registry("OctetString")
value = type_class("some data")  # Type unknown at parse time
```

### After (Direct Import)
```python
from pysnmp.proto.rfc1902 import OctetString

value = OctetString("some data")  # Type checked at parse time
```

## Projects Using This Pattern

This project now uses direct imports in:
- `minimal-for-reference/table_agent.py` - Full implementation example
- `app/cli_trap_sender.py` - CLI type handling
- `ui/mib_browser.py` - GUI SNMP operations

## Refactoring Opportunities

Areas in the codebase that could benefit from this approach:

1. **Type Registry** (`app/type_registry.py`) - Could use direct imports instead of dynamic string-based lookups for common types

2. **Default Value Plugins** (`app/default_value_plugins.py`) - Could import types directly instead of type lookup tables

3. **Type Initialization** (`app/type_recorder.py`) - Direct imports would improve type safety

4. **MIB Object Generation** (`app/mib_object.py`) - Type construction could be more explicit

## Performance Implications

Using direct imports has **no performance penalty** and may have slight benefits:
- Type checking happens at parse time, not runtime
- No dictionary lookups needed for common types
- More straightforward bytecode generation

## References

- [RFC 1902 - Structure of Management Information for version 2 of SNMP](https://tools.ietf.org/html/rfc1902)
- PySnmp Documentation: https://pysnmp.com/
- PySnmp v7 Migration Guide
