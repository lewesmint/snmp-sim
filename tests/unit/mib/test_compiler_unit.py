import os
from pathlib import Path
from typing import Any

import pytest

from app.compiler import MibCompiler, MibCompilationError


class _FakePysmiCompiler:
    def __init__(self, results: dict[str, str]) -> None:
        self._results = results
        self.sources: list[Any] = []
        self.searchers: list[Any] = []

    def addSources(self, source: Any) -> None:
        """Mimic pysmi API (camelCase)"""
        self.sources.append(source)

    def addSearchers(self, searcher: Any) -> None:
        """Mimic pysmi API (camelCase)"""
        self.searchers.append(searcher)

    def compile(self, _mib_filename: str) -> dict[str, str]:
        return self._results


def _patch_compiler(monkeypatch: pytest.MonkeyPatch, results: dict[str, str]) -> None:
    def fake_compiler(*_args: Any, **_kwargs: Any) -> _FakePysmiCompiler:
        return _FakePysmiCompiler(results)

    monkeypatch.setattr("app.compiler.PysmiMibCompiler", fake_compiler)
    monkeypatch.setattr("app.compiler.FileReader", lambda _path: f"reader:{_path}")
    monkeypatch.setattr("app.compiler.PyFileSearcher", lambda _path: f"searcher:{_path}")
    monkeypatch.setattr("app.compiler.PyFileWriter", lambda _path: f"writer:{_path}")
    monkeypatch.setattr("app.compiler.parserFactory", lambda: lambda: "parser")
    monkeypatch.setattr("app.compiler.PySnmpCodeGen", lambda: "codegen")


def test_compiler_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = {"TEST-MIB": "compiled"}
    _patch_compiler(monkeypatch, results)

    compiler = MibCompiler(output_dir=str(tmp_path))
    compiled_path = tmp_path / "TEST-MIB.py"
    compiled_path.write_text("# compiled")

    def fake_exists(path: str) -> bool:
        if path == "data/mibs":
            return False
        if path == str(compiled_path):
            return True
        return os.path.exists(path)

    monkeypatch.setattr("app.compiler.os.path.exists", fake_exists)

    output = compiler.compile("/tmp/TEST-MIB.txt")
    assert output == str(compiled_path)


def test_compiler_missing_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = {"TEST-MIB": "MISSING dependency"}
    _patch_compiler(monkeypatch, results)

    compiler = MibCompiler(output_dir=str(tmp_path))
    monkeypatch.setattr("app.compiler.os.path.exists", lambda _path: False)

    with pytest.raises(MibCompilationError) as excinfo:
        compiler.compile("/tmp/TEST-MIB.txt")
    assert "Missing MIB dependencies" in str(excinfo.value)
    assert excinfo.value.missing_dependencies == ["TEST-MIB"]


def test_compiler_failed_mib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = {"TEST-MIB": "failed"}
    _patch_compiler(monkeypatch, results)

    compiler = MibCompiler(output_dir=str(tmp_path))
    monkeypatch.setattr("app.compiler.os.path.exists", lambda _path: False)

    with pytest.raises(MibCompilationError) as excinfo:
        compiler.compile("/tmp/TEST-MIB.txt")
    assert "Failed to compile" in str(excinfo.value)


def test_compiler_no_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results: dict[str, str] = {}
    _patch_compiler(monkeypatch, results)

    compiler = MibCompiler(output_dir=str(tmp_path))
    monkeypatch.setattr("app.compiler.os.path.exists", lambda _path: False)

    with pytest.raises(MibCompilationError) as excinfo:
        compiler.compile("/tmp/TEST-MIB.txt")
    assert "No MIB module found" in str(excinfo.value)


def test_compiler_output_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = {"TEST-MIB": "compiled"}
    _patch_compiler(monkeypatch, results)

    compiler = MibCompiler(output_dir=str(tmp_path))
    monkeypatch.setattr("app.compiler.os.path.exists", lambda _path: False)

    with pytest.raises(MibCompilationError) as excinfo:
        compiler.compile("/tmp/TEST-MIB.txt")
    assert "output file not found" in str(excinfo.value)


def test_parse_missing_from_status() -> None:
    compiler = MibCompiler(output_dir="/tmp")
    status = "FOO is missing, BAR is missing, FOO is missing"
    missing = compiler._parse_missing_from_status(status)
    assert sorted(missing) == ["BAR", "FOO"]
