"""
Validator for the type registry. Checks for structure, required fields, and type consistency.
"""

import json
import sys
from typing import Dict, Any, List, Tuple
from pathlib import Path

def validate_type_registry(registry: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate type registry structure and contents.
    
    Args:
        registry: Dictionary containing type registry data
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
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
    
    return len(errors) == 0, errors

def validate_type_registry_file(json_path: str) -> Tuple[bool, List[str], int]:
    """
    Validate type registry from JSON file.
    
    Args:
        json_path: Path to the type registry JSON file
        
    Returns:
        Tuple of (is_valid, error_messages, type_count)
    """
    path = Path(json_path)
    
    if not path.exists():
        return False, [f"Type registry file not found: {json_path}"], 0
    
    try:
        with open(path) as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return False, ["Type registry must be a dictionary"], 0
        
        is_valid, errors = validate_type_registry(data)
        return is_valid, errors, len(data)
        
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in type registry: {e}"], 0
    except Exception as e:
        return False, [f"Failed to validate type registry: {e}"], 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <types.json>")
        sys.exit(2)
    with open(sys.argv[1]) as f:
        registry = json.load(f)
    validate_type_registry(registry)
