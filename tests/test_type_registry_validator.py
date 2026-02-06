import json
from pathlib import Path


from app.type_registry_validator import (
    validate_type_registry,
    validate_type_registry_file,
)


def test_validate_type_registry_valid() -> None:
    registry = {
        "MyType": {
            "base_type": "Integer",
            "used_by": [],
            "defined_in": "MY-MIB",
            "abstract": False,
        }
    }

    is_valid, errors = validate_type_registry(registry)

    assert is_valid is True
    assert errors == []


def test_validate_type_registry_missing_fields() -> None:
    registry = {"T": {"base_type": "Integer"}}

    is_valid, errors = validate_type_registry(registry)

    assert is_valid is False
    assert any("missing fields" in e for e in errors)
    assert "used_by" in ", ".join(errors) or ""


def test_validate_type_registry_wrong_types() -> None:
    registry = {
        "T": {
            "base_type": 123,
            "used_by": "not-a-list",
            "defined_in": 456,
            "abstract": "nope",
        }
    }

    is_valid, errors = validate_type_registry(registry)

    assert is_valid is False
    assert any("'base_type' must be a string or null" in e for e in errors)
    assert any("'used_by' must be a list" in e for e in errors)
    assert any("'defined_in' must be a string or null" in e for e in errors)
    assert any("'abstract' must be a boolean" in e for e in errors)


def test_validate_type_registry_file_not_found(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.json"

    is_valid, errors, count = validate_type_registry_file(str(path))

    assert is_valid is False
    assert count == 0
    assert any("not found" in e for e in errors)


def test_validate_type_registry_file_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{ not valid json }")

    is_valid, errors, count = validate_type_registry_file(str(path))

    assert is_valid is False
    assert count == 0
    assert any("Invalid JSON in type registry" in e for e in errors)


def test_validate_type_registry_file_not_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]))

    is_valid, errors, count = validate_type_registry_file(str(path))

    assert is_valid is False
    assert count == 0
    assert any("must be a dictionary" in e for e in errors)


def test_validate_type_registry_file_open_error(tmp_path: Path) -> None:
    # Pass a directory path to provoke an OSError when opening as a file
    is_valid, errors, count = validate_type_registry_file(str(tmp_path))

    assert is_valid is False
    assert count == 0
    assert any("Failed to validate type registry" in e for e in errors)
