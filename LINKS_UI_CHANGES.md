# Links UI Improvements - Summary

## What Changed

The links UI has been completely simplified from a complex tree-based picker to a straightforward text input system.

### Before
- Complex dialog with available/selected trees
- Had to navigate hierarchies  
- Dropdown showing "Match" with only one option (confusing)
- Scope/Match selection was not intuitive
- Row-by-row clicking to select columns

### After  
- Simple text input field
- Type column names or OIDs directly
- Auto-detection of link type
- Real-time status showing what will happen
- Much faster and clearer

## How the Simplification Works

### 1. **Smart Auto-Detection**
The system analyzes what you enter:
- Detects if OIDs are columns (have a table parent) or scalars
- Automatically sets `scope` to `per-instance` for columns or `global` for scalars
- Automatically sets `match` to `shared-index` for columns or `same` for scalars

### 2. **Status Bar Feedback**
As you type, you get real-time feedback:
- ✓ "3 columns: Will link by shared index" 
- ⚠ "Mix of columns and scalars (use one type)"
- ⚠ "Need at least 2 OIDs"

### 3. **Supported Input Formats**
- Column names: `ifDescr`, `ifName` (auto-resolved)
- Full OIDs: `1.3.6.1.2.1.2.2.1.2`
- Mixed on one line: `ifDescr, ifName`
- Multiple lines: One per line

## Files Changed

### [app/api_mibs.py](app/api_mibs.py)
- Enhanced metadata endpoint to include `parent_oid` and `parent_type`
- System can now detect columns vs scalars

### [app/api_links.py](app/api_links.py)
- Updated `LinkRequest.match` to accept both `"shared-index"` and `"same"`
- Now supports both augmented table linking and scalar linking

### [ui/snmp_gui_links_mixin.py](ui/snmp_gui_links_mixin.py)
- **Completely replaced** the dialog implementation
- Removed: Complex tree views, selection logic, scope change handlers
- Added: Simple text input, real-time validation, auto-detection
- Removed old helper methods:
  - `_build_link_available_tree()`
  - `_build_link_selected_tree()`
  - `_build_link_dialog_shell()`
  - `_compute_dialog_endpoint()`
  - `_load_existing_link_selected()`
  - `_save_link_dialog()`
  - `_parse_endpoints_text()`

## Testing

### Verify It Works
```bash
# Create a column link
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
  
# Should return: {"status": "ok", "id": "link_X"}
```

## User Benefits

✅ **Clear and Simple** - Just type what you want to link
✅ **Automatic Detection** - No need to understand scopes/match types  
✅ **Real-time Feedback** - See what will happen before clicking save
✅ **Fewer Clicks** - No tree navigation or button clicking
✅ **Supports Both Use Cases** - Augmented tables AND scalars (though scalars rarely needed)

## Documentation

See [LINKS_UI_GUIDE.md](LINKS_UI_GUIDE.md) for:
- Quick start guide
- Examples of linking ifDescr↔ifName
- Explanation of per-instance vs global linking
- Troubleshooting
- API usage examples
