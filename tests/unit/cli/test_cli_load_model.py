import json
from pathlib import Path
import pytest
from typing import Dict, Any


from app import cli_load_model as clm


def test_load_all_schemas_missing_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_dir = tmp_path / "nope"
    model = clm.load_all_schemas(str(fake_dir))
    captured = capsys.readouterr()
    assert model == {}
    assert "Schema directory not found" in captured.err


def test_load_all_schemas_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = tmp_path / "schemas"
    mib_dir = base / "BAD"
    mib_dir.mkdir(parents=True)
    (mib_dir / "schema.json").write_text("{ not json }")

    model = clm.load_all_schemas(str(base))
    captured = capsys.readouterr()
    assert model == {}
    assert "Error loading" in captured.err


def test_load_all_schemas_success(tmp_path: Path) -> None:
    base = tmp_path / "schemas"
    mib_dir = base / "GOOD"
    mib_dir.mkdir(parents=True)
    data = {"a": {"type": "MibScalar"}}
    (mib_dir / "schema.json").write_text(json.dumps(data))

    model = clm.load_all_schemas(str(base))
    assert "GOOD" in model
    assert model["GOOD"] == data


def test_main_no_schemas(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure load_all_schemas returns empty
    monkeypatch.setattr(clm, "load_all_schemas", lambda d: {})
    rc = clm.main(["--schema-dir", "doesnotmatter"])  # prints and returns 1
    assert rc == 1


def test_main_success_writes_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model: Dict[str, Dict[str, Any]] = {"M1": {"a": {}}}
    monkeypatch.setattr(clm, "load_all_schemas", lambda d: model)
    out_file = tmp_path / "out.json"

    rc = clm.main(["--schema-dir", str(tmp_path), "--output", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data == model


def test_main_output_write_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model: Dict[str, Dict[str, Any]] = {"M1": {"a": {}}}
    monkeypatch.setattr(clm, "load_all_schemas", lambda d: model)
    out_dir = tmp_path
    # Passing a directory path as output should cause file write error
    rc = clm.main(["--schema-dir", str(tmp_path), "--output", str(out_dir)])
    assert rc == 1
