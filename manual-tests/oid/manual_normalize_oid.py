#!/usr/bin/env python3
"""Test the _normalize_oid helper function"""


def normalize_oid(oid: str) -> str:
    """Normalize OID to work with pysnmp.

    pysnmp requires OIDs with at least 2 numeric components.
    If a single-component OID is provided (e.g., "1", ".1"),
    append ".0" to make it valid.

    Args:
        oid: Original OID string

    Returns:
        Normalized OID string with at least 2 components
    """
    # Remove leading/trailing whitespace
    oid = oid.strip()

    # Count numeric components (split by dots, filter out empty strings)
    parts = [p for p in oid.split(".") if p]

    # If only one component, append .0
    if len(parts) == 1:
        # Return as "X.0" format
        return f"{oid.rstrip('.')}.0"

    return oid


# Test cases
test_cases = [
    ("1", "1.0", "Single digit"),
    (".1", ".1.0", "Dot prefix single digit"),
    ("2", "2.0", "Different single digit"),
    (".2", ".2.0", "Dot prefix different digit"),
    ("1.0", "1.0", "Already normalized"),
    ("1.3.6.1.2.1.1", "1.3.6.1.2.1.1", "Multi-component OID"),
    (".1.3.6.1.2.1.1", ".1.3.6.1.2.1.1", "Dot-prefixed multi-component"),
    (" 1 ", "1.0", "Single digit with spaces"),
    (" 1.0 ", "1.0", "Multi-component with spaces"),
    (".1.", ".1.0", "Dot prefix and suffix single digit"),
]

print("\n" + "=" * 70)
print("Testing _normalize_oid Helper Function")
print("=" * 70 + "\n")

all_pass = True
for input_oid, expected, description in test_cases:
    result = normalize_oid(input_oid)
    pass_fail = "✅ PASS" if result == expected else "❌ FAIL"
    if result != expected:
        all_pass = False
    print(f"{pass_fail} | {description:40} | '{input_oid}' → '{result}'")
    if result != expected:
        print(f"       Expected: '{expected}'")

print("\n" + "=" * 70)
print(f"Results: {'All tests passed!' if all_pass else 'Some tests failed!'}")
print("=" * 70 + "\n")
