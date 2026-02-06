#!/usr/bin/env python3
"""Test script to verify value decoding functionality."""

import sys
import os

from app.snmp_agent import SNMPAgent


def test_decode_value() -> None:
    """Test the _decode_value method."""

    # Create a minimal agent instance (we only need the method)
    agent = SNMPAgent()

    # Test 1: Direct string value
    result = agent._decode_value("hello")
    assert result == "hello", f"Expected 'hello', got {result}"
    print("✓ Test 1 passed: Direct string value")

    # Test 2: Direct integer value
    result = agent._decode_value(42)
    assert result == 42, f"Expected 42, got {result}"
    print("✓ Test 2 passed: Direct integer value")

    # Test 3: Hex-encoded MAC address
    mac_value = {"value": "\\x00\\x11\\x22\\x33\\x44\\x55", "encoding": "hex"}
    result = agent._decode_value(mac_value)
    expected = b"\x00\x11\x22\x33\x44\x55"
    assert result == expected, f"Expected {expected!r}, got {result!r}"
    print(f"✓ Test 3 passed: Hex-encoded MAC address: {result.hex(':')}")

    # Test 4: Another hex-encoded value
    mac_value2 = {"value": "\\xAA\\xBB\\xCC\\xDD\\xEE\\xFF", "encoding": "hex"}
    result = agent._decode_value(mac_value2)
    expected = b"\xaa\xbb\xcc\xdd\xee\xff"
    assert result == expected, f"Expected {expected!r}, got {result!r}"
    print(f"✓ Test 4 passed: Another hex-encoded value: {result.hex(':')}")

    # Test 5: Dict without encoding (should return as-is)
    plain_dict = {"foo": "bar"}
    result = agent._decode_value(plain_dict)
    assert result == plain_dict, f"Expected {plain_dict}, got {result}"
    print("✓ Test 5 passed: Plain dict without encoding")

    # Test 6: All zeros MAC address
    mac_value3 = {"value": "\\x00\\x00\\x00\\x00\\x00\\x00", "encoding": "hex"}
    result = agent._decode_value(mac_value3)
    expected = b"\x00\x00\x00\x00\x00\x00"
    assert result == expected, f"Expected {expected!r}, got {result!r}"
    print(f"✓ Test 6 passed: All zeros MAC address: {result.hex(':')}")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    try:
        test_decode_value()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
