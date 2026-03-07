#!/usr/bin/env python3
"""Test the updated DateAndTime encoding."""

from datetime import datetime


def test_date_and_time() -> None:
    """Test case for test_date_and_time."""
    now = datetime.utcnow()
    year_bytes = now.year.to_bytes(2, byteorder="big")
    octets = year_bytes + bytes([now.month, now.day, now.hour, now.minute, now.second, 0])
    # Add UTC timezone: '+' (0x2B) for UTC+0:0
    octets += bytes([0x2B, 0, 0])

    # Decode and verify RFC2579 DateAndTime components
    assert len(octets) == 11
    assert int.from_bytes(octets[0:2], "big") == now.year
    assert octets[2] == now.month
    assert octets[3] == now.day
    assert octets[4] == now.hour
    assert octets[5] == now.minute
    assert octets[6] == now.second
    assert octets[7] == 0  # deci-seconds
    assert octets[8] == 0x2B  # '+'
    assert octets[9] == 0  # UTC offset hours
    assert octets[10] == 0  # UTC offset minutes


if __name__ == "__main__":
    test_date_and_time()
