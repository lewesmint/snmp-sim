# Value Encoding in Schema JSON

## Overview

The SNMP simulator uses a three-file architecture (British spelling):
- **schema.json** - Structure + initial values (generated)
- **behaviour.json** - Dynamic functions (optional, user-created)
- **values.json** - Runtime state (created by agent)

This document describes value encoding in **schema.json** files.

The SNMP simulator supports two formats for values in schema JSON files:

1. **Direct values** - Simple types like strings, integers, etc.
2. **Encoded values** - Complex binary data represented as dictionaries with encoding metadata

## Direct Values

Most values can be represented directly:

```json
{
  "myTestName": "Interface One",
  "myTestCounter": 12345,
  "myTestType": 1
}
```

## Encoded Values

For binary data (like MAC addresses, binary strings, etc.), use the encoded format:

```json
{
  "myTestMacAddress": {
    "value": "\\x00\\x11\\x22\\x33\\x44\\x55",
    "encoding": "hex"
  }
}
```

### Structure

An encoded value is a dictionary with two required keys:

- `value`: The encoded representation as a string
- `encoding`: The encoding type (currently supports `"hex"`)

### Hex Encoding

Hex encoding uses Python binary string escape sequences:

```json
{
  "value": "\\xAA\\xBB\\xCC\\xDD\\xEE\\xFF",
  "encoding": "hex"
}
```

**Important**: In JSON, backslashes must be escaped, so `\x` becomes `\\x`.

When the agent reads this value, it:
1. Detects it's a dictionary with `value` and `encoding` keys
2. Decodes the hex escape sequences to bytes
3. Passes the bytes to PySNMP

### Examples

#### MAC Address (6 bytes)
```json
"myMacAddress": {
  "value": "\\x00\\x11\\x22\\x33\\x44\\x55",
  "encoding": "hex"
}
```
Decodes to: `b'\x00\x11\x22\x33\x44\x55'` (00:11:22:33:44:55)

#### All Zeros
```json
"myMacAddress": {
  "value": "\\x00\\x00\\x00\\x00\\x00\\x00",
  "encoding": "hex"
}
```
Decodes to: `b'\x00\x00\x00\x00\x00\x00'` (00:00:00:00:00:00)

#### Arbitrary Binary Data
```json
"myBinaryData": {
  "value": "\\x01\\x02\\x03\\x04",
  "encoding": "hex"
}
```
Decodes to: `b'\x01\x02\x03\x04'`

## Implementation

### Agent Side (`app/snmp_agent.py`)

The `_decode_value()` method handles decoding:

```python
def _decode_value(self, value: Any) -> Any:
    """Decode a value that may be in encoded format."""
    # If not a dict, return as-is
    if not isinstance(value, dict):
        return value
    
    # Check for encoding format
    if "value" not in value or "encoding" not in value:
        return value
    
    # Decode based on encoding type
    if value["encoding"] == "hex":
        # Convert escape sequences to bytes
        return value["value"].encode('utf-8').decode('unicode_escape').encode('latin1')
    
    return value["value"]
```

This method is called for both scalar and table values before passing them to PySNMP.

### Generator Side (`app/generator.py`)

The generator creates schema JSON files but doesn't currently auto-generate encoded values. 
These are typically added manually when creating test data or behavior schemas.

## When to Use Encoded Values

Use encoded values for:

- **MAC addresses** (6 bytes)
- **Binary OCTET STRINGs** that aren't human-readable text
- **Raw binary data** that needs exact byte representation
- **Special characters** that can't be represented in JSON strings

Use direct values for:

- **Integers** (all integer types)
- **Text strings** (DisplayString, SnmpAdminString, etc.)
- **IP addresses** (can use string format like "192.168.1.1")
- **OIDs** (can use string format like "1.3.6.1.2.1")

## Future Encodings

The system is designed to support additional encodings in the future:

- `"base64"` - Base64-encoded binary data
- `"ascii"` - ASCII text with escape sequences
- `"utf8"` - UTF-8 encoded text

To add a new encoding, update the `_decode_value()` method in `app/snmp_agent.py`.

