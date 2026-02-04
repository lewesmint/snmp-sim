"""
Validator for the type registry. Checks for structure, required fields, and type consistency.
"""

import json
import sys
from typing import Dict, Any

def validate_type_registry(registry: Dict[str, Any]) -> None:
    required_fields = {"name", "syntax", "description"}
    errors = []
    for oid, entry in registry.items():
        missing = required_fields - set(entry.keys())
        if missing:
            errors.append(f"OID {oid} missing fields: {', '.join(missing)}")
        if not isinstance(entry.get("name"), str):
            errors.append(f"OID {oid} 'name' must be a string")
        if not isinstance(entry.get("syntax"), str):
            errors.append(f"OID {oid} 'syntax' must be a string")
        if not isinstance(entry.get("description"), str):
            errors.append(f"OID {oid} 'description' must be a string")
    if errors:
        print("Validation errors found:")
        for err in errors:
            print(" -", err)
        sys.exit(1)
    print("Type registry validation passed.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <types.json>")
        sys.exit(2)
    with open(sys.argv[1]) as f:
        registry = json.load(f)
    validate_type_registry(registry)
