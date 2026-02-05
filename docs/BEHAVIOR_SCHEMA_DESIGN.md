# Behavior JSON Schema Design

## Overview
This document defines the three-file architecture for SNMP agent simulation based on the type registry structure. The system uses separate files for schema definition, dynamic behaviors, and runtime state.

## Three-File Architecture

The system uses three separate JSON files for each MIB:

1. **schema.json** - MIB structure with OIDs, types, access, and **initial values** (static, generated from MIB)
2. **behavior.json** - Dynamic function assignments for computed values (user-defined, optional)
3. **values.json** - Current runtime values that override initial values (runtime state, modified during operation)

### Value Resolution Order

When the agent responds to an SNMP request, it resolves values in this order:

1. **Dynamic Function** - If `behavior.json` defines a dynamic_function (e.g., "uptime"), call that function
2. **Current Value** - If `values.json` has a value for this OID, use it
3. **Initial Value** - If `schema.json` has an initial value, use it
4. **Type Default** - Fall back to type default (should be avoided with good schema generation)

### Example: sysUpTime Resolution

```
Request: GET sysUpTime.0
Agent checks:
1. behavior.json → "sysUpTime": {"dynamic_function": "uptime"} → Call uptime plugin → Return 123456 ticks
```

### Example: sysDescr Resolution

```
Request: GET sysDescr.0
Agent checks:
1. behavior.json → no entry (not dynamic)
2. values.json → "sysDescr": {"value": "Modified System"} → Return "Modified System"
```

### Example: New Scalar Resolution

```
Request: GET myCustomOid.0
Agent checks:
1. behavior.json → no entry
2. values.json → no entry
3. schema.json → "myCustomOid": {"initial": "Default Value"} → Return "Default Value"
```

## Type Registry Structure (Source of Truth)

The type registry (`data/types.json`) provides canonical type information:

