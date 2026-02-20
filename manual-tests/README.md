# Manual Test Scripts

This directory contains interactive and manual test scripts that are not part of the automated pytest test suite. These scripts are meant to be executed directly for exploration, debugging, and manual testing purposes.

## Directory Structure

```
manual-tests/
├── ui/          # GUI/Tkinter interactive tests (12 files)
├── snmp/        # SNMP operation test scripts (8 files)
├── oid/         # OID utility test scripts (5 files)
└── mib/         # MIB exploration scripts (5 files)
```

## UI Tests (`ui/`)

Interactive GUI test scripts using Tkinter. These test various UI components and behaviors:

- `manual_dropdown_*.py` - Tests for dropdown/combobox behavior (7 files)
- `manual_edit_dialog.py` - Edit dialog test
- `manual_enum_dropdown.py` - Enum dropdown test
- `manual_endpoint_table.py` - Endpoint table test
- `manual_status_info.py` - Status info display test
- `manual_table_display.py` - Table display test

**Usage:**
```bash
python manual-tests/ui/manual_dropdown_alternative.py
python manual-tests/ui/manual_table_display.py
```

## SNMP Operation Tests (`snmp/`)

Scripts that perform actual SNMP operations against a running agent (typically at localhost:161 or localhost:11161):

- `test_snmp_operations.py` - Comprehensive SNMP operations (GET, SET, GETNEXT, WALK, GETBULK)
- `test_getnext_*.py` - GetNext operation tests with various OID formats
- `test_get_sysdescr.py` - System description retrieval test
- `test_tree_bulk.py` - Bulk operations test
- `test_multi_index.py` - Multi-index table test
- `test_normalized_oids_with_pysnmp.py` - OID normalization test

**Requirements:** These require a running SNMP agent. Start the agent first:
```bash
python run_agent_with_rest.py
# Then in another terminal:
python manual-tests/snmp/test_snmp_operations.py
```

## OID Utility Tests (`oid/`)

Scripts that test OID processing and format handling:

- `manual_normalize_oid.py` - OID normalization function test
- `manual_oid_1.py` - Basic OID test
- `manual_oid_formats.py` - OID format variations
- `manual_oid_format_variations.py` - Additional format tests
- `manual_short_oid_1.py` - Short OID handling

**Usage:**
```bash
python manual-tests/oid/manual_normalize_oid.py
```

## MIB Exploration Scripts (`mib/`)

Scripts for exploring MIB capabilities and pysnmp MIB handling:

- `test_mib_methods.py` - Explore MIB API methods
- `test_mib_names.py` - Test MIB name resolution
- `test_mib_resolution.py` - Test OID to MIB name resolution
- `test_mib_aware_engine.py` - Test MIB-aware SNMP engine
- `test_mib_browser_oid_compatibility.py` - Test OID compatibility

**Usage:**
```bash
python manual-tests/mib/test_mib_methods.py
```

## Why Manual Tests?

These scripts were moved out of the `tests/` directory because:

1. **Interactive GUI Scripts:** They use Tkinter and require user interaction
2. **Async Functions:** Some have `async def test_*()` functions that are called with `asyncio.run()` at module level, which causes pytest collection failures
3. **External Dependencies:** Many require a running SNMP agent or network access
4. **Exploratory Nature:** They're primarily for exploration and debugging rather than validation

## Note

Some of these scripts may have outdated imports or require specific setup. They are preserved here for reference and manual testing purposes but are not maintained as part of the automated test suite.
