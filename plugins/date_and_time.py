"""DateAndTime TEXTUAL-CONVENTION plugin for proper SNMP octet encoding."""

from typing import Union
from datetime import datetime
from plugins.type_encoders import register_type_encoder


def _format_date_and_time(value: Union[str, bytes, None]) -> bytes:
    """Convert a value to DateAndTime octets.

    DateAndTime is an OCTET STRING of 8 or 11 octets representing:
    - Year (2 bytes, big-endian, e.g., 2025)
    - Month (1 byte, 1-12)
    - Day (1 byte, 1-31)
    - Hour (1 byte, 0-23)
    - Minute (1 byte, 0-59)
    - Second (1 byte, 0-59)
    - Deciseconds (1 byte, 0-9)
    - UTC sign (1 byte, '+' = 0x2B, '-' = 0x2D) (optional, included for RFC compliance)
    - UTC hours offset (1 byte, 0-12) (optional, included for RFC compliance)
    - UTC minutes offset (1 byte, 0-59) (optional, included for RFC compliance)

    Returns 11-octet format with UTC+0:0 timezone for RFC 2579 compliance.

    If value is "unset", empty string, None, or "unknown", returns current time.
    If value is already bytes with 8+ octets, return as-is.
    If value is a datetime string, parse and format it.

    Args:
        value: The value to format (string, bytes, or None)

    Returns:
        11-byte DateAndTime octet string (year, month, day, hour, minute, second, deciseconds, +, 0, 0)
    """
    # If already bytes with valid length, return as-is
    if isinstance(value, bytes):
        if len(value) >= 8:
            return value

    # Default to current time if unset/None/empty
    if value in [None, "unset", "", "unknown"]:
        now = datetime.utcnow()
    else:
        # Try to parse the value as a datetime string
        try:
            if isinstance(value, str):
                # Try ISO format first (handle comma as time separator)
                now = datetime.fromisoformat(value.replace(",", "T"))
            else:
                now = datetime.utcnow()
        except (ValueError, AttributeError):
            # If parsing fails, use current time
            now = datetime.utcnow()

    # Encode as 11 octets (8 + timezone):
    # year(2), month(1), day(1), hour(1), minute(1), second(1), deciseconds(1)
    # plus UTC sign (0x2B for '+'), hours offset (0), minutes offset (0)
    year_bytes = now.year.to_bytes(2, byteorder="big")
    octets = year_bytes + bytes(
        [now.month, now.day, now.hour, now.minute, now.second, 0]
    )
    # Add UTC timezone: '+' (0x2B) for UTC+0:0
    octets += bytes([0x2B, 0, 0])  # +0:0
    return octets


# Register the converter when module is imported
register_type_encoder("DateAndTime", _format_date_and_time)