```json
{
  "TypeName": {
    "base_type": "Integer32|OctetString|ObjectIdentifier|etc",
    "display_hint": "formatting string or null",
    "size": {
      "type": "range|set",
      "min": 0,
   File Format Specifications

### 1. schema.json - MIB Structure and Initial Values

Contains the complete MIB structure with metadata from the type registry. This file is generated from compiled MIBs.

**Scalar Objects:**

```json
{
  "scalars": {
    "sysDescr": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 1, 0],
      "type": "DisplayString",
      "access": "read-only",
      "initial": "Simple Python SNMP Agent",
      "metadata": {
        "constraints": [
          {"type": "ValueSizeConstraint", "min": 0, "max": 255}
        ],
        "display_hint": "255a"
      }
    },
    
    "sysObjectID": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 2, 0],
      "type": "ObjectIdentifier",
      "access": "read-only",
      "initial": [1, 3, 6, 1, 4, 1, 99999]
    },
    
    "sysUpTime": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 3, 0],
      "type": "TimeTicks",
      "access": "read-only",
      "initial": 0,
      "metadata": {
        "note": "This is computed dynamically, see behavior.jsonormation**: Only stores type name, not full type metadata
2. **No Constraint Validation**: Can't validate values against constraints
3. **No Enum Support**: Doesn't reference or validate enum values
4. **Basic Table Support**: Tables are flat, no proper row structure
5. **No Display Hint Usage**: Can't format values properly (e.g., MAC addresses, dates)

## Proposed Behavior JSON Schema

### Scalar Objects

```json
{
  "sysDescr": {
    "oid": [1, 3, 6, 1, 2, 1, 1, 1, 0],
    "type": "DisplayString",
    "access": "read-only",
    "value": "Simple Python SNMP Agent",
    "metadata": {
      "dynamic": null,          // or "uptime", "counter", etc.
      "constraints_checked": true,
      "display_hint": "255a"    // from type registry
    }
  },
  
  "sysObjectID": {
    "oid": [1, 3, 6, 1, 2, 1, 1, 2, 0],
    "type": "ObjectIdentifier",
    "access": "read-only",
    "value": [1, 3, 6, 1, 4, 1, 99999],  // OID as array
    "metadata": {
      "dynamic": null
    }
  },
  
  "ifAdminStatus": {
    "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 7],
    "type": "INTEGER",
    "access": "read-write",
    "value": 1,  // up(1)
    "metadata": {
      "enum": "up",           // human-readable enum name
      "valid_enums": {        // from type registry
        "1": "up",
        "2": "down",
        "3": "testing"
      }
    }
  }
}
```

### Table Objects
**Table Objects:**

```json
{
  "tables": {
    "ifTable": {
      "oid": [1, 3, 6, 1, 2, 1, 2, 2],
      "type": "SEQUENCE"
    },
    
    "ifEntry": {
      "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1],
      "type": "SEQUENCE",
      "indexes": ["ifIndex"],
      "augments": null,
      "columns": {
        "ifIndex": {
          "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
          "type": "InterfaceIndex",
          "access": "not-accessible",
          "is_index": true
        },
        "ifDescr": {
          "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
          "type": "DisplayString",
          "access": "read-only"
        },
        "ifType": {
          "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 3],
          "type": "IANAifType",
          "access": "read-only",
          "metadata": {
            "enums": {
              "1": "other",
              "6": "ethernetCsmacd",
              "24": "softwareLoopback"
            }
          }
        },
        "ifInOctets": {
          "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 10],
          "type": "Counter32",
          "access": "read-only",
          "metadata": {
            "note": "See behavior.json for counter increment"
          }
        }
      },
      "rows": [
        {
          "index": [1],
          "initial": {
            "ifDescr": "eth0",
            "ifType": 6,
            "ifMtu": 1500,
            "ifSpeed": 1000000000,
            "ifPhysAddress": [0x00, 0x11, 0x22, 0x33, 0x44, 0x55],
            "ifAdminStatus": 1,
            "ifOperStatus": 1,
            "ifInOctets": 0
          }
        },
        {
          "index": [2],
          "initial": {
            "ifDescr": "lo0",
            "ifType": 24,
            "ifMtu": 65536,
            "ifSpeed": 0,
            "ifPhysAddress": [],
            "ifAdminStatus": 1,
            "ifOperStatus": 1,
            "ifInOctets": 0
          }
        }
      ]
    }
  }
}
```

### 2. behavior.json - Dynamic Function Assignments

Contains mappings of OIDs to dynamic functions. This file is user-defined and optional.

```json
{
  "scalars": {
    "sysUpTime": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 3, 0],
      "dynamic_function": "uptime"
    }
  },
  "tables": {
    "ifEntry": {
      "columns": {
        "ifInOctets": {
          "dynamic_function": "counter_increment"
        },
        "ifOutOctets": {
          "dynamic_function": "counter_increment"
        }
      }
    }
  }
}
```

**Available Dynamic Functions:**
- `uptime` - Returns time since agent started in TimeTicks
- `counter_increment` - Auto-incrementing counter
- `random_gauge` - Random value within constraints
- `timestamp` - Current timestamp
- Custom plugin functions

### 3. values.json - Runtime State

Contains current values that differ from initial values. This file is created/updated during agent runtime.

```json
{
  "scalars": {
    "sysDescr": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 1, 0],
      "value": "Modified System Description",
      "last_modified": "2026-02-05T10:30:00Z"
    },
    "sysContact": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 4, 0],
      "value": "admin@example.com",
      "last_modified": "2026-02-05T09:15:00Z"
    }
  },
  "tables": {
    "ifEntry": {
      "rows": [
        {
          "index": [1],
          "values": {
            "ifAdminStatus": 2,
            "ifOperStatus": 2
          },
          "last_modified": "2026-02-05T10:45:00Z"
        }
      ]
    }
}
```

### Experimental Schema (foo_schema.json)

The current `foo_schema.json` is close but could be improved:

**Current:**
```json
{
  "mib": {
    "name": "MY-TEST-MIB",
    "tables": [
      {
        "name": "myTestTable",
        "oid": "1.3.6.1.4.1.99999.1.1",
        "columns": [...],
        "rows": [{"index": [1], "values": {...}}]
      }
    ]
  }
}
```Implementation Details

### Generator Updates

The `BehaviourGenerator` should:
1. Generate `{mib}_schema.json` with structure, types, and initial values
2. NOT generate behavior.json (user creates this manually as needed)
3. NOT generate values.json (created automatically by agent at runtime)

### Agent Value Resolution

```python
def get_value(oid):
    # 1. Check for dynamic function
    behavior = load_behavior_json()
    if oid in behavior and behavior[oid].get('dynamic_function'):
        func_name = behavior[oid]['dynamic_function']
        return call_dynamic_function(func_name, oid)
    
    # 2. Check for current value
    values = load_values_json()
    if oid in values:
        return values[oid]['value']
    
    # 3. Check for initial value
    schema = load_schema_json()
    if oid in schema and 'initial' in schema[oid]:
        return schema[oid]['initial']
    
    # 4. Fall back to type default
    type_naWorkflows

### Initial Setup

1. Compile MIB: `python -m app.cli_compile_mib IF-MIB.txt`
2. Generate schema: `python -m app.cli_mib_to_json compiled-mibs/IF-MIB.py`
   - Creates `mock-behaviour/IF-MIB/schema.json`
3. (Optional) Create `behavior.json` for dynamic values
4. Start agent - `values.json` created automatically on first run

### Adding Dynamic Behavior

```bash
# Edit mock-behaviour/SNMPv2-MIB/behavior.json
{
  "scalars": {
    "sysUpTime": {"dynamic_function": "uptime"}
  }
}
```

### Modifying Values at Runtime

```bash
# SNMP SET command
snmpset -v2c -c private localhost:1161 sysContact.0 s "newadmin@example.com"

# Agent updates values.json automatically:
{
  "scalars": {
    "sysContact": {
      "oid": [1, 3, 6, 1, 2, 1, 1, 4, 0],
      "value": "newadmin@example.com",
      "last_modified": "2026-02-05T11:00:00Z"
    }
  }
}
```

### Adding New Table Rows

Add to `values.json`:
```json
{
  "tables": {
    "ifEntry": {
      "rows": [
        {
          "index": [3],
          "initial": {
            "ifDescr": "wlan0",
            "ifType": 71,
            "ifMtu": 1500,
            "ifSpeed": 54000000
          }
        }
      ]
    }
  }
}
```

## Benefits of Three-File Architecture

1. **Separation of Concerns**
   - Schema = Structure (from MIB definition)
   - Behavior = Logic (dynamic computations)
   - Values = State (runtime modifications)

2. **Clean Regeneration**
   - Can regenerate schema.json from MIB without losing runtime state
   - Dynamic behaviors persist across schema updates

3. **Version Control Friendly**
   - schema.json: Generated, commit to repo
   - behavior.json: User-defined, commit to repo
   - values.json: Runtime state, add to .gitignore

4. **Easier Testing**
   - Test with different behavior configs without modifying schema
   - Reset state by deleting values.json

5. **Performance**
   - Only load schema once (immutable)
   - Cache dynamic function references
   - values.json is small and fast to update
    values.json
```
        "oid": [1, 3, 6, 1, 4, 1, 99999, 2, 1],
        "entry": {
          "name": "myTestEntry",
          "oid": [1, 3, 6, 1, 4, 1, 99999, 2, 1, 1],
          "indexes": ["myTestIndex"],
          "columns": {
            "myTestIndex": {
              "oid": [1, 3, 6, 1, 4, 1, 99999, 2, 1, 1, 1],
              "type": "Integer32",
              "access": "not-accessible",
              "is_index": true,
              "metadata": {
                "constraints": [
                  {"type": "ValueRangeConstraint", "min": 1, "max": 2147483647}
                ]
              }
            },
            "myTestName": {
              "oid": [1, 3, 6, 1, 4, 1, 99999, 2, 1, 1, 2],
              "type": "DisplayString",
              "access": "read-only",
              "is_index": false,
              "metadata": {
                "constraints": [
                  {"type": "ValueSizeConstraint", "min": 0, "max": 255}
                ]
              }
            }
          }
        },
        "rows": [
          {
            "index": [1],
            "values": {
              "myTestName": "First Entry",
              "myTestStatus": 1
            }
          }
        ]
      }
    }
  }
}
```

## Recommendations

### 1. Enhance Behavior Generator
- Load type registry at initialization
- Include full type metadata in generated behavior files
- Add validation helpers that check values against constraints
- Support enum name ↔ value mapping
- Use display hints for default value formatting

### 2. Schema Validation
Create a JSON schema validator that:
- Validates OID structure (array of integers)
- Checks values against type constraints
- Validates enum values
- Ensures table indexes are properly defined
- Validates AUGMENTS relationships

### 3. Value Helpers
Add utilities for:
- Converting enum names ↔ values using type registry
- Formatting values using display hints (MAC addresses, dates, etc.)
- Generating random but valid values within constraints
- Creating sensible default rows for tables

### 4. Migration Path
1. Update `BehaviourGenerator` to include type metadata
2. Add validator script to check existing behavior files
3. Create migration tool to upgrade old behavior files
4. Update documentation with examples

## Example Use Cases

### Creating a New Interface Row
```python
# With type registry available
type_info = type_registry["IANAifType"]
valid_types = {e["value"]: e["name"] for e in type_info["enums"]}

new_row = {
    "index": [3],
    "values": {
        "ifDescr": "wlan0",
        "ifType": 71,  # ieee80211, validated against enums
        "ifMtu": 1500,
        "ifSpeed": 54000000
    }
}
```

### Validating Configuration
```python
def validate_value(value, type_name, type_registry):
    type_info = type_registry[type_name]
    
    # Check enums
    if type_info["enums"]:
        valid_values = [e["value"] for e in type_info["enums"]]
        if value not in valid_values:
            raise ValueError(f"Invalid enum value: {value}")
    
    # Check constraints
    for constraint in type_info["constraints"]:
        if constraint["type"] == "ValueRangeConstraint":
            if not (constraint["min"] <= value <= constraint["max"]):
                raise ValueError(f"Value {value} out of range")
```

## Next Steps

1. Review and approve schema design
2. Update `BehaviourGenerator` to include metadata
3. Create schema validation tool
4. Generate sample behavior files using new schema
5. Update documentation
