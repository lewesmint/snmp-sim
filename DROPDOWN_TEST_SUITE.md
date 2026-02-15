# Dropdown Lockup - Test Suite

Since none of the standard strategies work, I've created multiple test files to help diagnose and fix the issue.

## Test Files

### 1. `test_dropdown_debug.py` - Event Debugging
**Purpose:** See exactly what events fire and in what order.

```bash
python3 test_dropdown_debug.py
```

**What to watch:**
- The event log shows every event that fires
- Look for the sequence of events when you select from dropdown
- Note if FocusOut fires and when
- Check if the UI locks up before or after certain events

### 2. `test_dropdown_no_hide.py` - Never Hide Overlay
**Purpose:** Test if the issue is with hiding/destroying the widget.

```bash
python3 test_dropdown_no_hide.py
```

**What's different:**
- The overlay is never destroyed with `place_forget()`
- Instead, it's just moved off-screen to x=-1000, y=-1000
- If this works, the issue is specifically with hiding the widget

### 3. `test_dropdown_postcommand.py` - Track Dropdown State
**Purpose:** Use the combobox `postcommand` to track when dropdown opens.

```bash
python3 test_dropdown_postcommand.py
```

**What's different:**
- Uses `postcommand` callback to know when dropdown is opening
- Tracks dropdown state with a flag
- May help understand the timing better

### 4. `test_dropdown_alternative.py` - Listbox Popup
**Purpose:** Completely avoid combobox by using a Listbox in a Toplevel window.

```bash
python3 test_dropdown_alternative.py
```

**What's different:**
- No combobox at all
- Uses a Listbox in a borderless Toplevel window
- Click (not double-click) to edit
- If this works, we can replace combobox with this approach

### 5. `test_dropdown_strategies.py` - Compare Strategies
**Purpose:** Test 4 different event handling strategies side-by-side.

```bash
python3 test_dropdown_strategies.py
```

**Strategies:**
1. Save on ComboboxSelected (immediate)
2. Save on ComboboxSelected (after_idle)
3. Save on FocusOut only
4. Save on ComboboxSelected + close dropdown first

## What to Test

For each test file, please try:

1. **Does it lock up?** - Can you still interact with the window after selecting?
2. **Does the value save?** - Check if the cell value actually changes
3. **What do you have to do to unlock?** - Click elsewhere? Click on desktop?
4. **Console output** - What messages appear in the terminal?

## Reporting Results

Please test each file and report:

```
test_dropdown_debug.py:
- Locks up: YES/NO
- Value saves: YES/NO
- Console shows: [paste relevant output]

test_dropdown_no_hide.py:
- Locks up: YES/NO
- Value saves: YES/NO

test_dropdown_alternative.py:
- Locks up: YES/NO
- Value saves: YES/NO

test_dropdown_postcommand.py:
- Locks up: YES/NO
- Value saves: YES/NO
```

## Next Steps

Based on which tests work:

- **If `test_dropdown_no_hide.py` works:** The issue is with `place_forget()`. We can use the move-off-screen approach.

- **If `test_dropdown_alternative.py` works:** We should replace combobox with a Listbox popup for enum fields.

- **If `test_dropdown_debug.py` shows specific event sequence:** We can adjust timing based on actual events.

- **If none work:** The issue may be deeper - possibly with tkinter/ttk on macOS, and we may need a completely different UI approach.

## Current Hypothesis

The issue is likely that on macOS:
1. Readonly combobox dropdown creates a modal grab
2. The grab persists even after `<<ComboboxSelected>>` fires
3. Any attempt to modify the widget tree while grab is active causes lockup
4. The grab only releases when you click outside the dropdown area

This is a known issue with ttk.Combobox on macOS and may require working around it entirely.

