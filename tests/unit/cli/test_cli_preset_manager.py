"""Tests for preset manager CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli_preset_manager import (
    delete_preset,
    list_presets,
    load_preset,
    main,
    save_preset,
)


def test_list_presets_returns_sorted_names(tmp_path: Path) -> None:
    """Test case for test_list_presets_returns_sorted_names."""
    preset_base = tmp_path / "presets"
    assert list_presets(preset_base) == []

    (preset_base / "zeta").mkdir(parents=True)
    (preset_base / "alpha").mkdir(parents=True)
    (preset_base / "not_a_dir.txt").write_text("x", encoding="utf-8")

    assert list_presets(preset_base) == ["alpha", "zeta"]


def test_save_preset_missing_schema_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test case for test_save_preset_missing_schema_dir."""
    code = save_preset(tmp_path / "agent-model", tmp_path / "presets", "test")
    out = capsys.readouterr()
    assert code == 1
    assert "does not exist" in out.err


def test_save_preset_creates_copy_and_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test case for test_save_preset_creates_copy_and_metadata."""
    schema_dir = tmp_path / "agent-model"
    schema_dir.mkdir(parents=True)
    (schema_dir / "A-MIB").mkdir(parents=True)
    (schema_dir / "A-MIB" / "schema.json").write_text('{"x":1}', encoding="utf-8")

    preset_base = tmp_path / "presets"
    code = save_preset(schema_dir, preset_base, "baseline")
    out = capsys.readouterr()

    assert code == 0
    preset_dir = preset_base / "baseline"
    assert (preset_dir / "A-MIB" / "schema.json").exists()
    metadata = json.loads((preset_dir / "preset_metadata.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "baseline"
    assert "created" in metadata
    assert "saved" in out.out


def test_save_preset_existing_cancel_or_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test case for test_save_preset_existing_cancel_or_overwrite."""
    schema_dir = tmp_path / "agent-model"
    schema_dir.mkdir(parents=True)
    (schema_dir / "schema.json").write_text('{"v":1}', encoding="utf-8")

    preset_base = tmp_path / "presets"
    preset_dir = preset_base / "dup"
    preset_dir.mkdir(parents=True)
    (preset_dir / "old.txt").write_text("old", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    code_cancel = save_preset(schema_dir, preset_base, "dup")
    out_cancel = capsys.readouterr()
    assert code_cancel == 1
    assert "Cancelled" in out_cancel.out
    assert (preset_dir / "old.txt").exists()

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    code_overwrite = save_preset(schema_dir, preset_base, "dup")
    assert code_overwrite == 0
    assert (preset_dir / "schema.json").exists()
    assert not (preset_dir / "old.txt").exists()


def test_load_preset_missing_and_success_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test case for test_load_preset_missing_and_success_paths."""
    schema_dir = tmp_path / "agent-model"
    preset_base = tmp_path / "presets"
    backup_base = tmp_path / "backups"

    code_missing = load_preset(schema_dir, preset_base, "missing", backup_base, no_backup=False)
    out_missing = capsys.readouterr()
    assert code_missing == 1
    assert "not found" in out_missing.err

    preset_dir = preset_base / "good"
    preset_dir.mkdir(parents=True)
    (preset_dir / "schema.json").write_text('{"ok":true}', encoding="utf-8")
    (preset_dir / "preset_metadata.json").write_text('{"name":"good"}', encoding="utf-8")

    schema_dir.mkdir(parents=True)
    (schema_dir / "current.json").write_text('{"old":true}', encoding="utf-8")

    code_ok = load_preset(schema_dir, preset_base, "good", backup_base, no_backup=False)
    out_ok = capsys.readouterr()
    assert code_ok == 0
    assert "Backup created" in out_ok.out
    assert (schema_dir / "schema.json").exists()
    assert not (schema_dir / "preset_metadata.json").exists()
    assert any(p.name.startswith("before_preset_good_") for p in backup_base.iterdir())


def test_load_preset_no_backup_skips_backup(tmp_path: Path) -> None:
    """Test case for test_load_preset_no_backup_skips_backup."""
    schema_dir = tmp_path / "agent-model"
    preset_base = tmp_path / "presets"
    backup_base = tmp_path / "backups"

    preset_dir = preset_base / "good"
    preset_dir.mkdir(parents=True)
    (preset_dir / "schema.json").write_text('{"ok":true}', encoding="utf-8")
    schema_dir.mkdir(parents=True)
    (schema_dir / "current.json").write_text('{"old":true}', encoding="utf-8")

    code = load_preset(schema_dir, preset_base, "good", backup_base, no_backup=True)
    assert code == 0
    assert not backup_base.exists()


def test_delete_preset_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test case for test_delete_preset_paths."""
    preset_base = tmp_path / "presets"
    code_missing = delete_preset(preset_base, "none")
    out_missing = capsys.readouterr()
    assert code_missing == 1
    assert "not found" in out_missing.err

    preset_dir = preset_base / "x"
    preset_dir.mkdir(parents=True)

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    code_cancel = delete_preset(preset_base, "x")
    out_cancel = capsys.readouterr()
    assert code_cancel == 1
    assert "Cancelled" in out_cancel.out
    assert preset_dir.exists()

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    code_ok = delete_preset(preset_base, "x")
    out_ok = capsys.readouterr()
    assert code_ok == 0
    assert "deleted" in out_ok.out
    assert not preset_dir.exists()


def test_main_dispatches_actions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test case for test_main_dispatches_actions."""
    schema_dir = tmp_path / "agent-model"
    preset_dir = tmp_path / "presets"
    backup_dir = tmp_path / "backups"
    schema_dir.mkdir(parents=True)
    (schema_dir / "schema.json").write_text('{"a":1}', encoding="utf-8")

    code_list_empty = main(["list", "--preset-dir", str(preset_dir)])
    out_list_empty = capsys.readouterr()
    assert code_list_empty == 0
    assert "No presets found" in out_list_empty.out

    code_missing_name = main(
        ["save", "--schema-dir", str(schema_dir), "--preset-dir", str(preset_dir)]
    )
    out_missing_name = capsys.readouterr()
    assert code_missing_name == 1
    assert "preset_name required" in out_missing_name.err

    code_save = main(
        [
            "save",
            "scenario1",
            "--schema-dir",
            str(schema_dir),
            "--preset-dir",
            str(preset_dir),
        ]
    )
    assert code_save == 0

    code_list = main(["list", "--preset-dir", str(preset_dir)])
    out_list = capsys.readouterr()
    assert code_list == 0
    assert "scenario1" in out_list.out

    code_load = main(
        [
            "load",
            "scenario1",
            "--schema-dir",
            str(schema_dir),
            "--preset-dir",
            str(preset_dir),
            "--backup-dir",
            str(backup_dir),
            "--no-backup",
        ]
    )
    assert code_load == 0

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    code_delete = main(["delete", "scenario1", "--preset-dir", str(preset_dir)])
    assert code_delete == 0
