#!/usr/bin/env python3
"""
Test script to verify enum dropdown functionality in the GUI.
Tests both scalar and table enum editing.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Main test function to demonstrate enum dropdown usage."""
    print("=" * 70)
    print("Testing Enum Dropdown Functionality")
    print("=" * 70)
    print()
    print("This test verifies that enum fields show dropdowns for editing.")
    print()
    print("Test Steps:")
    print("1. Start the SNMP agent with TEST-ENUM-MIB data")
    print("2. Launch the GUI")
    print("3. Connect to the agent")
    print("4. Test scalar enum editing:")
    print("   - Navigate to TEST-ENUM-MIB → testColour")
    print("   - Double-click to edit")
    print("   - Should see dropdown with: 1 (red), 2 (green), 3 (blue), 4 (yellow)")
    print("   - Select a value and save")
    print()
    print("5. Test table enum editing:")
    print("   - Navigate to TEST-ENUM-MIB → testEnumTable")
    print("   - Click on Table View tab")
    print("   - Click on any Colour or Priority cell")
    print("   - Should see dropdown with enum values")
    print("   - For testRowColour: 1 (red), 2 (green), 3 (blue), 4 (yellow)")
    print("   - For testRowPriority: 1 (low), 2 (medium), 3 (high)")
    print("   - Select a value and press Enter or click away")
    print()
    print("=" * 70)
    print()
    
    # Check if TEST-ENUM-MIB data exists
    mib_dir = Path(__file__).parent / "agent-model" / "TEST-ENUM-MIB"
    if not mib_dir.exists():
        print(f"ERROR: {mib_dir} not found!")
        print("Please ensure TEST-ENUM-MIB model exists.")
        return 1
    
    schema_file = mib_dir / "schema.json"
    if not schema_file.exists():
        print(f"ERROR: {schema_file} not found!")
        return 1
    
    # Read schema to verify enums exist
    import json
    with open(schema_file) as f:
        schema = json.load(f)
    
    print("Enum definitions found in schema:")
    print()
    
    # Check all objects for enums
    objects = schema.get("objects", {})
    if not objects:
        print("  No objects found in schema!")
        return 1
    
    for name, data in objects.items():
        if "enums" in data:
            obj_type = "Table Column" if "." in name or "Entry" in name.title() else "Scalar/Object"
            print(f"  {obj_type}: {name}")
            print(f"    OID: {'.'.join(map(str, data.get('oid', [])))}")
            print(f"    Type: {data.get('type', 'Unknown')}")
            print(f"    Enums: {data['enums']}")
            print()
    
    print("=" * 70)
    print("Ready to test!")
    print()
    print("Run these commands in separate terminals:")
    print()
    print("  Terminal 1: python run_agent_with_rest.py")
    print("  Terminal 2: python start_with_gui.py")
    print()
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
