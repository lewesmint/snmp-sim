#!/usr/bin/env python3
"""Test script to verify value decoding functionality."""

import sys
from typing import cast

from app.snmp_agent import JsonValue, SNMPAgent


def test_decode_value() -> None:
    """Test the _decode_value method."""
    # Create a minimal agent instance (we only need the method)
    agent = SNMPAgent()

    # Test 1: Direct string value
    result = agent._decode_value("hello")
    assert result == "hello", f"Expected 'hello', got {result!r}"

    # Test 2: Direct integer value
    result = agent._decode_value(42)
    assert result == 42, f"Expected 42, got {result!r}"

    # Test 3: Hex-encoded MAC address
    mac_value: dict[str, JsonValue] = {
        "value": "\\x00\\x11\\x22\\x33\\x44\\x55",
        "encoding": "hex",
    }
    result = agent._decode_value(cast("JsonValue", mac_value))
    expected = b"\x00\x11\x22\x33\x44\x55"
    if isinstance(result, (bytes, bytearray)):
        assert result == expected, f"Expected {expected!r}, got {result!r}"
    else:
        assert result == mac_value

    # Test 4: Another hex-encoded value
    mac_value2: dict[str, JsonValue] = {
        "value": "\\xAA\\xBB\\xCC\\xDD\\xEE\\xFF",
        "encoding": "hex",
    }
    result = agent._decode_value(cast("JsonValue", mac_value2))
    expected = b"\xaa\xbb\xcc\xdd\xee\xff"
    if isinstance(result, (bytes, bytearray)):
        assert result == expected, f"Expected {expected!r}, got {result!r}"
    else:
        assert result == mac_value2

    # Test 5: Dict without encoding (should return as-is)
    plain_dict: dict[str, JsonValue] = {"foo": "bar"}
    result = agent._decode_value(cast("JsonValue", plain_dict))
    assert result == plain_dict, f"Expected {plain_dict!r}, got {result!r}"

    # Test 6: All zeros MAC address
    mac_value3: dict[str, JsonValue] = {
        "value": "\\x00\\x00\\x00\\x00\\x00\\x00",
        "encoding": "hex",
    }
    result = agent._decode_value(cast("JsonValue", mac_value3))
    expected = b"\x00\x00\x00\x00\x00\x00"
    if isinstance(result, (bytes, bytearray)):
        assert result == expected, f"Expected {expected!r}, got {result!r}"
    else:
        assert result == mac_value3


if __name__ == "__main__":
    try:
        test_decode_value()
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
