# SNMP Simulator Architecture Summary

## Three-File Architecture (Option C - British Spelling)

### File Structure

```
mock-behaviour/
  {MIB_NAME}/
    schema.json       ← Generated: Structure + initial values
    behaviour.json    ← Optional: Dynamic functions (user-created)
    values.json       ← Runtime: Current state (agent-created)
```

### Components

#### 1. Schema Generation (`BehaviourGenerator`)

**Purpose:** Generate `schema.json` from compiled MIBs

**CLI Command:**
```bash
python -m app.cli_mib_to_json compiled-mibs/SNMPv2-MIB.py
```

**Output:** `mock-behaviour/SNMPv2-MIB/schema.json`

**Contains:**
- OID definitions
- SNMP types
- Access levels
- Initial values (from plugins)
- Type metadata

#### 2. Value Encoding

**Direct values:**
```json
"myName": "Interface One",
"myCounter": 42
```

**Encoded values (binary data):**
```json
"myMacAddress": {
  "value": "\\x00\\x11\\x22\\x33\\x44\\x55",
  "encoding": "hex"
}
```

**Agent decoding:** `_decode_value()` method handles both formats

#### 3. Value Resolution Order

When agent receives SNMP GET:

1. **behaviour.json** → Dynamic function?
2. **values.json** → Runtime value?
3. **schema.json** → Initial value?
4. **Type default** → Fallback

### Key Classes

- **`BehaviourGenerator`** - Generates schema.json from compiled MIBs
- **`SNMPAgent`** - Loads schemas and serves SNMP requests
- **`_decode_value()`** - Decodes encoded values (hex, etc.)

### Naming Conventions

✅ **British spelling:** behaviour.json (not behavior.json)  
✅ **Directory per MIB:** mock-behaviour/{MIB_NAME}/  
✅ **Three files:** schema.json, behaviour.json, values.json  
✅ **Class name:** BehaviourGenerator

### Workflow

```bash
# 1. Compile MIB
python -m app.cli_compile_mib data/mibs/IF-MIB.txt

# 2. Generate schema
python -m app.cli_mib_to_json compiled-mibs/IF-MIB.py

# 3. (Optional) Create behaviour.json manually

# 4. Start agent (creates values.json if needed)
python -m app.snmp_agent
```

### Recent Changes

✅ Fixed generator syntax error (line 151)  
✅ Added value encoding support (hex format)  
✅ Updated generator to create directory structure  
✅ Updated agent to load from new structure  
✅ Updated CLI help text  
✅ Created comprehensive documentation

### Documentation

- `docs/THREE_FILE_ARCHITECTURE.md` - Complete guide to the three-file system
- `docs/VALUE_ENCODING.md` - How to encode binary values
- `docs/BEHAVIOR_SCHEMA_DESIGN.md` - Original design document

