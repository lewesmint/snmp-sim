# Dropdown Lockup Issue - Root Cause and Fix

## Problem Description

When selecting an item from a readonly combobox dropdown in the table view, the UI would lock up. The user had to click on another window to unlock it. Additionally, the value would not be saved.

## Root Cause - SOLVED!

After extensive testing, the issue was **incorrect assumptions about event order on macOS**.

### The Critical Discovery

On macOS, the event sequence is:

1. User clicks dropdown → Dropdown opens
2. User selects item → **`<FocusOut>` fires FIRST**
3. Then → **`<<ComboboxSelected>>` fires SECOND**

This is **opposite** to what we initially assumed! We thought ComboboxSelected fired first while the grab was still active.

### What Was Happening

Our "fix" was waiting for FocusOut to save, but:
- FocusOut fired BEFORE ComboboxSelected
- So we never saved in FocusOut (because we were waiting for ComboboxSelected to mark the selection)
- Then ComboboxSelected fired but we didn't save there either (we were waiting for FocusOut)
- Result: Nothing saved, UI locked up

### The Actual Solution

**Save immediately in `<<ComboboxSelected>>`** - By the time this event fires, FocusOut has already happened and the grab is already released!

## The Fix

### Solution: Save immediately in `<<ComboboxSelected>>`

Since FocusOut fires BEFORE ComboboxSelected, by the time ComboboxSelected fires, the grab is already released. We can save immediately!

### Code Changes:

**1. In `_on_combo_selected()` - Save immediately:**

```python
def _on_combo_selected(self):
    """Handle combo selection.

    CRITICAL INSIGHT: On macOS, FocusOut fires BEFORE ComboboxSelected!
    By the time we get here, the grab is already released, so we can save immediately.
    """
    if not self.editing_item:
        return

    print("DEBUG: ComboboxSelected event fired - saving immediately")

    # Save immediately - the grab is already released by this point
    self._save_edit()
```

**2. In `_on_focus_out()` - Don't save here:**

```python
def _on_focus_out(self):
    """Handle focus leaving combobox.

    On macOS, this fires BEFORE ComboboxSelected, so we don't save here.
    """
    print("DEBUG: FocusOut event fired (happens before ComboboxSelected on macOS)")
```

**3. In `_save_edit()` - Hide immediately in finally block:**

```python
def _save_edit(self):
    try:
        # ... save logic ...
    finally:
        # Hide immediately - no delay needed since grab is already released
        self._hide_edit_overlay()
```

## Why This Works

### The Key Insight:
The event order on macOS is:
1. `<FocusOut>` fires first (when dropdown closes)
2. `<<ComboboxSelected>>` fires second (after grab is released)

### Why Our Previous "Fixes" Failed:
- We were waiting for FocusOut to save, but FocusOut fires BEFORE ComboboxSelected
- So we never saved because we were waiting for the wrong event
- The grab is already released by the time ComboboxSelected fires

### The Correct Approach:
- Save immediately in `<<ComboboxSelected>>`
- By that time, FocusOut has already fired and the grab is released
- No delays needed - just save and hide immediately

## Testing

### Diagnostic Testing (How We Found the Solution)
Run the debug version to see event order:
```bash
python3 test_dropdown_debug.py
```

This shows that FocusOut fires BEFORE ComboboxSelected on macOS!

### Manual Testing
Run the fixed test file:
```bash
python3 test_dropdown_lockup.py
```

Double-click on Column 2 cells and select different values from the dropdown. The UI should remain responsive and values should be saved correctly.

## Files Modified

