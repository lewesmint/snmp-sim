# Value Linking Feature

## Overview

The value linking system allows you to create bidirectional synchronization between OID values. When one linked OID is updated via SNMP SET, all other linked OIDs are automatically updated with the same value.

This is particularly useful for:
- Augmented tables where columns should stay synchronized (e.g., `ifDescr` and `ifName`)
- Mirroring values across different MIBs
- Maintaining data consistency

## Configuration

Add a `"links"` section to your schema JSON file:

```json
{
  "mibs": ["IF-MIB"],
  "objects": {
    "ifTable": {...},
    "ifEntry": {...},
    "ifDescr": {...},
    "ifName": {...}
  },
  "links": [
    {
      "id": "if-descr-name-link",
      "columns": ["ifDescr", "ifName"],
      "scope": "per-instance",
      "type": "bidirectional"
    }
  ]
}
```

## Link Configuration

### Required Fields

- **`columns`**: Array of column names to link together (minimum 2)
- **`scope`**: 
  - `"per-instance"`: Link table columns on a per-row basis (typical for tables)
  - `"global"`: Link scalar OIDs (future feature)

### Optional Fields

- **`id`**: Unique identifier for the link (auto-generated if not provided)
- **`type`**: Always `"bidirectional"` (future: could support one-way)

## Behavior

### Per-Instance Table Linking

When columns are linked with `scope: "per-instance"`:

1. Each table instance maintains its own synchronized values
2. Updating `ifDescr.1` will also update `ifName.1`
3. Updating `ifName.1` will also update `ifDescr.1` 
4. Instance `.2` has independent values from instance `.1`

### Example

Given this link configuration:
```json
{
  "columns": ["ifDescr", "ifName"],
  "scope": "per-instance"
}
```

**Before:**
```
ifDescr.1 = "eth0"
ifName.1 = "Ethernet0" 
ifDescr.2 = "eth1"
ifName.2 = "Ethernet1"
```

**After SNMP SET** `ifDescr.1 = "FastEthernet0"`:
```
ifDescr.1 = "FastEthernet0"  ← Updated by SET
ifName.1 = "FastEthernet0"   ← Automatically synchronized
ifDescr.2 = "eth1"             (unchanged)
ifName.2 = "Ethernet1"         (unchanged)
```

## Implementation Details

### Infinite Loop Prevention

The link manager tracks updates in progress to prevent infinite recursion:
- When `ifDescr` is updated, it propagates to `ifName`
- The propagation to `ifName` is marked as "in progress"
- `ifName`'s link back to `ifDescr` sees the "in progress" flag and skips propagation

### Table Instance Matching

For augmented tables (tables that share indexes via AUGMENTS):
- Links automatically work across table boundaries
- The `table_oid` is derived from the schema structure
- Instance indexes are matched across all linked columns

## CLI Tool: Managing Links

You can view and test links via the API:

```bash
# View loaded links (future feature)
curl http://localhost:8000/links

# Test a link by updating a value
curl -X POST http://localhost:8000/table-row \
  -H "Content-Type: application/json" \
  -d '{
    "table_oid": "1.3.6.1.2.1.2.2",
    "index_values": {"ifIndex": 1},
    "column_values": {"ifDescr": "NewDescription"}
  }'

# Verify both columns updated
curl http://localhost:8000/value?oid=1.3.6.1.2.1.2.2.1.2.1  # ifDescr.1
curl http://localhost:8000/value?oid=1.3.6.1.2.1.31.1.1.1.1.1  # ifName.1
```

## Logging

Link operations are logged at INFO level:

```
INFO: Added value link: ValueLink(if-descr-name-link, {'ifDescr', 'ifName'}, scope=per-instance)
INFO: Propagating value from ifDescr to linked columns: ['ifName']
```

## Future Enhancements

- **Transformations**: Apply functions during propagation (e.g., lowercase, prefix)
- **Global scope**: Link scalar OIDs (non-table)
- **One-way links**: Source-only propagation without bidirectional sync
- **Conditional links**: Only link if certain conditions are met
- **GUI management**: Configure links via the SNMP GUI
