"""Tests for test api."""

import json
from pathlib import Path
from typing import Dict, Any, Generator

import pytest
from fastapi.testclient import TestClient

from app import api

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def restore_snmp_agent() -> Generator[None, None, None]:
    """Test case for restore_snmp_agent."""
    # Ensure we don't leak a fake snmp_agent between tests
    original = getattr(api, "snmp_agent")
    api.snmp_agent = None
    yield
    api.snmp_agent = original


@pytest.fixture
def backup_types_json(tmp_path: Any, monkeypatch: Any) -> Generator[None, None, None]:
    """Test case for backup_types_json."""
    # Back up existing data/types.json if present and restore after test
    data_path = Path("data") / "types.json"
    backup = None
    if data_path.exists():
        backup = data_path.read_text()
    yield
    if backup is None:
        try:
            data_path.unlink()
        except Exception:
            pass
    else:
        data_path.write_text(backup)


def test_get_sysdescr_agent_not_initialized() -> None:
    """Test case for test_get_sysdescr_agent_not_initialized."""
    r = client.get("/sysdescr")
    assert r.status_code == 500
    assert "SNMP agent not initialized" in r.json()["detail"]


def test_get_and_set_sysdescr_happy_path(mocker: Any) -> None:
    """Test case for test_get_and_set_sysdescr_happy_path."""
    fake = mocker.MagicMock()
    oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
    fake.get_scalar_value.return_value = "My system"
    api.snmp_agent = fake

    r = client.get("/sysdescr")
    assert r.status_code == 200
    # JSON returns lists for sequences; accept either
    assert tuple(r.json()["oid"]) == oid
    assert r.json()["value"] == "My system"

    r2 = client.post("/sysdescr", json={"value": "New desc"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "ok"
    fake.set_scalar_value.assert_called_with(oid, "New desc")


def test_validate_types_invalid(monkeypatch: Any) -> None:
    """Test case for test_validate_types_invalid."""
    # Patch validator to return invalid
    monkeypatch.setattr(
        "app.type_registry_validator.validate_type_registry_file",
        lambda p: (False, ["err1"], 0),
    )
    r = client.get("/validate-types")
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["valid"] is False
    assert "err1" in body["detail"]["errors"]


def test_validate_types_valid(monkeypatch: Any) -> None:
    """Test case for test_validate_types_valid."""
    monkeypatch.setattr(
        "app.type_registry_validator.validate_type_registry_file",
        lambda p: (True, [], 42),
    )
    r = client.get("/validate-types")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["type_count"] == 42


def test_get_type_info_not_found(backup_types_json: Any) -> None:
    """Test case for test_get_type_info_not_found."""
    # Write a minimal registry that does not contain FooType
    Path("data").mkdir(exist_ok=True)
    Path("data/types.json").write_text(json.dumps({"Bar": {"base_type": "Integer32"}}))

    r = client.get("/type-info/FooType")
    assert r.status_code == 404


def test_get_type_info_found(backup_types_json: Any) -> None:
    """Test case for test_get_type_info_found."""
    # Prepare a registry where DisplayString -> OctetString and OctetString -> OCTET STRING
    Path("data").mkdir(exist_ok=True)
    registry: Dict[str, Any] = {
        "DisplayString": {"base_type": "OctetString", "display_hint": "255a"},
        "OctetString": {"base_type": "OCTET STRING"},
    }
    Path("data/types.json").write_text(json.dumps(registry))

    r = client.get("/type-info/DisplayString")
    assert r.status_code == 200
    body = r.json()
    assert body["type_name"] == "DisplayString"
    assert body["base_asn1_type"] == "OCTET STRING"
    assert body["type_info"]["display_hint"] == "255a"


def test_list_types(backup_types_json: Any) -> None:
    """Test case for test_list_types."""
    Path("data").mkdir(exist_ok=True)
    registry: Dict[str, Any] = {"A": {}, "B": {}, "C": {}}
    Path("data/types.json").write_text(json.dumps(registry))

    r = client.get("/types")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["types"] == sorted(["A", "B", "C"])
