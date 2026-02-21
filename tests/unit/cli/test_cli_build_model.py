import json
from typing import Any, NoReturn


from app import cli_build_model as cbm


def test_load_mib_schema_missing(tmp_path: Any, capsys: Any) -> None:
    schema = cbm.load_mib_schema("NONEXISTENT", str(tmp_path))
    captured = capsys.readouterr()
    assert schema is None
    assert "Warning: Schema not found" in captured.err


def test_load_mib_schema_invalid_json(tmp_path: Any, capsys: Any) -> None:
    mib_dir = tmp_path / "TEST-MIB"
    mib_dir.mkdir()
    (mib_dir / "schema.json").write_text("{ not: json }")

    schema = cbm.load_mib_schema("TEST-MIB", str(tmp_path))
    captured = capsys.readouterr()
    assert schema is None
    assert "Error: Failed to parse" in captured.err


def test_load_mib_schema_valid(tmp_path: Any) -> None:
    mib_dir = tmp_path / "GOOD-MIB"
    mib_dir.mkdir()
    data = {"foo": {"type": "MibScalar"}}
    (mib_dir / "schema.json").write_text(json.dumps(data))

    schema = cbm.load_mib_schema("GOOD-MIB", str(tmp_path))
    assert schema == data


def test_build_internal_model_only_includes_present(tmp_path: Any) -> None:
    m1 = tmp_path / "A"
    m1.mkdir()
    (m1 / "schema.json").write_text(json.dumps({"a": {}}))

    model = cbm.build_internal_model(["A", "B"], str(tmp_path))
    assert "A" in model
    assert "B" not in model


def test_print_model_summary(capsys: Any) -> None:
    model = {
        "M1": {"x": {"type": "MibScalar"}, "t": {"type": "MibTable"}},
        "M2": {"a": {"type": "MibScalar"}},
    }
    cbm.print_model_summary(model)
    out = capsys.readouterr().out
    assert "Loaded 2 MIB schemas" in out
    assert "M1: 2 objects, 1 tables" in out


class DummyConfigNoMibs:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def get(self, key: Any, default: Any = None) -> Any:
        if key == "mibs":
            return []
        return default


class DummyConfigWithMibs:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def get(self, key: Any, default: Any = None) -> Any:
        if key == "mibs":
            return ["M1"]
        return default


def test_main_config_not_found(monkeypatch: Any, capsys: Any) -> None:
    def raise_nf(*a: Any, **k: Any) -> NoReturn:
        raise FileNotFoundError()

    monkeypatch.setattr(cbm, "AppConfig", raise_nf)
    rc = cbm.main([])
    assert rc == 1


def test_main_no_mibs(monkeypatch: Any) -> None:
    monkeypatch.setattr(cbm, "AppConfig", DummyConfigNoMibs)
    rc = cbm.main([])
    assert rc == 1


def test_main_no_schemas_loaded(monkeypatch: Any) -> None:
    monkeypatch.setattr(cbm, "AppConfig", DummyConfigWithMibs)
    monkeypatch.setattr(cbm, "build_internal_model", lambda mibs, schema_dir: {})
    rc = cbm.main(["--schema-dir", "nonexistent_dir"])
    assert rc == 1


def test_main_output_write_error(monkeypatch: Any, tmp_path: Any) -> None:
    # Provide a model and attempt to write to a directory path to force an IOError
    monkeypatch.setattr(cbm, "AppConfig", DummyConfigWithMibs)
    monkeypatch.setattr(
        cbm, "build_internal_model", lambda mibs, schema_dir: {"M1": {}}
    )
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    rc = cbm.main(["--schema-dir", str(tmp_path), "--output", str(out_dir)])
    assert rc == 1


def test_main_success_writes_output(
    monkeypatch: Any, tmp_path: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cbm, "AppConfig", DummyConfigWithMibs)
    model: dict[str, dict[str, Any]] = {"M1": {"a": {}}}
    monkeypatch.setattr(cbm, "build_internal_model", lambda mibs, schema_dir: model)
    out_file = tmp_path / "out.json"

    rc = cbm.main(["--schema-dir", str(tmp_path), "--output", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data == model
    assert "Model saved to" in capsys.readouterr().out
