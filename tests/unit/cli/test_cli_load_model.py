import json
from pathlib import Path
import pytest
from typing import Dict, Any, cast


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


def test_load_all_schemas_skips_empty_and_non_schema_entries(tmp_path: Path) -> None:
    base = tmp_path / "schemas"
    good = base / "GOOD"
    empty = base / "EMPTY"
    no_schema = base / "NO_SCHEMA"
    base.mkdir(parents=True)
    good.mkdir()
    empty.mkdir()
    no_schema.mkdir()
    (base / "README.txt").write_text("not a dir", encoding="utf-8")

    (good / "schema.json").write_text(json.dumps({"obj": {"type": "MibScalar"}}), encoding="utf-8")
    (empty / "schema.json").write_text(json.dumps({}), encoding="utf-8")

    model = clm.load_all_schemas(str(base))
    assert list(model.keys()) == ["GOOD"]


def test_load_all_schemas_generic_processing_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = tmp_path / "schemas"
    mib_dir = base / "BROKEN"
    mib_dir.mkdir(parents=True)
    schema_path = mib_dir / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")

    real_open = open

    def fake_open(*args: Any, **kwargs: Any) -> Any:
        file_arg = args[0] if args else ""
        if str(file_arg).endswith("schema.json"):
            raise RuntimeError("boom")
        return real_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    model = clm.load_all_schemas(str(base))
    captured = capsys.readouterr()
    assert model == {}
    assert "Error processing BROKEN: boom" in captured.err


def test_print_model_summary_handles_both_schema_shapes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    model: Dict[str, Dict[str, Any]] = {
        "NEW": {
            "objects": {
                "tbl": {"type": "MibTable"},
                "s": {"type": "MibScalar"},
            }
        },
        "OLD": {
            "a": {"type": "MibScalar"},
            "b": {"type": "MibTable"},
        },
        "BAD": cast(Dict[str, Any], {"objects": "not-a-dict"}),
    }

    clm.print_model_summary(model)
    out = capsys.readouterr().out
    assert "Loaded 3 MIB schemas:" in out
    assert "NEW: 2 objects, 1 tables" in out
    assert "OLD: 2 objects, 1 tables" in out
    assert "BAD: 0 objects, 0 tables" in out


def test_main_success_without_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model: Dict[str, Dict[str, Any]] = {"M1": {"objects": {"x": {"type": "MibScalar"}}}}
    monkeypatch.setattr(clm, "load_all_schemas", lambda d: model)

    rc = clm.main(["--schema-dir", str(tmp_path)])
    assert rc == 0
