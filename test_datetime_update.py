#!/usr/bin/env python3
"""Test the updated DateAndTime encoding."""

from datetime import datetime

def test_date_and_time() -> None:
    now = datetime.utcnow()
    year_bytes = now.year.to_bytes(2, byteorder='big')
    octets = year_bytes + bytes([now.month, now.day, now.hour, now.minute, now.second, 0])
    # Add UTC timezone: '+' (0x2B) for UTC+0:0
    octets += bytes([0x2B, 0, 0])
    
    print(f"Length: {len(octets)} octets (should be 11)")
    print(f"Hex: {octets.hex()}")
    
    # Decode to verify
    year = int.from_bytes(octets[0:2], 'big')
    month = octets[2]
    day = octets[3]
    hour = octets[4]
    minute = octets[5]
    second = octets[6]
    deciseconds = octets[7]
    sign_byte = octets[8]
    tz_hour = octets[9]
    tz_min = octets[10]
    
    sign = '+' if sign_byte == 0x2B else '-'
    formatted = f'{year}-{month}-{day},{hour}:{minute}:{second}.{deciseconds}{sign}{tz_hour}:{tz_min}'
    print(f"Formatted: {formatted}")
    print("Expected:  2026-2-5,19:xx:xx.0+0:0")

if __name__ == '__main__':
    test_date_and_time()
