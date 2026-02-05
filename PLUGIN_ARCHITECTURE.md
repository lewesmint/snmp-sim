# Plugin Architecture Documentation

## Overview

The plugin system consists of two separate but complementary layers:

### 1. Default Value Plugins (`app/default_value_plugins.py`)

**Purpose**: Generate sensible default values during MIB-to-JSON schema generation

**Current Plugins**:
- `plugins/basic_types.py` - Provides defaults for common SNMP types and specific OIDs

**How it works**:
1. When `BehaviourGenerator` creates a schema.json from compiled MIBs, it calls plugins to determine initial values
2. Plugins are registered via `@register_plugin('name')` decorator
3. Each plugin function receives: `type_info` (dict with type metadata) and `symbol_name` (OID name)
4. Plugin returns a default value or None if it doesn't handle that type
5. The returned value gets written to schema.json's `"initial"` field

**Example** (`plugins/basic_types.py`):
```python
@register_plugin('basic_types')
def get_default_value(type_info: TypeInfo, symbol_name: str) -> Any:
    if symbol_name == 'sysDescr':
        return 'Simple Python SNMP Agent'
    elif base_type in ('OctetString', 'DisplayString'):
        return 'unset'
    # ... etc
```

**Current Flow**:
```
MIB files 
  → Compiler (libsmi)
    → Python MIB modules
      → Generator reads types
        → Calls get_default_value() plugins
          → Writes schema.json with "initial" values
```

---

### 2. Type Converter Plugins (`plugins/type_converters.py`)

**Purpose**: Convert Python schema values to proper SNMP types at runtime when registering instances

**Current Plugins**:
- `plugins/date_and_time.py` - Converts string/"unset" to DateAndTime octets

**How it works**:
1. When `SNMPAgent._build_mib_symbols()` reads schema.json values, it calls type converters
2. Converters are registered via `register_type_converter('TypeName', converter_func)` in module init
3. Each converter function receives the raw value and returns converted value
4. Agent calls `convert_value(value, type_name)` to apply conversion
5. Converted value is then passed to PySNMP type constructor

**Example** (`plugins/date_and_time.py`):
```python
def _format_date_and_time(value):
    """Convert "unset" or string to 8-byte DateAndTime octets"""
    if value in [None, "unset", ""]:
        now = datetime.utcnow()
    # ... encode as octets
    return octets

register_type_converter('DateAndTime', _format_date_and_time)
```

**Current Flow**:
```
schema.json value (e.g., "unset")
  → Agent loads value
    → Calls convert_value(value, "DateAndTime")
      → Converter runs
        → Returns proper 8-byte octets
          → Passed to PySNMP OctetString constructor
            → Instance registered in MIB tree
```

---

## Current Implementation Status

### What Works
- ✅ Default value plugins generate initial schema values
- ✅ Type converters registered on module import
- ✅ DateAndTime values converted at instance creation time
- ✅ Both scalar and table column values are converted

### Import Chain
```python
# In app/snmp_agent.py
from plugins.type_converters import convert_value
import plugins.date_and_time  # Registers DateAndTime converter on import
```

### Design Questions for Review

1. **Plugin Discovery**: Currently plugins must be explicitly imported in `snmp_agent.py`. Should we auto-discover plugins from the `plugins/` directory instead?

2. **Plugin Scope**: 
   - Should default value plugins ALSO be available as runtime converters?
   - Or keep them strictly separated (generation-time vs runtime)?

3. **Plugin Configuration**:
   - Should plugins be configurable (e.g., timezone for DateAndTime)?
   - Should there be a plugin configuration file?

4. **Error Handling**:
   - Current converters silently fall back to defaults on error. Should this be logged more verbosely?
   - Should plugins raise exceptions vs returning defaults?

5. **Type Mapping**:
   - Should converters handle base types (e.g., "OctetString") in addition to TEXTUAL-CONVENTIONs (e.g., "DateAndTime")?
   - Currently only explicit type names trigger converters

---

## Files Involved

- `app/default_value_plugins.py` - Registry and loader for default value plugins
- `plugins/basic_types.py` - Default value plugin (existing)
- `plugins/type_converters.py` - NEW: Registry and loader for type converters
- `plugins/date_and_time.py` - NEW: DateAndTime type converter
- `app/snmp_agent.py` - Uses `convert_value()` when building instances
