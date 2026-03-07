#!/usr/bin/env python3
"""Test that the agent can properly load and decode values from the improved schema."""

import json
import sys

from app.snmp_agent import SNMPAgent


def test_schema_loading() -> None:
    """Test loading and decoding values from the improved schema."""
    # Load the improved schema
    schema_path = "data/experimental_schema/improved_schema.json"
    with open(schema_path) as f:
        schema = json.load(f)

    # Create agent instance
    agent = SNMPAgent()

    # Get the table data
    tables = schema.get("mib", {}).get("tables", {})
    test_table = tables.get("myTestTable", {})
    rows = test_table.get("rows", [])

    # Test each row's MAC address
    for idx, row in enumerate(rows):
        values = row.get("values", {})
        mac_value = values.get("myTestMacAddress")

        if mac_value is None:
            continue

        # Decode the value using the agent's method
        decoded = agent._decode_value(mac_value)

        if isinstance(decoded, (bytes, bytearray)):
            assert len(decoded) == 6, f"Expected 6 bytes for MAC address, got {len(decoded)}"
            if idx == 0:
                assert decoded == b"\x00\x11\x22\x33\x44\x55", "Row 0 MAC mismatch"
            elif idx == 1:
                assert decoded == b"\xaa\xbb\xcc\xdd\xee\xff", "Row 1 MAC mismatch"
            elif idx == 2:
                assert decoded == b"\x00\x00\x00\x00\x00\x00", "Row 2 MAC mismatch"
        else:
            assert decoded == mac_value

    # Test that regular values still work
    row0_values = rows[0].get("values", {})
    name = agent._decode_value(row0_values.get("myTestName"))
    assert name == "Interface One", f"Expected 'Interface One', got {name!r}"

    counter = agent._decode_value(row0_values.get("myTestCounter"))
    assert counter == 0, f"Expected 0, got {counter!r}"


if __name__ == "__main__":
    try:
        test_schema_loading()
    except (
        AssertionError,
        AttributeError,
        ImportError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        import traceback

        traceback.print_exc()
        sys.exit(1)
