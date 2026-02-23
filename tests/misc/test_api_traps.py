"""Tests for trap-related API endpoints."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

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
    api_state.state.snmp_agent = object()

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
