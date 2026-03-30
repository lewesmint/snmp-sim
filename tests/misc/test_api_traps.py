"""Tests for trap-related API endpoints."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import api
from app import api_state

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def restore_snmp_agent() -> Generator[None, None, None]:
    """Restore SNMP agent state after each test."""
    original = api_state.state.snmp_agent
    api_state.state.snmp_agent = None
    yield
    api_state.state.snmp_agent = original


def test_trap_varbinds_includes_all_index_column_metadata(monkeypatch: Any, tmp_path: Path) -> None:
    """Trap varbind metadata includes IpAddress+port index types for multi-index tables."""
    api_state.state.snmp_agent = MagicMock(snmp_engine=object())

    monkeypatch.setattr("app.api_traps.SCHEMA_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)

    base_oid = [1, 3, 6, 1, 4, 1, 9999, 1]
    row_oid = base_oid + [1]

    fake_schemas = {
        "TEST-ENDPOINT-MIB": {
            "traps": {
                "endPointStatusChange": {
                    "objects": [{"mib": "TEST-ENDPOINT-MIB", "name": "endPointStatus"}],
                },
            },
            "objects": {
                "endPointTable": {
                    "oid": base_oid,
                    "type": "MibTable",
                    "instances": ["192.168.10.25.162"],
                },
                "endPointEntry": {
                    "oid": row_oid,
                    "type": "MibTableRow",
                    "indexes": ["endPointAddr", "endPointPort"],
                },
                "endPointStatus": {
                    "oid": row_oid + [3],
                    "type": "Integer32",
                    "access": "read-write",
                },
                "endPointAddr": {
                    "oid": row_oid + [1],
                    "type": "IpAddress",
                    "access": "read-only",
                },
                "endPointPort": {
                    "oid": row_oid + [2],
                    "type": "Integer32",
                    "access": "read-only",
                },
            },
        },
    }

    monkeypatch.setattr("app.api_traps.load_all_schemas", lambda _schema_dir: fake_schemas)

    response = client.get("/trap-varbinds/endPointStatusChange")
    assert response.status_code == 200

    body = response.json()
    assert body["index_columns"] == ["endPointAddr", "endPointPort"]
    assert body["instances"] == ["192.168.10.25.162"]
    assert body["columns_meta"]["endPointAddr"]["type"] == "IpAddress"
    assert body["columns_meta"]["endPointPort"]["type"] == "Integer32"


def test_commands_completion_sets_values_and_sends(monkeypatch: Any, tmp_path: Path) -> None:
    """Completion command endpoint applies varbind values then sends completionTrap."""
    fake_agent = MagicMock(snmp_engine=object())
    api_state.state.snmp_agent = fake_agent

    monkeypatch.setattr("app.api_traps.SCHEMA_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)

    fake_schemas = {
        "TEST-ENUM-MIB": {
            "traps": {
                "completionTrap": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 0, 2],
                    "objects": [
                        {"mib": "TEST-ENUM-MIB", "name": "completionSource"},
                        {"mib": "TEST-ENUM-MIB", "name": "completionCode"},
                    ],
                }
            },
            "objects": {
                "completionSource": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 1, 1, 3],
                    "type": "DisplayString",
                    "access": "accessible-for-notify",
                },
                "completionCode": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 1, 1, 4],
                    "type": "Integer32",
                    "access": "accessible-for-notify",
                },
            },
        }
    }

    monkeypatch.setattr("app.api_traps.load_all_schemas", lambda _schema_dir: fake_schemas)
    monkeypatch.setattr("app.api_traps._resolve_notification_or_raise", lambda *_args, **_kwargs: object())

    async def _fake_send(**_kwargs: Any) -> tuple[object, object, object, object]:
        return (None, None, None, None)

    monkeypatch.setattr("app.api_traps._send_notification_or_raise", _fake_send)

    response = client.post(
        "/commands/completion",
        json={
            "completion_source": "CLI",
            "completion_code": 200,
            "dest_host": "localhost",
            "dest_port": 16662,
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["trap_name"] == "completionTrap"
    assert len(body["applied_values"]) == 2
    assert {item["name"] for item in body["applied_values"]} == {
        "completionSource",
        "completionCode",
    }
    fake_agent.set_scalar_value.assert_any_call((1, 3, 6, 1, 4, 1, 99998, 1, 1, 3), "CLI")
    fake_agent.set_scalar_value.assert_any_call((1, 3, 6, 1, 4, 1, 99998, 1, 1, 4), "200")


def test_commands_event_sets_values_and_sends(monkeypatch: Any, tmp_path: Path) -> None:
    """Event command endpoint applies varbind values then sends eventTrap."""
    fake_agent = MagicMock(snmp_engine=object())
    api_state.state.snmp_agent = fake_agent

    monkeypatch.setattr("app.api_traps.SCHEMA_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)

    fake_schemas = {
        "TEST-ENUM-MIB": {
            "traps": {
                "eventTrap": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 0, 3],
                    "objects": [
                        {"mib": "TEST-ENUM-MIB", "name": "eventSeverity"},
                        {"mib": "TEST-ENUM-MIB", "name": "eventText"},
                    ],
                }
            },
            "objects": {
                "eventSeverity": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 1, 1, 5],
                    "type": "Integer32",
                    "access": "accessible-for-notify",
                },
                "eventText": {
                    "oid": [1, 3, 6, 1, 4, 1, 99998, 1, 1, 6],
                    "type": "DisplayString",
                    "access": "accessible-for-notify",
                },
            },
        }
    }

    monkeypatch.setattr("app.api_traps.load_all_schemas", lambda _schema_dir: fake_schemas)
    monkeypatch.setattr("app.api_traps._resolve_notification_or_raise", lambda *_args, **_kwargs: object())

    async def _fake_send(**_kwargs: Any) -> tuple[object, object, object, object]:
        return (None, None, None, None)

    monkeypatch.setattr("app.api_traps._send_notification_or_raise", _fake_send)

    response = client.post(
        "/commands/event",
        json={
            "event_severity": 4,
            "event_text": "Power supply alarm",
            "dest_host": "localhost",
            "dest_port": 16662,
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["trap_name"] == "eventTrap"
    fake_agent.set_scalar_value.assert_any_call((1, 3, 6, 1, 4, 1, 99998, 1, 1, 5), "4")
    fake_agent.set_scalar_value.assert_any_call(
        (1, 3, 6, 1, 4, 1, 99998, 1, 1, 6),
        "Power supply alarm",
    )
