"""Validator for the type registry. Checks for structure, required fields, and type consistency."""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_EXPECTED_ARGC = 2
_USAGE_EXIT_CODE = 2


def validate_type_registry(registry: dict[str, dict[str, object]]) -> tuple[bool, list[str]]:
    """Validate type registry structure and contents.

    Args:
        registry: Dictionary containing type registry data

    Returns:
        Tuple of (is_valid, error_messages)

    """
    required_fields = {"base_type", "used_by", "defined_in", "abstract"}
    errors = []

    for type_name, entry in registry.items():
        missing = required_fields - set(entry.keys())
        if missing:
            errors.append(f"Type {type_name} missing fields: {', '.join(missing)}")
        if not isinstance(entry.get("base_type"), (str, type(None))):
            errors.append(f"Type {type_name} 'base_type' must be a string or null")
        if not isinstance(entry.get("used_by"), list):
            errors.append(f"Type {type_name} 'used_by' must be a list")
        if not isinstance(entry.get("defined_in"), (str, type(None))):
            errors.append(f"Type {type_name} 'defined_in' must be a string or null")
        if not isinstance(entry.get("abstract"), bool):
            errors.append(f"Type {type_name} 'abstract' must be a boolean")

    return len(errors) == 0, errors


def validate_type_registry_file(json_path: str) -> tuple[bool, list[str], int]:
    """Validate type registry from JSON file.

    Args:
        json_path: Path to the type registry JSON file

    Returns:
        Tuple of (is_valid, error_messages, type_count)

    """
    path = Path(json_path)

    if not path.exists():
        return False, [f"Type registry file not found: {json_path}"], 0

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return False, ["Type registry must be a dictionary"], 0

        normalized: dict[str, dict[str, object]] = {}
        for type_name, entry in data.items():
            if not isinstance(type_name, str) or not isinstance(entry, dict):
                return False, ["Type registry must map string names to object entries"], 0
            normalized[type_name] = entry

        is_valid, errors = validate_type_registry(normalized)
        return is_valid, errors, len(normalized)

    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in type registry: {e}"], 0
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        return False, [f"Failed to validate type registry: {e}"], 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) != _EXPECTED_ARGC:
        logger.error("Usage: %s <types.json>", sys.argv[0])
        sys.exit(_USAGE_EXIT_CODE)
    with Path(sys.argv[1]).open(encoding="utf-8") as json_file:
        registry_data = json.load(json_file)
    validate_type_registry(registry_data)
