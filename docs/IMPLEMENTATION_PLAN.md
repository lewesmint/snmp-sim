# Implementation Plan: Three-File Architecture

## Changes Required

### 1. BehaviourGenerator (app/generator.py)
**Current:** Generates `{mib}_behaviour.json` with mixed structure
**New:** Generates `{mib}/schema.json` with clean structure

Changes:
- Rename `generate()` output from `{mib}_behaviour.json` to `{mib}/schema.json`
- Create MIB-specific directory: `mock-behaviour/{mib}/`
- Separate scalars and tables in output structure
- Use "initial" key instead of mixed "value"/"initial" 
- Remove "dynamic_function" from schema (moves to behavior.json)
- Include metadata from type registry (constraints, enums, display_hint)

### 2. Behavior Store (app/behaviour_store.py)
**Current:** Single file loader
**New:** Three-file loader with resolution order

Changes:
- Load schema.json (structure + initial values)
- Load behavior.json (dynamic_function mappings) - optional
- Load values.json (current runtime state) - optional, auto-created
- Implement resolution order: dynamic → current → initial → type default

### 3. SNMP Agent (app/snmp_agent.py)
**Current:** Loads single behaviour.json
**New:** Uses BehaviourStore for value resolution

Changes:
- Use BehaviourStore.get_value(oid) with full resolution
- Handle SET operations to update values.json
- Initialize dynamic function plugins on startup

### 4. Dynamic Function Plugins (new: app/dynamic_plugins/)
**New directory** for dynamic function implementations

Create:
- `__init__.py` - Plugin loader
- `uptime_plugin.py` - System uptime in TimeTicks
- `counter_plugin.py` - Auto-incrementing counters
- Plugin registration system

### 5. CLI Updates
- `cli_mib_to_json.py` - Update help text to mention schema.json
- Add new CLI: `cli_create_behavior.py` - Helper to create behavior.json templates

## File Structure After Changes

```
mock-behaviour/
  SNMPv2-MIB/
    schema.json          # Generated: structure + initial values
    behavior.json        # Optional: dynamic functions
    values.json          # Runtime: current state
  IF-MIB/
    schema.json
    behavior.json
    values.json
```

## Implementation Order

1. ✅ Update design document
2. Update BehaviourGenerator to create new schema format
3. Create dynamic plugins system
4. Update BehaviourStore with three-file resolution
5. Update SNMP Agent to use new system
6. Create migration tool for old behavior files
7. Update CLI tools and documentation
8. Test with sample MIBs

## Next Step

Start with step 2: Update BehaviourGenerator
