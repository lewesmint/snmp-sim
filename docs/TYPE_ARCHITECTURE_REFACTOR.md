# Type System Architecture Refactoring

## Problem
Current implementation hardcodes many derived SNMP types that should be resolved from the type registry.

## ASN.1 Base Types (The Only Hardcoded Types)
According to SNMPv2-SMI (RFC 2578), only 3 base ASN.1 types exist:
1. **INTEGER** - Base integer type
2. **OCTET STRING** - Base string/binary type  
3. **OBJECT IDENTIFIER** - OID type

## Application Types (Should Come from Type Registry)
These are **NOT** base types - they're application-defined wrappers:
- Integer32 - [APPLICATION 0] tagged INTEGER
- IpAddress - [APPLICATION 0] OCTET STRING(SIZE(4))
- Counter32 - [APPLICATION 1] INTEGER (wraps)
- Gauge32 - [APPLICATION 2] INTEGER (doesn't wrap)
- Unsigned32 - [APPLICATION 2] INTEGER (same as Gauge32)
- TimeTicks - [APPLICATION 3] INTEGER (hundredths of seconds)
- Opaque - [APPLICATION 4] OCTET STRING
- Counter64 - [APPLICATION 6] INTEGER (64-bit)

## BITS Pseudo-Type
BITS is a special pseudo-type in OBJECT-TYPE SYNTAX, not a base type.

## All TEXTUAL-CONVENTIONs
Every TEXTUAL-CONVENTION (DisplayString, DateAndTime, RowStatus, etc.) derives from one of the 3 base types or application types.

## Current Issues

### 1. **snmp_type_initializer.py (Lines 42-49)**
```python
if base_type in ('Integer32', 'Integer', 'Counter32', 'Gauge32', 'Unsigned32', 'TimeTicks'):
    return 0
if base_type in ('OctetString', 'DisplayString'):
    return ''
if base_type == 'ObjectIdentifier':
    return '0.0'
```
**Problem**: Hardcodes application types and textual conventions.
**Fix**: Only handle INTEGER, OCTET STRING, OBJECT IDENTIFIER. Look up everything else in type registry.

### 2. **snmp_agent.py (Line 293)**
```python
if base_type in ["Integer32", "Integer", "Gauge32", "Counter32", "Counter64", "TimeTicks", "Unsigned32"]:
```
**Problem**: Hardcodes application types.
**Fix**: Resolve from type registry, check base ASN.1 type.

### 3. **Type Registry Structure**
Current type registry should store:
- **base_asn1_type**: One of INTEGER, OCTET STRING, or OBJECT IDENTIFIER
- **application_tag**: For application types (0-6)
- **syntax**: Full type name (Integer32, IpAddress, etc.)
- **encoding_rules**: How to encode/decode (wrapping, constraints, etc.)

## Proposed Refactoring

### Phase 1: Enhance Type Registry
Add base ASN.1 type information to all types:
```python
{
  "Integer32": {
    "base_asn1_type": "INTEGER",
    "application_tag": 0,
    "constraints": {"range": [-2147483648, 2147483647]},
    ...
  },
  "IpAddress": {
    "base_asn1_type": "OCTET STRING",
    "application_tag": 0,
    "constraints": {"size": 4},
    ...
  },
  "DisplayString": {
    "base_asn1_type": "OCTET STRING",
    "parent_type": "OCTET STRING",
    "constraints": {"size": [0, 255]},
    ...
  }
}
```

### Phase 2: Create Base Type Handler
```python
class BaseTypeHandler:
    """Handles only the 3 base ASN.1 types"""
    
    BASE_TYPES = {
        'INTEGER': int,
        'OCTET STRING': bytes,
        'OBJECT IDENTIFIER': tuple
    }
    
    def get_base_type(self, type_name: str) -> str:
        """Resolve any type to its base ASN.1 type"""
        type_info = self.type_registry.get(type_name)
        return type_info.get('base_asn1_type', 'INTEGER')
    
    def create_value(self, type_name: str, value: Any) -> Any:
        """Create value using base type + registry rules"""
        base_type = self.get_base_type(type_name)
        # Apply application tag, constraints, etc. from registry
```

### Phase 3: Update Type Initializer
Remove all hardcoded type names except base types:
```python
def get_default_value(self, type_name: str, type_info: Dict[str, Any]) -> Any:
    base_asn1_type = type_info.get('base_asn1_type', 'INTEGER')
    
    if base_asn1_type == 'INTEGER':
        if type_info.get('enums'):
            return type_info['enums'][0]['value']
        return 0
    elif base_asn1_type == 'OCTET STRING':
        return b'' if type_info.get('binary') else ''
    elif base_asn1_type == 'OBJECT IDENTIFIER':
        return (0, 0)
    else:
        raise ValueError(f"Unknown base type: {base_asn1_type}")
```

### Phase 4: Update Type Recorder
Enhance type recording to capture base ASN.1 type:
```python
def _record_type(self, symbol_name: str, symbol_obj: Any) -> None:
    entry = {
        "name": symbol_name,
        "syntax": self._get_syntax(symbol_obj),
        "base_asn1_type": self._get_base_asn1_type(symbol_obj),  # NEW
        "application_tag": self._get_application_tag(symbol_obj),  # NEW
        ...
    }
```

## Benefits
1. **Correctness**: Aligns with SMI specification
2. **Extensibility**: New types automatically supported via type registry
3. **Maintainability**: No hardcoded type lists scattered through code
4. **Flexibility**: Easy to add custom TEXTUAL-CONVENTIONs
5. **Clarity**: Clear separation between base types and derived types

## Migration Path
1. ✅ Document current architecture issues (this file)
2. Enhance type_recorder.py to capture base_asn1_type
3. Rebuild type registry with new information
4. Create BaseTypeHandler class
5. Update snmp_type_initializer.py to use registry
6. Update snmp_agent.py to use registry
7. Remove all hardcoded type lists
8. Add tests verifying base type resolution
9. Update documentation

## Files to Modify
- `app/type_recorder.py` - Add base_asn1_type capture
- `app/type_registry.py` - Enhance registry structure
- `app/snmp_type_initializer.py` - Remove hardcoded types
- `app/snmp_agent.py` - Use registry for type resolution
- `app/base_type_handler.py` - NEW: Handle base type operations
- `data/types.json` - Regenerate with new structure
- Tests - Add base type resolution tests
