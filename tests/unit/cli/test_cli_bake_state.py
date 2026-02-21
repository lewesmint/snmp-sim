"""Tests for CLI state baking tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli_bake_state import (
    backup_schemas,
    bake_state_into_schemas,
    load_mib_state,
    main,
)


def test_backup_schemas_existing_and_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schema_dir = tmp_path / "agent-model"
    backup_base = tmp_path / "backups"

    schema_dir.mkdir(parents=True)
    (schema_dir / "MIB-A").mkdir(parents=True)
    (schema_dir / "MIB-A" / "schema.json").write_text("{}", encoding="utf-8")

    backup_dir = backup_schemas(schema_dir, backup_base)
    out = capsys.readouterr()
    assert backup_dir.exists()
    assert (backup_dir / "MIB-A" / "schema.json").exists()
    assert "Backup created" in out.out

    missing_dir = tmp_path / "missing-agent-model"
    backup_dir2 = backup_schemas(missing_dir, backup_base)
    out2 = capsys.readouterr()
    assert backup_dir2.parent == backup_base
    assert "does not exist, skipping backup" in out2.out


def test_load_mib_state_missing_and_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "mib_state.json"
    state_missing = load_mib_state(missing)
    out_missing = capsys.readouterr()
    assert state_missing == {"scalars": {}, "tables": {}, "deleted_instances": []}
    assert "does not exist" in out_missing.out

    present = tmp_path / "present_state.json"
    expected = {
        "scalars": {"1.2.3": 1},
        "tables": {"1.2.4": {}},
        "deleted_instances": ["1.2.4.9"],
    }
    present.write_text(json.dumps(expected), encoding="utf-8")
    assert load_mib_state(present) == expected


def test_bake_state_into_schemas_scalars_and_tables(tmp_path: Path) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "IF-MIB"
    mib_dir.mkdir(parents=True)

    schema = {
        "objects": {
            "sysDescr": {"oid": [1, 3, 6, 1, 2, 1, 1, 1], "type": "DisplayString"},
            "ipAddrTable": {
                "oid": [1, 3, 6, 1, 2, 1, 4, 20],
                "type": "MibTable",
                "rows": [],
            },
            "ipAddrEntry": {
                "oid": [1, 3, 6, 1, 2, 1, 4, 20, 1],
                "type": "MibTableRow",
                "indexes": ["ipAdEntAddr", "ifIndex"],
            },
            "ipAdEntAddr": {
                "oid": [1, 3, 6, 1, 2, 1, 4, 20, 1, 1],
                "type": "IpAddress",
            },
            "ifIndex": {"oid": [1, 3, 6, 1, 2, 1, 4, 20, 1, 2], "type": "Integer32"},
            "ipAdEntIfIndex": {
                "oid": [1, 3, 6, 1, 2, 1, 4, 20, 1, 2],
                "type": "Integer32",
            },
        }
    }
    schema_file = mib_dir / "schema.json"
    schema_file.write_text(json.dumps(schema), encoding="utf-8")

    state = {
        "scalars": {"1.3.6.1.2.1.1.1": "new-sysdescr"},
        "tables": {
            "1.3.6.1.2.1.4.20": {
                "10.0.0.1.7": {
                    "column_values": {
                        "ipAdEntIfIndex": 7,
                        "ipAdEntAddr": "10.0.0.1",
                    }
                }
            }
        },
        "deleted_instances": [],
    }

    baked_count = bake_state_into_schemas(schema_dir, state)
    assert baked_count >= 2

    updated = json.loads(schema_file.read_text(encoding="utf-8"))
    objects = updated["objects"]
    assert objects["sysDescr"]["initial"] == "new-sysdescr"
    assert len(objects["ipAddrTable"]["rows"]) == 1
    row = objects["ipAddrTable"]["rows"][0]
    assert row["ipAdEntAddr"] == "10.0.0.1"
    assert row["ifIndex"] == 7


def test_bake_state_handles_index_sentinel_and_bad_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "TEST-MIB"
    bad_dir = schema_dir / "BAD-MIB"
    mib_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)

    schema = {
        "objects": {
            "testTable": {
                "oid": [1, 3, 6, 1, 4, 1, 99999, 1],
                "type": "MibTable",
                "rows": [],
            },
            "testEntry": {
                "oid": [1, 3, 6, 1, 4, 1, 99999, 1, 1],
                "type": "MibTableRow",
                "indexes": ["__index__"],
            },
        }
    }
    (mib_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (bad_dir / "schema.json").write_text("{bad json", encoding="utf-8")

    state = {
        "scalars": {},
        "tables": {
            "1.3.6.1.4.1.99999.1": {"custom.idx": {"column_values": {"someCol": "v"}}}
        },
        "deleted_instances": [],
    }

    baked_count = bake_state_into_schemas(schema_dir, state)
    out = capsys.readouterr()

    assert baked_count == 1
    assert "Error processing" in out.err

    updated = json.loads((mib_dir / "schema.json").read_text(encoding="utf-8"))
    rows = updated["objects"]["testTable"]["rows"]
    assert rows[0]["__index__"] == "custom.idx"
    assert rows[0]["someCol"] == "v"


def test_main_no_backup_bakes_and_clears_state(tmp_path: Path) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "SNMPv2-MIB"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    mib_dir.mkdir(parents=True)

    schema = {
        "objects": {
            "sysContact": {"oid": [1, 3, 6, 1, 2, 1, 1, 4], "type": "DisplayString"}
        }
    }
    (mib_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")

    state_file = data_dir / "mib_state.json"
    state_file.write_text(
        json.dumps(
            {
                "scalars": {"1.3.6.1.2.1.1.4": "admin@example.com"},
                "tables": {},
                "deleted_instances": [],
            }
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--schema-dir",
            str(schema_dir),
            "--state-file",
            str(state_file),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--no-backup",
        ]
    )

    assert code == 0
    updated_schema = json.loads((mib_dir / "schema.json").read_text(encoding="utf-8"))
    assert updated_schema["objects"]["sysContact"]["initial"] == "admin@example.com"

    cleared_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert cleared_state == {"scalars": {}, "tables": {}, "deleted_instances": []}


def test_bake_state_legacy_index_values_format(tmp_path: Path) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "LEGACY-MIB"
    mib_dir.mkdir(parents=True)

    schema = {
        "objects": {
            "legacyTable": {
                "oid": [1, 3, 6, 1, 4, 1, 99999, 2],
                "type": "MibTable",
                "rows": [],
            },
            "legacyEntry": {
                "oid": [1, 3, 6, 1, 4, 1, 99999, 2, 1],
                "type": "MibTableRow",
                "indexes": "not-a-list",
            },
        }
    }
    schema_file = mib_dir / "schema.json"
    schema_file.write_text(json.dumps(schema), encoding="utf-8")

    state = {
        "scalars": {},
        "tables": {
            "1.3.6.1.4.1.99999.2": {
                "1": {"index_values": {"legacyIndex": 1, "legacyCol": "x"}}
            }
        },
        "deleted_instances": [],
    }

    baked_count = bake_state_into_schemas(schema_dir, state)
    assert baked_count == 1

    updated = json.loads(schema_file.read_text(encoding="utf-8"))
    rows = updated["objects"]["legacyTable"]["rows"]
    assert rows[0]["legacyIndex"] == 1
    assert rows[0]["legacyCol"] == "x"


def test_main_with_backup_enabled_creates_backup_and_clears_state(
    tmp_path: Path,
) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "TEST-MIB"
    backup_dir = tmp_path / "agent-model-backups"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    mib_dir.mkdir(parents=True)

    (mib_dir / "schema.json").write_text(
        json.dumps({"objects": {"objA": {"oid": [1, 2, 3], "type": "Integer32"}}}),
        encoding="utf-8",
    )
    state_file = data_dir / "mib_state.json"
    state_file.write_text(
        json.dumps({"scalars": {}, "tables": {}, "deleted_instances": []}),
        encoding="utf-8",
    )

    code = main(
        [
            "--schema-dir",
            str(schema_dir),
            "--state-file",
            str(state_file),
            "--backup-dir",
            str(backup_dir),
        ]
    )

    assert code == 0
    assert backup_dir.exists()
    assert any(p.is_dir() for p in backup_dir.iterdir())
    assert json.loads(state_file.read_text(encoding="utf-8")) == {
        "scalars": {},
        "tables": {},
        "deleted_instances": [],
    }


def test_bake_state_flat_schema_structure_and_non_dict_table_entries(
    tmp_path: Path,
) -> None:
    schema_dir = tmp_path / "agent-model"
    mib_dir = schema_dir / "FLAT-MIB"
    mib_dir.mkdir(parents=True)

    # Flat schema (without top-level "objects") should still be supported
    flat_schema = {
        "flatScalar": {"oid": [1, 3, 6, 1, 4, 1, 9, 9], "type": "Integer32"},
        "flatTable": {"oid": [1, 3, 6, 1, 4, 1, 9, 10], "type": "MibTable", "rows": []},
        "flatEntry": {
            "oid": [1, 3, 6, 1, 4, 1, 9, 10, 1],
            "type": "MibTableRow",
            "indexes": ["idx"],
        },
        "idx": {"oid": [1, 3, 6, 1, 4, 1, 9, 10, 1, 1], "type": "Integer32"},
    }
    schema_file = mib_dir / "schema.json"
    schema_file.write_text(json.dumps(flat_schema), encoding="utf-8")

    state = {
        "scalars": {"1.3.6.1.4.1.9.9": 77},
        # non-dict entry should be skipped by bake loop
        "tables": {"1.3.6.1.4.1.9.10": ["not", "a", "dict"]},
        "deleted_instances": [],
    }

    baked_count = bake_state_into_schemas(schema_dir, state)
    assert baked_count == 1

    updated = json.loads(schema_file.read_text(encoding="utf-8"))
    assert updated["flatScalar"]["initial"] == 77
    assert updated["flatTable"]["rows"] == []
