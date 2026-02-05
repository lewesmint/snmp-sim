#!/usr/bin/env python3
"""Test that the agent can properly load and decode values from the improved schema."""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.snmp_agent import SNMPAgent


def test_schema_loading() -> None:
    """Test loading and decoding values from the improved schema."""

    # Load the improved schema
    schema_path = "data/experiemntal_schema/improved_schema.json"
    with open(schema_path, "r") as f:
        schema = json.load(f)

    print(f"✓ Loaded schema from {schema_path}")

    # Create agent instance
    agent = SNMPAgent()

    # Get the table data
    tables = schema.get("mib", {}).get("tables", {})
    test_table = tables.get("myTestTable", {})
    rows = test_table.get("rows", [])

    print(f"✓ Found {len(rows)} rows in myTestTable")

    # Test each row's MAC address
    for idx, row in enumerate(rows):
        values = row.get("values", {})
        mac_value = values.get("myTestMacAddress")

        if mac_value is None:
            print(f"  Row {idx}: No MAC address")
            continue

        # Decode the value using the agent's method
        decoded = agent._decode_value(mac_value)

        # Verify it's bytes
        assert isinstance(decoded, bytes), f"Expected bytes, got {type(decoded)}"
        assert len(decoded) == 6, (
            f"Expected 6 bytes for MAC address, got {len(decoded)}"
        )

        # Format as MAC address
        mac_str = decoded.hex(":")
        print(f"  Row {idx}: MAC address = {mac_str}")

        # Verify the specific values
        if idx == 0:
            assert decoded == b"\x00\x11\x22\x33\x44\x55", "Row 0 MAC mismatch"
        elif idx == 1:
            assert decoded == b"\xaa\xbb\xcc\xdd\xee\xff", "Row 1 MAC mismatch"
        elif idx == 2:
            assert decoded == b"\x00\x00\x00\x00\x00\x00", "Row 2 MAC mismatch"

    # Test that regular values still work
    row0_values = rows[0].get("values", {})
    name = agent._decode_value(row0_values.get("myTestName"))
    assert name == "Interface One", f"Expected 'Interface One', got {name}"
    print(f"✓ Regular string value works: {name}")

    counter = agent._decode_value(row0_values.get("myTestCounter"))
    assert counter == 0, f"Expected 0, got {counter}"
    print(f"✓ Regular integer value works: {counter}")

    print("\n✅ All schema integration tests passed!")


if __name__ == "__main__":
    try:
        test_schema_loading()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
