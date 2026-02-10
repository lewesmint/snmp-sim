# MIB Browser Module

## Overview

The MIB Browser is a standalone SNMP testing tool that can be run independently or embedded in the main SNMP Simulator GUI.

## Features

- **SNMP Operations**: GET, GETNEXT, WALK, SET
- **Hierarchical Display**: Tree view of SNMP walk results
- **OID Name Resolution**: Automatic MIB name lookup
- **Standalone or Embedded**: Can run as a separate tool or within the main GUI

## Dependencies

The MIB Browser requires `pysnmp` for SNMP protocol operations. Install it using:

```bash
# Note: Package ecosystem is in transition
# Try one of these:
pip install pysnmp
# or
pip install pysnmp-lextudio
# or 
pip install easysnmp
```

**Note**: The pysnmp package ecosystem has undergone significant changes. Version 7.x has a different API structure. For compatibility, you may need to:

1. Check pysnmp documentation for your version
2. Adjust imports in `ui/mib_browser.py` if needed
3. Consider using `easysnmp` as an alternative

## Running Standalone

```bash
python -m ui.mib_browser --host 127.0.0.1 --port 161 --community public
```

Or from within the ui directory:

```bash
cd ui
python mib_browser.py --help
```

## Usage

### As Standalone Application

```python
from ui.mib_browser import MIBBrowserWindow

browser = MIBBrowserWindow(
    default_host="127.0.0.1",
    default_port=161,
    default_community="public"
)
browser.run()
```

### Embedded in Another Application

```python
from ui.mib_browser import MIBBrowserWindow
from ui.common import Logger

# Create logger
logger = Logger(log_widget=some_text_widget)

# Create embedded browser
browser = MIBBrowserWindow(
    parent=some_frame,
    logger=logger,
    default_host="192.168.1.1",
    oid_metadata=metadata_dict  # Optional: for name resolution
)

# Update metadata later
browser.set_oid_metadata(new_metadata)
```

## Architecture

### Module Structure

```
ui/
├── common.py          # Shared utilities (Logger, formatters)
├── mib_browser.py     # Standalone MIB Browser
├── snmp_gui.py        # Main GUI (embeds MIB Browser)
└── README_MIB_BROWSER.md
```

### Key Classes

- **MIBBrowserWindow**: Main browser window/widget
  - Handles SNMP operations
  - Manages UI components
  - Can be standalone or embedded

- **Logger** (from common.py): Shared logging utility
  - Outputs to console and optional text widget
  - Consistent timestamped messages

### OctetString Type

The MIB browser properly imports `OctetString` from `pysnmp.smi.rfc1902` instead of using wildcard imports. This is the correct way to get MIB types:

```python
from pysnmp.smi.rfc1902 import OctetString, Integer, Counter32, etc...
```

## Configuration

### Connection Settings

- **Host**: SNMP agent IP address (default: 127.0.0.1)
- **Port**: SNMP port (default: 161)
- **Community**: SNMP community string (default: public)

### OID Metadata

The browser can use OID metadata for human-readable names:

```python
metadata = {
    "1.3.6.1.2.1.1.1.0": {
        "name": "sysDescr",
        "type": "OctetString"
    }
}
browser.set_oid_metadata(metadata)
```

## Type Checking

The module passes strict mypy type checking:

```bash
mypy ui/mib_browser.py
mypy ui/common.py
mypy ui/snmp_gui.py
```

## Troubleshooting

### Import Errors

If you see `ImportError: cannot import name 'SnmpEngine'`:

1. Check your pysnmp version: `pip show pysnmp`
2. Try reinstalling: `pip uninstall pysnmp pysnmp-lextudio && pip install pysnmp`
3. Check pysnmp documentation for API changes

### Module Not Found

If running from `ui/` directory fails with module import errors, run from the project root:

```bash
python -m ui.mib_browser
```

## Future Enhancements

- Type selection UI for SET operations (currently defaults to OctetString)
- MIB file loading and compilation
- Save/load SNMP queries
- Bulk operations support
- V3 authentication support
