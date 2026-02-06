import os
import types
import json
from pathlib import Path
from typing import Any

import pytest

from app.generator import BehaviourGenerator


def test_parse_mib_name_from_py(tmp_path: Path) -> None:
    p = tmp_path / "CUST-MIB.py"
    p.write_text("# some header\nmibBuilder.exportSymbols(\"CUST-MIB\", )\n")
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    name = g._parse_mib_name_from_py(str(p))
    assert name == "CUST-MIB"


def test_get_default_value_legacy() -> None:
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    assert g._get_default_value("DisplayString", "foo") == "unset"
    assert g._get_default_value("ObjectIdentifier", "foo") == "0.0"
    assert g._get_default_value("Integer32", "foo") == 0
    assert g._get_default_value("UnknownType", "sysDescr") is None or isinstance(
        g._get_default_value("UnknownType", "sysDescr"), str
    )


def test_extract_type_info_enums_and_constraints() -> None:
    class Syntax:
        namedValues = {"one": 1, "two": 2}

        class subtypeSpec:
            values = [1, 2]

    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    info = g._extract_type_info(Syntax(), "MyType")
    assert info["enums"] is not None
    assert info["constraints"] is not None


def test_generate_writes_schema(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Prepare fake symbol objects
    class MibTable:
        def getName(self) -> tuple[int, ...]:
            return (1, 3)

        def getSyntax(self) -> None:
            return None

    class MibTableRow:
        def getName(self) -> tuple[int, ...]:
            return (1, 3, 6)

        def getSyntax(self) -> None:
            return None

    class MibTableColumn:
        def __init__(self, oid: list[int]) -> None:
            self._oid = oid

        def getName(self) -> tuple[int, ...]:
            return tuple(self._oid)

        def getSyntax(self) -> object:
            class Int:
                pass

            return Int()

        def getMaxAccess(self) -> str:
            return "read-only"

    class FakeBuilder:
        def __init__(self, symbols: dict[str, Any]):
            self.mibSymbols = symbols

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    symbols = {
        "TESTMIB": {
            "MyTable": MibTable(),
            "MyTableEntry": MibTableRow(),
            "col1": MibTableColumn([1, 3, 6, 1]),
        }
    }

    def fake_mibbuilder_factory() -> "FakeBuilder":
        return FakeBuilder(symbols)

    # Monkeypatch the builder used in generator module
    import app.generator as genmod

    # Replace builder with a simple namespace that exposes MibBuilder to satisfy attribute checks
    monkeypatch.setattr(genmod, "builder", types.SimpleNamespace(MibBuilder=lambda: fake_mibbuilder_factory()))

    # Monkeypatch default value lookup to avoid plugin dependency
    monkeypatch.setattr(BehaviourGenerator, "_get_default_value_from_type_info", lambda self, t, s: 0)

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    # Create a dummy compiled py path
    compiled = tmp_path / "TESTMIB.py"
    compiled.write_text("# dummy compiled mib")

    schema_path = g.generate(str(compiled), mib_name="TESTMIB", force_regenerate=True)
    assert os.path.exists(schema_path)
    with open(schema_path, "r") as f:
        data = json.load(f)
    # Ensure columns and table entry exist
    assert "col1" in data
    assert "MyTable" in data
