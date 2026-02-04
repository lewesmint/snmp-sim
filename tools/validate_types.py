#!/usr/bin/env python3
"""
[DEPRECATED] This tool has been moved into the app module.

Please use app.type_registry_validator.validate_type_registry_file() instead.
This file is kept for backward compatibility but may be removed in the future.

For API access, use the /validate-types endpoint.
"""
import sys
import json
from pathlib import Path
import warnings

warnings.warn(
    "tools/validate_types.py is deprecated. Use app.type_registry_validator instead.",
    DeprecationWarning,
    stacklevel=2
)

def validate_types(json_path: str) -> int:
    """Validate type registry JSON file."""
    path = Path(json_path)
    
    if not path.exists():
        print(f"ERROR: Type registry file not found: {json_path}", file=sys.stderr)
        return 1
    
    try:
        with open(path) as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            print(f"ERROR: Type registry must be a dictionary", file=sys.stderr)
            return 1
        
        print(f"✓ Type registry validated: {len(data)} types found")
        return 0
    
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in type registry: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Failed to validate type registry: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <types.json>", file=sys.stderr)
        sys.exit(1)
    
    sys.exit(validate_types(sys.argv[1]))
