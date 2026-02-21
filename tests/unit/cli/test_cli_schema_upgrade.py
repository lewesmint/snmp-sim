"""Tests for schema upgrade CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli_schema_upgrade import _iter_schema_files, main


def test_iter_schema_files_returns_sorted_paths(tmp_path: Path) -> None:
    base = tmp_path / "agent-model"
    (base / "B-MIB").mkdir(parents=True)
    (base / "A-MIB").mkdir(parents=True)
    (base / "B-MIB" / "schema.json").write_text("{}", encoding="utf-8")
    (base / "A-MIB" / "schema.json").write_text("{}", encoding="utf-8")

    files = _iter_schema_files(base)
    assert [p.parent.name for p in files] == ["A-MIB", "B-MIB"]


def test_main_returns_error_when_schema_dir_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--schema-dir", "does-not-exist"])
    out = capsys.readouterr()

    assert code == 1
    assert "Schema directory not found" in out.out


def test_main_returns_error_when_no_schema_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_dir = tmp_path / "agent-model"
    empty_dir.mkdir(parents=True)

    code = main(["--schema-dir", str(empty_dir)])
    out = capsys.readouterr()

    assert code == 1
    assert "No schema.json files found." in out.out


def test_main_updates_only_changed_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schema_dir = tmp_path / "agent-model"
    mib1 = schema_dir / "IF-MIB"
    mib2 = schema_dir / "SNMPv2-MIB"
    mib1.mkdir(parents=True)
    mib2.mkdir(parents=True)

    p1 = mib1 / "schema.json"
    p2 = mib2 / "schema.json"
    p1.write_text(json.dumps({"schema_version": "1.0.0", "objects": {}}), encoding="utf-8")
    p2.write_text(json.dumps({"schema_version": "1.0.1", "objects": {}}), encoding="utf-8")

    code = main(["--schema-dir", str(schema_dir), "--set-version", "1.0.1"])
    out = capsys.readouterr()

    assert code == 0
    assert "Updated 1 schema file(s) to version 1.0.1." in out.out
    assert json.loads(p1.read_text(encoding="utf-8"))["schema_version"] == "1.0.1"
    assert json.loads(p2.read_text(encoding="utf-8"))["schema_version"] == "1.0.1"


def test_main_skips_non_dict_json_and_handles_bad_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schema_dir = tmp_path / "agent-model"
    good = schema_dir / "GOOD-MIB"
    array_mib = schema_dir / "ARRAY-MIB"
    bad = schema_dir / "BAD-MIB"
    good.mkdir(parents=True)
    array_mib.mkdir(parents=True)
    bad.mkdir(parents=True)

    (good / "schema.json").write_text(json.dumps({"schema_version": "0.9.0"}), encoding="utf-8")
    (array_mib / "schema.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    (bad / "schema.json").write_text("{bad json", encoding="utf-8")

    code = main(["--schema-dir", str(schema_dir), "--set-version", "2.0.0"])
    out = capsys.readouterr()

    assert code == 0
    assert "Failed to update" in out.out
    assert "Updated 1 schema file(s) to version 2.0.0." in out.out
    assert (
        json.loads((good / "schema.json").read_text(encoding="utf-8"))["schema_version"] == "2.0.0"
    )
