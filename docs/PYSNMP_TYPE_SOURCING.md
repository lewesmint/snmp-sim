# PySNMP Type Sourcing - Definitive Guide

## Summary

This document clarifies where different SNMP types can be sourced from in PySNMP, based on empirical testing.

## Two Categories of Types

### 1. Base RFC 1902 Types (Direct Import)

**Source:** `pysnmp.proto.rfc1902`

These are the fundamental SNMP types defined in RFC 1902. They can be imported directly:

```python
from pysnmp.proto.rfc1902 import (
    OctetString, Integer32, Counter32, Counter64, Gauge32,
    IpAddress, TimeTicks, ObjectIdentifier, Unsigned32,
    Integer, Bits, Opaque, Null
)
```

**All of these are available:**
- `OctetString` - Byte/text strings
- `Integer32` - 32-bit signed integer
- `Counter32` - 32-bit counter
- `Counter64` - 64-bit counter
- `Gauge32` - 32-bit gauge
- `IpAddress` - IPv4 address
- `TimeTicks` - Time in hundredths of a second
- `ObjectIdentifier` - OID values
- `Unsigned32` - 32-bit unsigned integer
- `Integer` - Basic integer
- `Bits` - Bit strings
- `Opaque` - Opaque data
- `Null` - Null value

### 2. TEXTUAL-CONVENTIONs (MibBuilder Required)

**Source:** MIB modules via `MibBuilder.import_symbols()`

These are derived types defined in MIB modules (primarily SNMPv2-TC). They **cannot** be imported from `pysnmp.proto.rfc1902`.

```python
from pysnmp.smi import builder

mib_builder = builder.MibBuilder()
mib_builder.load_modules('SNMPv2-TC')

DisplayString = mib_builder.import_symbols('SNMPv2-TC', 'DisplayString')[0]
PhysAddress = mib_builder.import_symbols('SNMPv2-TC', 'PhysAddress')[0]
```

**Common TEXTUAL-CONVENTIONs from SNMPv2-TC:**
- `DisplayString` - Human-readable text (subclass of OctetString)
- `PhysAddress` - Physical address (MAC address, etc.)
- `MacAddress` - 6-octet MAC address
- `TruthValue` - Boolean (1=true, 2=false)
- `TimeStamp` - sysUpTime value
- `AutonomousType` - OID reference
- `RowStatus` - Table row status
- `StorageType` - Storage type for rows
- `TestAndIncr` - Test-and-increment
- `TimeInterval` - Time interval in hundredths
- `DateAndTime` - Date and time encoding

## Key Insight: DisplayString is a Subclass

```python
DisplayString.__mro__
# (<class 'DisplayString'>, 
#  <class 'TextualConvention'>, 
#  <class 'pysnmp.proto.rfc1902.OctetString'>,  # ← Base type!
#  ...)

issubclass(DisplayString, OctetString)  # True
```

**This means:**
- `DisplayString` is ultimately an `OctetString` with additional constraints
- For value creation, you can often use `OctetString` as a fallback
- But for proper MIB compliance, use the actual `DisplayString` type

## Recommended Approach in Code

### For Base Types (Simple)

```python
from pysnmp.proto import rfc1902

# Direct, simple, type-safe
value = rfc1902.OctetString("test")
counter = rfc1902.Counter32(100)
```

### For TEXTUAL-CONVENTIONs (Requires MibBuilder)

```python
def get_type_class(type_name: str, mib_builder):
    """Get SNMP type class, trying MibBuilder first, then rfc1902."""
    
    # Try MibBuilder for TEXTUAL-CONVENTIONs
    for module in ['SNMPv2-TC', 'SNMPv2-SMI', 'SNMPv2-CONF']:
        try:
            return mib_builder.import_symbols(module, type_name)[0]
        except Exception:
            continue
    
    # Fallback to rfc1902 for base types
    from pysnmp.proto import rfc1902
    type_class = getattr(rfc1902, type_name, None)
    if type_class:
        return type_class
    
    # Not found
    raise ValueError(f"Type {type_name} not found")
```

## What About pysnmp.smi.rfc1902?

`pysnmp.smi.rfc1902` exists but contains **helper classes**, not type classes:
- `ObjectType`, `ObjectIdentity`, `NotificationType`
- `MibViewController`
- Not useful for getting type classes like `DisplayString`

## Testing

Run `tests/misc/test_pysnmp_type_sources.py` to verify type availability:

```bash
python -m pytest tests/misc/test_pysnmp_type_sources.py -v -s
```

## Implementation in Code

### ✅ Correct Approach (used in `app/base_type_handler.py`)

```python
def _get_pysnmp_type_class(type_name: str, mib_builder) -> Optional[Any]:
    """Get PySNMP type class, trying MibBuilder first, then rfc1902."""

    # Try MibBuilder FIRST (handles both base types and TEXTUAL-CONVENTIONs)
    for module in ["SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"]:
        try:
            return mib_builder.import_symbols(module, type_name)[0]
        except Exception:
            continue

    # Fallback to rfc1902 (works for base types, returns None for TEXTUAL-CONVENTIONs)
    try:
        from pysnmp.proto import rfc1902
        return getattr(rfc1902, type_name, None)
    except Exception:
        pass

    return None
```

**Why this works:**
- MibBuilder lookup succeeds for both base types AND TEXTUAL-CONVENTIONs
- rfc1902 fallback succeeds for base types (Integer32, OctetString, etc.)
- rfc1902 fallback returns `None` for TEXTUAL-CONVENTIONs (DisplayString, etc.)
- Caller handles `None` appropriately (falls back to base type creation)

## PySNMP Source Code Analysis

### Where DisplayString is Defined

**File:** `pysnmp/smi/mibs/SNMPv2-TC.py`

```python
class DisplayString(TextualConvention, OctetString):
    status = "current"
    displayHint = "255a"
    subtypeSpec = OctetString.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueSizeConstraint(0, 255),
    )
```

**Exported from SNMPv2-TC:**
```python
mibBuilder.export_symbols(
    "SNMPv2-TC",
    **{"DisplayString": DisplayString,
       "PhysAddress": PhysAddress,
       "MacAddress": MacAddress,
       "TruthValue": TruthValue,
       # ... and more TEXTUAL-CONVENTIONs
    }
)
```

### What's in pysnmp.proto.rfc1902

**File:** `pysnmp/proto/rfc1902.py`

Contains only base RFC 1902 types:
- `class OctetString(univ.OctetString)` ✓
- `class IpAddress(OctetString)` ✓
- `class Opaque(univ.OctetString)` ✓
- `class Bits(OctetString)` ✓
- `class Integer32`, `class Counter32`, etc. ✓

**Does NOT contain:**
- `DisplayString` ✗ (defined in SNMPv2-TC MIB)
- `PhysAddress` ✗ (defined in SNMPv2-TC MIB)
- `MacAddress` ✗ (defined in SNMPv2-TC MIB)
- Any other TEXTUAL-CONVENTIONs ✗

## References

- RFC 1902: Structure of Management Information for SNMPv2
- PySNMP Documentation: https://pysnmp.com/
- Test file: `tests/misc/test_pysnmp_type_sources.py`
- PySNMP source: `pysnmp/proto/rfc1902.py` (base types)
- PySNMP source: `pysnmp/smi/mibs/SNMPv2-TC.py` (TEXTUAL-CONVENTIONs)

