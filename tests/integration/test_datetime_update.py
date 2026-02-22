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

    # Decode to verify
    int.from_bytes(octets[0:2], "big")
    octets[2]
    octets[3]
    octets[4]
    octets[5]
    octets[6]
    octets[7]
    octets[8]
    octets[9]
    octets[10]


if __name__ == "__main__":
    test_date_and_time()
