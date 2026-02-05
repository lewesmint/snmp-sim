# Default Value Fixes - Summary

## Issues Fixed

### 1. **Invalid Enum Values Returning 0**
**Problem**: Fields like `ifAdminStatus`, `ifOperStatus`, `hrDeviceStatus`, etc. were returning 0 as the default, but 0 is not a valid enum value. Valid values are 1 (up), 2 (down), 3 (testing).

**Files Modified**:
- [plugins/basic_types.py](plugins/basic_types.py) - Added `_get_first_enum_value()` helper and improved enum handling in `get_default_value()`
- [app/generator.py](app/generator.py) - Modified `_extract_mib_info()` to always extract enums from compiled MIB syntax objects

**Changes**:
- Extract enums directly from compiled MIB syntax objects using `_extract_type_info()`
- Updated `_get_first_enum_value()` to handle both dict format (`{'name': value}`) and list format (`[{'value': v, 'name': n}]`)
- Enums are now properly sorted and the first (lowest) valid enum value is returned
- For `ifAdminStatus`/`ifOperStatus`: Now returns 1 (up) instead of 0

### 2. **MAC Address Returning ASCII "unset"**
**Problem**: Physical address fields like `ifPhysAddress` were returning the string "unset" encoded as ASCII bytes `75:6e:73:65:74`, which confuses network managers expecting real MAC addresses.

**Files Modified**:
- [plugins/basic_types.py](plugins/basic_types.py)

**Changes**:
- MAC/physical address fields now return proper null MAC: `[0x00, 0x00, 0x00, 0x00, 0x00, 0x00]`
- Checks both type name and symbol name for MAC-like fields
- Applies to: `PhysAddress`, `MacAddress`, `ifPhysAddress`, `ipNetMediaPhysAddress`, `atPhysAddress`

### 3. **Unstable snmpEngineID**
**Problem**: `snmpEngineID` was changing on each request, but it should be stable for a given agent instance as it's used in SNMPv3 security associations.

**Files Created**:
- [plugins/snmp_framework.py](plugins/snmp_framework.py) - New plugin for SNMP Framework MIB objects

**Changes**:
- Generates snmpEngineID using RFC 3414 format with stable prefix: `0x80 0x00 0x01 0x86 0x9f` (private enterprise)
- Suffix is deterministic based on system hostname + SHA256 hash with fixed salt
- Caches the generated ID in process memory so it's stable for the lifetime of the agent
- Same hostname will always produce the same engine ID

## How the Fixes Work

### Enum Extraction Flow:
1. Generator loads compiled MIB using pysnmp
2. For each symbol, extracts syntax object which contains `namedValues`
3. Calls `_extract_type_info()` to convert namedValues to standardized format
4. Plugin receives enriched `type_info` dict with `enums` key
5. `_get_first_enum_value()` returns first (lowest) valid enum value

### Plugin Registration:
- `basic_types` plugin loaded by default
- `snmp_framework` plugin auto-discovered and loaded by `plugin_loader.py`

## Testing

To regenerate schema files with these fixes:
```bash
python3 -c "
from app.generator import BehaviourGenerator
gen = BehaviourGenerator('mock-behaviour', load_default_plugins=True)
for mib in ['IF-MIB', 'HOST-RESOURCES-MIB', 'SNMPv2-MIB']:
    result = gen.generate(f'compiled-mibs/{mib}.py', mib, force_regenerate=True)
    print(f'Generated: {result}')
"
```

## Before/After Examples

### ifAdminStatus:
- **Before**: 0 (invalid)
- **After**: 1 (up - valid first enum value)

### ifPhysAddress:
- **Before**: "unset" → ASCII bytes `75:6e:73:65:74`
- **After**: `[0, 0, 0, 0, 0, 0]` (proper null MAC)

### snmpEngineID:
- **Before**: Random/changing value
- **After**: Stable value based on hostname (e.g., `80 00 01 86 9f fb 08 56 95 ce 88 04 6e f4 73 f4`)
