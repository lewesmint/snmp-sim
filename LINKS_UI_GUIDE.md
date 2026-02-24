# Links UI - Simple Column/Scalar Linking

## Quick Start

The links dialog is now much simpler:

1. **Click Add** to create a new link
2. **Enter OID/column names** (one per line or comma-separated):
   - Column names: `ifDescr`, `ifName` (auto-resolved to OIDs)
   - Or full OIDs: `1.3.6.1.2.1.2.2.1.2`, `1.3.6.1.2.1.31.1.1.1.1`
3. **Watch the status bar** - it shows what type of link will be created
4. **Enter a description** (optional)
5. **Click "Create Link"**

That's it! The system automatically:
- ✓ Detects if you're linking columns (table rows) or scalars
- ✓ Sets the appropriate scope (per-instance or global)
- ✓ Chooses the right match type (shared-index or same)

## Examples

### Linking Table Columns (Recommended - Augmented Tables)

Link `ifDescr` from the base IF-MIB table to `ifName` in the augmented IF-MIB-X table:

```
ifDescr
ifName
```

Or using full OIDs:
```
1.3.6.1.2.1.2.2.1.2
1.3.6.1.2.1.31.1.1.1.1
```

**Result**: When you set `ifDescr[1]` = "eth0", then `ifName[1]` automatically becomes "eth0" too (and vice versa).

### Linking Multiple Columns

Link three related columns together:
```
ifDescr
ifName
ifAlias
```

**Result**: All three stay in sync for each interface index.

### Why Not Link Scalars?

Scalars usually don't need linking because:
- Scalars have ONE value for the whole device, no indices
- If you "link" multiple scalars, they all become identical
- This just wastes space - use one scalar instead

## Column Linking (with Shared Index)

For table columns in augmented tables:

- **Scope**: per-instance
- **Match**: shared-index
- **How it works**: When instance `[1]` is updated in one column, instance `[1]` in all linked columns updates

Example:
- ifDescr[1] = "eth0" → ifName[1] = "eth0"
- ifDescr[2] = "eth1" → ifName[2] = "eth1"

Each index stays synchronized independently.

## Scalar Linking (with Same Value)

For scalars with no index:

- **Scope**: global  
- **Match**: same
- **How it works**: All linked scalars MUST have identical values

Example:
- sysDescr = "System A"
- If sysDescr was linked to sysObjectID, they'd both have the same value
- (Usually not useful - just use one scalar)

## What Gets Linked

✓ **Table Columns** - anything with a parent table OID → **Use shared-index**
✓ **Multiple columns** - link 2+ columns together  
✓ **Bidirectional** - changes propagate both ways
⚠ **Scalars** - technically works but rarely needed → **Use same match**

## Testing Your Links

After creating a link, test it in the Tables tab:

1. Find the first column and set a value
2. Check that the linked column updated automatically
3. Change the linked column
4. Verify the first column changed back

Or use SNMP:
```bash
# Set ifDescr[1]
snmpset -v2c -c private localhost:11161 1.3.6.1.2.1.2.2.1.2.1 s "eth-test"

# Check ifName[1] was updated
snmpget -v2c -c public localhost:11161 1.3.6.1.2.1.31.1.1.1.1.1
# Should show: eth-test
```

## Troubleshooting

**"Need at least 2 OIDs"** → You only entered one. Add at least one more.

**"Mix of columns and scalars"** → You're mixing table columns with scalars. Use one type only.

**"Could not resolve types"** → OID name doesn't exist. Check spelling or use full OID.

**Link created but not syncing** → Make sure both columns exist with data. Links sync values, they don't create missing instances.

## API Usage

```bash
# Link table columns
curl -X POST http://localhost:8800/links \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "per-instance",
    "type": "bidirectional", 
    "match": "shared-index",
    "endpoints": [
      {"table_oid": "1.3.6.1.2.1.2.2", "column": "ifDescr"},
      {"table_oid": "1.3.6.1.2.1.31.1.1", "column": "ifName"}
    ]
  }'

# List all links
curl http://localhost:8800/links | jq

# Delete a link  
curl -X DELETE http://localhost:8800/links/link_1
```

