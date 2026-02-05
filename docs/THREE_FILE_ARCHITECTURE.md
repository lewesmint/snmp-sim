# Three-File Architecture (Option C - British Spelling)

## Overview

The SNMP simulator uses a **three-file architecture** for each MIB, with British spelling conventions:

```
mock-behaviour/
  SNMPv2-MIB/
    schema.json       ← Generated: Structure + initial values
    behaviour.json    ← Optional: Dynamic functions (user-created)
    values.json       ← Runtime: Current state (agent-created)
  IF-MIB/
    schema.json
    behaviour.json
    values.json
```

## The Three Files

### 1. schema.json (Generated)

**Created by:** `BehaviourGenerator` via `cli_mib_to_json`  
**Purpose:** MIB structure with OIDs, types, access levels, and initial values  
**When:** Generated once from compiled MIB  
**Modified:** Regenerated when MIB changes

**Command:**
```bash
python -m app.cli_mib_to_json compiled-mibs/SNMPv2-MIB.py
# Creates: mock-behaviour/SNMPv2-MIB/schema.json
```

**Contains:**
- OID definitions
- SNMP types
- Access levels (read-only, read-write, etc.)
- Initial/default values
- Type metadata (constraints, enums, display hints)

### 2. behaviour.json (Optional, User-Created)

**Created by:** User (manually)  
**Purpose:** Define dynamic value computations  
**When:** Only when you need computed/dynamic values  
**Modified:** By user as needed

**Example:**
```json
{
  "sysUpTime": {
    "dynamic_function": "uptime"
  },
  "ifInOctets": {
    "dynamic_function": "counter_increment",
    "params": {
      "rate": 1000
    }
  }
}
```

**Use cases:**
- System uptime (constantly changing)
- Counters that auto-increment
- Values computed from other values
- Time-based values

### 3. values.json (Runtime, Agent-Created)

**Created by:** SNMP Agent at runtime  
**Purpose:** Store current runtime state  
**When:** Created/updated during agent operation  
**Modified:** By agent when values change (SNMP SET operations)

**Example:**
```json
{
  "sysContact": {
    "oid": [1, 3, 6, 1, 2, 1, 1, 4, 0],
    "value": "admin@example.com",
    "last_modified": "2026-02-05T10:30:00Z"
  }
}
```

**Use cases:**
- Values modified via SNMP SET
- Runtime state that persists across restarts
- Override initial values from schema.json

## Value Resolution Order

When the agent receives an SNMP GET request, it resolves values in this order:

1. **Dynamic Function** - Check `behaviour.json` for dynamic_function
2. **Current Value** - Check `values.json` for runtime value
3. **Initial Value** - Check `schema.json` for initial value
4. **Type Default** - Fall back to type default (should rarely happen)

### Example: sysUpTime

```
GET sysUpTime.0
→ behaviour.json has "dynamic_function": "uptime"
→ Call uptime plugin
→ Return 123456 ticks
```

### Example: sysContact (after SET)

```
GET sysContact.0
→ behaviour.json: no entry
→ values.json has "value": "admin@example.com"
→ Return "admin@example.com"
```

### Example: sysDescr (default)

```
GET sysDescr.0
→ behaviour.json: no entry
→ values.json: no entry
→ schema.json has "initial": "Simple Python SNMP Agent"
→ Return "Simple Python SNMP Agent"
```

## Workflow

### Initial Setup

```bash
# 1. Compile MIB
python -m app.cli_compile_mib data/mibs/IF-MIB.txt

# 2. Generate schema
python -m app.cli_mib_to_json compiled-mibs/IF-MIB.py
# Creates: mock-behaviour/IF-MIB/schema.json

# 3. (Optional) Create behaviour.json for dynamic values
# Manually create: mock-behaviour/IF-MIB/behaviour.json

# 4. Start agent
python -m app.snmp_agent
# Agent creates: mock-behaviour/IF-MIB/values.json (if needed)
```

### Adding Dynamic Behaviour

Create `mock-behaviour/SNMPv2-MIB/behaviour.json`:

```json
{
  "sysUpTime": {
    "dynamic_function": "uptime"
  }
}
```

### Modifying Values at Runtime

```bash
# SNMP SET updates values.json automatically
snmpset -v2c -c private localhost:1161 sysContact.0 s "newadmin@example.com"
```

## Naming Conventions

- **British spelling:** behaviour.json (not behavior.json)
- **Lowercase:** schema.json, behaviour.json, values.json
- **Directory per MIB:** mock-behaviour/{MIB_NAME}/
- **Class name:** `BehaviourGenerator` (British spelling)

## Migration from Old Format

If you have old `{MIB}_behaviour.json` files (flat format), they need to be migrated:

**Old format:**
```
mock-behaviour/
  SNMPv2-MIB_behaviour.json
```

**New format:**
```
mock-behaviour/
  SNMPv2-MIB/
    schema.json
```

The agent now expects the new directory structure.