1. ✅ `test_dropdown_lockup.py` - Fixed to save immediately in ComboboxSelected
2. ✅ `ui/snmp_gui.py` - Fixed to save immediately in ComboboxSelected
3. ✅ `test_dropdown_debug.py` - NEW: Debug tool that revealed the event order
4. ✅ `test_dropdown_no_hide.py` - NEW: Alternative approach (move off-screen)
5. ✅ `test_dropdown_alternative.py` - NEW: Listbox popup alternative
6. ✅ `test_dropdown_postcommand.py` - NEW: PostCommand approach
7. ✅ `test_dropdown_strategies.py` - NEW: Strategy comparison tool
8. ✅ `DROPDOWN_TEST_SUITE.md` - Test suite documentation
9. ✅ `DROPDOWN_LOCKUP_FIX.md` - This documentation

## Summary

The lockup was caused by **incorrect assumptions about event order on macOS**.

### What We Learned:
- On macOS, `<FocusOut>` fires **BEFORE** `<<ComboboxSelected>>`
- By the time ComboboxSelected fires, the grab is already released
- We can save immediately in ComboboxSelected without any delays

### The Solution:
1. **Save immediately in `<<ComboboxSelected>>`** - The grab is already released
2. **Don't save in `<FocusOut>`** - It fires too early (before selection is made)
3. **No delays needed** - Just save and hide immediately
4. **Refresh OID tree** - After saving, update the OID tree to show changes

This is the opposite of what we initially thought! The debug test file (`test_dropdown_debug.py`) was critical in revealing the actual event sequence.

## Additional Fix: OID Tree Refresh

After fixing the dropdown lockup, we discovered another issue: when you edit values in the table view, the changes save to JSON correctly, but the OID tree (left panel) doesn't refresh to show the changes.

### The Problem:
- The OID tree is populated from bulk API calls when you connect
- After editing a cell, the table view updates but the OID tree doesn't
- Newly added instances don't appear in the tree
- Modified values don't update in the tree

### The Solution:
Added two new methods to refresh the OID tree after edits:

1. **`_refresh_oid_tree_value(full_oid, display_value)`** - Updates a specific OID value in the tree
   - Searches the tree for the matching OID (base OID + instance)
   - Updates the value column to show the new value
   - Called after every successful cell edit

2. **`_refresh_oid_tree_table(table_item)`** - Re-discovers table instances to show new rows
   - Triggers background re-discovery of all table instances
   - Rebuilds the tree nodes to include new entries
   - Called when a new instance is created

### How New Instances Are Detected:
When saving a cell edit, the code checks if the full OID (column OID + instance) exists in the `oid_values` cache:
- If it doesn't exist → this is a **new instance** → call both refresh methods
- If it exists → this is an **update** → only call `_refresh_oid_tree_value()`

### Auto-Refresh on Expand:
When you expand a table node in the OID tree, it **always refreshes** the instances from the API (line 1877-1902 in `_on_node_open`). This ensures the OID tree always shows the current state when you expand it.

### Immediate OID Tree Updates:
The OID tree now updates **immediately** when you make changes in the table view:

1. **Delete instance** (line 3110-3116 in `_remove_instance`):
   - After successful deletion via DELETE /table-row
   - Calls `_remove_instance_from_oid_tree()` to immediately remove the entry from the tree
   - No need to manually expand the table to see the change

2. **Add instance** (line 3033-3043 in `_add_instance`):
   - After successful creation via POST /table-row
   - Calls `_add_instance_to_oid_tree()` to immediately add the entry to the tree
   - The new instance appears in the tree with proper sorting

3. **Edit instance index** (line 2504-2536 in `_save_cell_edit`):
   - When an index column is edited, the old instance is deleted and a new one is created
   - Calls `_remove_instance_from_oid_tree()` for the old instance
   - Calls `_add_instance_to_oid_tree()` for the new instance
   - The tree automatically re-sorts to put the changed index in the right place

This ensures:
- ✅ Deleted instances disappear from the tree **immediately**
- ✅ Added instances appear in the tree **immediately**
- ✅ Modified values update in the tree **immediately**
- ✅ Index changes are reflected with proper sorting **immediately**
- ✅ No need to manually expand/collapse to see changes

