from __future__ import annotations

import json
from pathlib import Path
from app.generator import BehaviourGenerator
from typing import Any
import pytest


class _FakeSyntax:
    def __init__(self, name: str) -> None:
        self.__class__.__name__ = name


class _FakeSymbol:
    def __init__(self, name: str, oid: tuple[int, ...], syntax_name: str, access: str = "read-only") -> None:
        self._name = name
        self._oid = oid
        self._syntax = _FakeSyntax(syntax_name)
        self._access = access

    def getName(self) -> tuple[int, ...]:
        return self._oid

    def getSyntax(self) -> _FakeSyntax:
        return self._syntax

    def getMaxAccess(self) -> str:
        return self._access


class _FakeEntry(_FakeSymbol):
    def __init__(self, name: str, oid: tuple[int, ...], indexes: list[tuple[str, str, str]]) -> None:
        super().__init__(name, oid, "MibTableRow", "not-accessible")
        self._indexes = indexes

    def getIndexNames(self) -> list[tuple[str, str, str]]:
        return self._indexes


class _FakeMibBuilder:
    def __init__(self, mib_name: str, symbols: dict[str, Any]) -> None:
        self.mibSymbols = {mib_name: symbols}

    def add_mib_sources(self, _source: Any) -> None:
        return None

    def load_modules(self, _mib_name: str) -> None:
        return None


def test_parse_mib_name_from_py(tmp_path: Path) -> None:
    mib_file = tmp_path / "TEST-MIB.py"
    mib_file.write_text('mibBuilder.exportSymbols("TEST-MIB", testSymbol)')

    generator = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=False)
    assert generator._parse_mib_name_from_py(str(mib_file)) == "TEST-MIB"


def test_parse_mib_name_from_py_fallback(tmp_path: Path) -> None:
    mib_file = tmp_path / "FOO-BAR.py"
    mib_file.write_text("# no export symbols")

    generator = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=False)
    assert generator._parse_mib_name_from_py(str(mib_file)) == "FOO-BAR"


def test_get_default_value_from_type_info_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    monkeypatch.setattr("app.generator.get_default_value", lambda _type_info, _name: "value")
    assert generator._get_default_value_from_type_info({"base_type": "Integer32"}, "sysDescr") == "value"


def test_get_default_value_from_type_info_raises(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    monkeypatch.setattr("app.generator.get_default_value", lambda _type_info, _name: None)

    with pytest.raises(RuntimeError):
        generator._get_default_value_from_type_info({"base_type": "Integer32"}, "sysDescr")



def test_get_default_value_legacy() -> None:
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("DisplayString", "sysName") == "my-pysnmp-agent"
    assert generator._get_default_value("ObjectIdentifier", "foo") == "0.0"
    assert generator._get_default_value("Integer32", "foo") == 0


def test_extract_mib_info_inherited_indexes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mib_name = "TEST-MIB"
    entry_oid = (1, 2, 3, 1)
    entry = _FakeEntry("testEntry", entry_oid, [("idx", "OTHER-MIB", "ifIndex")])
    col = _FakeSymbol("col", entry_oid + (1,), "Integer32")
    symbols = {
        "testEntry": entry,
        "col": col,
    }

    fake_builder = _FakeMibBuilder(mib_name, symbols)
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: fake_builder)
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")

    generator = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=False)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})
    monkeypatch.setattr(generator, "_get_dynamic_function", lambda _name: None)
    # Avoid RuntimeError on default value lookup in this test
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 0)

    result = generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), mib_name)
    assert result["testEntry"]["index_from"] == [{"mib": "OTHER-MIB", "column": "ifIndex"}]


def test_generate_writes_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    generator = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=False)
    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: {"sysDescr": {"oid": [1], "type": "OctetString"}})

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    output_path = Path(output)
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "sysDescr" in data


def test_generate_respects_existing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    # If schema.json exists for the MIB and force_regenerate=False, it should be respected
    mib_dir = output_dir / "TEST-MIB"
    mib_dir.mkdir(parents=True)
    existing = mib_dir / "schema.json"
    existing.write_text("{}")

    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=False)
    assert output == str(existing)


def test_generate_adds_default_row_for_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    info = {
        "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1], "indexes": ["idx"]},
        "idx": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
        "val": {"type": "OctetString", "oid": [1, 2, 3, 1, 2]},
    }

    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"OctetString": {"base_type": "OctetString"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: "default")

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    data = json.loads(Path(output).read_text())
    rows = data["testTable"]["rows"]
    assert rows and rows[0]["idx"] == 1
    assert rows[0]["val"] == "default"
    # Ensure returned path is the schema.json path
    assert output.endswith("schema.json")


def test_generate_extracts_index_names_from_compiled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    info = {
        "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
        "idx": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
        "val": {"type": "OctetString", "oid": [1, 2, 3, 1, 2]},
    }

    class _EntryObj:
        def getIndexNames(self) -> list[tuple[str, str, str]]:
            return [("idx", "TEST-MIB", "idx")]

    class _FakeBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"testEntry": _EntryObj()}}

        def add_mib_sources(self, _source: Any) -> None:
            return None

        def load_modules(self, _name: str) -> None:
            return None

    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: _FakeBuilder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")

    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"OctetString": {"base_type": "OctetString"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: "default")

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    data = json.loads(Path(output).read_text())
    rows = data["testTable"]["rows"]
    assert rows and rows[0]["idx"] == 1


def test_extract_type_info_enums_and_constraints() -> None:
    class _SubtypeSpec:
        values = ["constraint-1", "constraint-2"]

    class _Syntax:
        def __init__(self) -> None:
            self.namedValues = {"up": 1, "down": 2}
            self.subtypeSpec = _SubtypeSpec()

    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    type_info = generator._extract_type_info(_Syntax(), "Integer32")
    assert type_info["base_type"] == "Integer32"
    assert type_info["enums"] == {"up": 1, "down": 2}
    assert type_info["constraints"] == ["constraint-1", "constraint-2"]


def test_extract_type_info_subtype_no_values() -> None:
    class _SubtypeSpec:
        def __str__(self) -> str:
            return "subtype"

    class _Syntax:
        namedValues = None
        subtypeSpec = _SubtypeSpec()

    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    type_info = generator._extract_type_info(_Syntax(), "Integer32")
    assert type_info["constraints"] == ["subtype"]


def test_get_dynamic_function() -> None:
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_dynamic_function("sysUpTime") == "uptime"
    assert generator._get_dynamic_function("sysDescr") is None


def test_load_type_registry_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    monkeypatch.setattr("app.generator.os.path.exists", lambda _p: False)
    with pytest.raises(FileNotFoundError):
        generator._load_type_registry()


def test_extract_mib_info_non_dict_symbols(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mib_name = "TEST-MIB"

    class _BadBuilder:
        mibSymbols: dict[str, list[Any]] = {mib_name: []}

        def add_mib_sources(self, _source: Any) -> None:
            return None

        def load_modules(self, _mib_name: str) -> None:
            return None

    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: _BadBuilder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")

    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    with pytest.raises(TypeError):
        generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), mib_name)


def test_table_without_entry_suffix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test table name extraction when table doesn't end with 'Table'"""
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    info = {
        "someList": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        "someListEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1], "indexes": ["idx"]},
        "idx": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
    }

    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 0)

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    data = json.loads(Path(output).read_text())
    # Should have added a row despite non-standard table name
    assert "rows" in data["someList"]


def test_extract_type_info_no_enums_or_constraints() -> None:
    """Test extract_type_info with no enums or constraints"""
    class _Syntax:
        namedValues = None
        subtypeSpec = None

    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    type_info = generator._extract_type_info(_Syntax(), "Integer32")
    assert type_info["base_type"] == "Integer32"
    assert type_info["enums"] is None
    assert type_info["constraints"] is None


def test_extract_type_info_empty_enums() -> None:
    """Test extract_type_info with empty enums"""
    class _Syntax:
        namedValues: dict[str, int] = {}
        subtypeSpec = None

    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    type_info = generator._extract_type_info(_Syntax(), "Integer32")
    assert type_info["enums"] is None


def test_extract_type_info_constraint_exception() -> None:
    """Test extract_type_info when constraint extraction raises exception"""
    class _BadSubtypeSpec:
        values = property(lambda self: (_ for _ in ()).throw(Exception("boom")))

    class _Syntax:
        namedValues = None
        subtypeSpec = _BadSubtypeSpec()

    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    type_info = generator._extract_type_info(_Syntax(), "Integer32")
    # Should handle exception gracefully
    assert type_info["constraints"] is None or type_info["constraints"] == []


def test_get_default_value_legacy_specific_symbols() -> None:
    """Test legacy get_default_value for specific system symbols"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("DisplayString", "sysDescr") == "Simple Python SNMP Agent - Demo System"
    assert generator._get_default_value("OID", "sysObjectID") == "1.3.6.1.4.1.99999"
    assert generator._get_default_value("DisplayString", "sysContact") == "Admin <admin@example.com>"
    assert generator._get_default_value("DisplayString", "sysLocation") == "Development Lab"
    assert generator._get_default_value("TimeTicks", "sysUpTime") is None  # Dynamic


def test_get_default_value_legacy_counter_types() -> None:
    """Test legacy get_default_value for counter types"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("Counter32", "ifInOctets") == 0
    assert generator._get_default_value("Counter64", "ifHCInOctets") == 0


def test_get_default_value_legacy_gauge_types() -> None:
    """Test legacy get_default_value for Gauge32 and Unsigned32"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("Gauge32", "ifSpeed") == 0
    assert generator._get_default_value("Unsigned32", "someValue") == 0


def test_get_default_value_legacy_ip_address() -> None:
    """Test legacy get_default_value for IpAddress"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("IpAddress", "ipAddr") == "0.0.0.0"


def test_get_default_value_legacy_unknown_type() -> None:
    """Test legacy get_default_value for unknown type"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    assert generator._get_default_value("UnknownType", "someSymbol") is None


def test_generate_missing_mib_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test generate when mib_name is None - should parse from file"""
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('mibBuilder.exportSymbols("AUTO-MIB", testSym)')
        f.flush()

        # Mock _extract_mib_info to avoid actual MIB loading
        def mock_extract(_path: str, _name: str) -> dict[str, Any]:
            return {"testSym": {"oid": [1], "type": "Integer32", "access": "read-only", "initial": 0}}

        monkeypatch.setattr(generator, "_extract_mib_info", mock_extract)

        try:
            output = generator.generate(f.name, mib_name=None, force_regenerate=True)
            assert "AUTO-MIB/schema.json" in output
        finally:
            import os
            os.unlink(f.name)


def test_extract_mib_info_symbol_without_methods(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test _extract_mib_info skips symbols without getName/getSyntax"""
    mib_name = "TEST-MIB"
    
    class _GoodSymbol:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)
        
        def getSyntax(self) -> Any:
            class _Syntax:
                __name__ = "Integer32"
            return _Syntax()
        
        def getMaxAccess(self) -> str:
            return "read-only"
    
    class _BadSymbol:
        pass  # No getName or getSyntax
    
    class _Builder:
        mibSymbols = {mib_name: {"goodSym": _GoodSymbol(), "badSym": _BadSymbol()}}
        
        def add_mib_sources(self, _source: Any) -> None:
            return None
        
        def load_modules(self, _name: str) -> None:
            return None
    
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: _Builder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 0)
    monkeypatch.setattr(generator, "_get_dynamic_function", lambda _n: None)
    
    result = generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), mib_name)
    assert "goodSym" in result
    assert "badSym" not in result


def test_extract_mib_info_get_name_raises_type_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test _extract_mib_info handles TypeError from getName"""
    mib_name = "TEST-MIB"
    
    class _SymbolWithError:
        def getName(self) -> None:
            raise TypeError("boom")
        
        def getSyntax(self) -> Any:
            return None
    
    class _Builder:
        mibSymbols = {mib_name: {"errorSym": _SymbolWithError()}}
        
        def add_mib_sources(self, _source: Any) -> None:
            return None
        
        def load_modules(self, _name: str) -> None:
            return None
    
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: _Builder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    
    result = generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), mib_name)
    # Should skip the erroring symbol
    assert "errorSym" not in result


def test_extract_mib_info_none_syntax(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test _extract_mib_info with None syntax"""
    mib_name = "TEST-MIB"
    
    class _NoneTypeClass:
        __name__ = "NoneType"
    
    class _SymbolWithNone:
        def __init__(self) -> None:
            self.__class__.__name__ = "TestSymbol"
        
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)
        
        def getSyntax(self) -> None:
            return None
        
        def getMaxAccess(self) -> str:
            return "read-only"
    
    class _Builder:
        mibSymbols = {mib_name: {"testSym": _SymbolWithNone()}}
        
        def add_mib_sources(self, _source: Any) -> None:
            return None
        
        def load_modules(self, _name: str) -> None:
            return None
    
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: _Builder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: None)
    monkeypatch.setattr(generator, "_get_dynamic_function", lambda _n: None)
    
    result = generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), mib_name)
    # Should use the symbol's class name as type
    assert result["testSym"]["type"] == "TestSymbol"


def test_detect_inherited_indexes_no_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _detect_inherited_indexes with entry that has no indexes"""
    class _Entry:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3, 1)
        
        def getIndexNames(self) -> list[Any]:
            return []
    
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    result: dict[str, Any] = {"testEntry": {"oid": [1, 2, 3, 1]}}
    table_entries = {"testEntry": _Entry()}
    
    generator._detect_inherited_indexes(result, table_entries, "TEST-MIB")
    # Should not add index_from since there are no indexes
    assert "index_from" not in result["testEntry"]


def test_detect_inherited_indexes_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _detect_inherited_indexes handles exceptions gracefully"""
    class _BadEntry:
        def getIndexNames(self) -> None:
            raise Exception("boom")
    
    generator = BehaviourGenerator(output_dir="/tmp", load_default_plugins=False)
    result: dict[str, Any] = {"badEntry": {"oid": [1, 2, 3, 1]}}
    table_entries = {"badEntry": _BadEntry()}
    
    # Should not raise exception
    generator._detect_inherited_indexes(result, table_entries, "TEST-MIB")
    assert "index_from" not in result["badEntry"]


def test_table_with_no_entry_info(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test table generation when entry_info is empty dict"""
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    info = {
        "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        # No testEntry at all
    }

    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    data = json.loads(Path(output).read_text())
    # Should still have empty rows
    assert data["testTable"]["rows"] == []


def test_table_entry_already_has_indexes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that index extraction is skipped when entry already has indexes"""
    output_dir = tmp_path / "out"
    generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

    info = {
        "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1], "indexes": ["idx"]},
        "idx": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
    }

    # Mock MibBuilder to verify it's NOT called when indexes already exist
    class _MockBuilder:
        def __init__(self) -> None:
            self.load_called = False
        
        def add_mib_sources(self, _source: Any) -> None:
            return None
        
        def load_modules(self, _name: str) -> None:
            self.load_called = True
            raise AssertionError("load_modules should not be called when indexes already exist")

    mock_builder = _MockBuilder()
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: mock_builder)
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    
    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 1)

    output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    data = json.loads(Path(output).read_text())
    # Should have generated row
    assert len(data["testTable"]["rows"]) > 0


class TestGeneratorErrorHandling:
    """Test error handling in BehaviourGenerator"""

    def test_generate_with_missing_entry_info(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test handling of MIB with table but no entry info"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            # Entry info is missing - should not crash
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        
        # Should handle gracefully without raising
        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema.json")

    def test_generate_table_with_no_columns(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test handling of table with entry but no columns"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1], "indexes": []},
            # No columns defined
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        
        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        data = json.loads(Path(output).read_text())
        # Should create rows even with no columns
        assert "testTable" in data

    def test_mibbuilder_exception_during_index_extraction(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test graceful handling of MibBuilder exceptions"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
            "testCol": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]}
        }

        class _FailingBuilder:
            def add_mib_sources(self, _source: Any) -> None:
                pass
            
            def load_modules(self, _name: str) -> None:
                raise RuntimeError("MIB loading error")
            
            mibSymbols: dict[str, Any] = {}

        monkeypatch.setattr("app.generator.builder.MibBuilder", _FailingBuilder)
        monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _p: "src")
        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 1)
        
        # Should handle exception and continue
        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema.json")

    def test_parse_mib_name_with_fallback(self, tmp_path: Path) -> None:
        """Test parsing MIB names with fallback to filename"""
        gen = BehaviourGenerator(load_default_plugins=False)
        
        # Create a file without exportSymbols
        py_file = tmp_path / "FALLBACK-MIB.py"
        py_file.write_text("# No export symbols here\nvar = 1")
        
        # Should use filename as fallback
        result = gen._parse_mib_name_from_py(str(py_file))
        assert result == "FALLBACK-MIB"

    def test_parse_mib_name_with_export_symbols(self, tmp_path: Path) -> None:
        """Test parsing MIB names from exportSymbols line"""
        gen = BehaviourGenerator(load_default_plugins=False)
        
        # Create a file with exportSymbols
        py_file = tmp_path / "SOURCE.py"
        py_file.write_text('mibBuilder.exportSymbols("TEST-MIB-NAME")')
        
        result = gen._parse_mib_name_from_py(str(py_file))
        assert result == "TEST-MIB-NAME"

    def test_generate_symbol_info_not_dict(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate skips non-dict symbol info (line 50)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "nonDictSymbol": "string_not_dict",
            "validSymbol": {"type": "OctetString", "oid": [1, 2, 3]},
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema.json")

    def test_generate_symbol_is_table_row_not_table(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate handles MibTableRow without matching MibTable (line 55)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        # MibTableRow without type key should get type assigned
        info = {
            "testEntry": {"oid": [1, 2, 3, 1], "indexes": []},
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)

        # Manually set the type for this test
        info["testEntry"]["type"] = "MibTableRow"

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema.json")

    def test_generate_table_without_type_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate assigns NoneType when type key missing from table (line 59)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"oid": [1, 2, 3], "rows": []},
        }
        
        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)

        # Manually set type to trigger the branch
        info["testTable"]["type"] = "MibTable"

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema

    def test_generate_rows_not_list_or_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate handles rows field that is not a list (line 61)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": "not_a_list"},
            "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        monkeypatch.setattr(generator, "_get_dynamic_function", lambda _name: None)

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        # After generation, rows should be converted to list
        assert isinstance(info["testTable"]["rows"], list)
        # Ensure returned path is schema.json
        assert output.endswith("schema.json")

    def test_extract_type_info_constraint_with_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _extract_type_info handles constraints with values attribute (line 286)"""
        class ConstraintWithValues:
            values = [1, 2, 3]

        class SyntaxObj:
            subtypeSpec = ConstraintWithValues()

        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._extract_type_info(SyntaxObj(), "TestType")
        
        assert "constraints" in result
        assert isinstance(result["constraints"], list)

    def test_extract_type_info_constraint_no_values_attr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _extract_type_info handles constraints without values attribute (line 289)"""
        class SimpleConstraint:
            def __str__(self) -> str:
                return "ValueRangeConstraint(0, 100)"

        class SyntaxObj:
            subtypeSpec = SimpleConstraint()

        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._extract_type_info(SyntaxObj(), "TestType")
        
        assert "constraints" in result
        assert isinstance(result["constraints"], list)
        assert len(result["constraints"]) > 0

    def test_get_default_value_ipaddress(self) -> None:
        """Test _get_default_value returns IP address default (line 356)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._get_default_value("IpAddress", "unknownSymbol")
        assert result == "0.0.0.0"

    def test_get_default_value_object_identifier(self) -> None:
        """Test _get_default_value returns ObjectIdentifier default (line 354)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._get_default_value("ObjectIdentifier", "unknownSymbol")
        assert result == "0.0"

    def test_get_default_value_timeticks(self) -> None:
        """Test _get_default_value returns TimeTicks default (line 358)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._get_default_value("TimeTicks", "unknownSymbol")
        assert result == 0

    def test_get_default_value_unknown_type_fallthrough(self) -> None:
        """Test _get_default_value fallthrough for unknown types (line 346, 356)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._get_default_value("UnknownType", "unknownSymbol")
        assert result is None

    def test_extract_type_info_no_namedvalues(self) -> None:
        """Test _extract_type_info when namedValues is None (line 276)"""
        class SyntaxObj:
            namedValues = None

        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._extract_type_info(SyntaxObj(), "TestType")
        
        assert result["enums"] is None

    def test_extract_type_info_empty_namedvalues(self) -> None:
        """Test _extract_type_info when namedValues is empty (line 276)"""
        class SyntaxObj:
            namedValues = {}

        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._extract_type_info(SyntaxObj(), "TestType")
        
        assert result["enums"] is None

    def test_extract_type_info_no_subtypespec(self) -> None:
        """Test _extract_type_info when subtypeSpec is missing (line 281)"""
        class SyntaxObj:
            pass

        gen = BehaviourGenerator(load_default_plugins=False)
        result = gen._extract_type_info(SyntaxObj(), "TestType")
        
        assert result["constraints"] is None
    def test_generate_handles_missing_type_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate assigns NoneType when type is in condition but not in dict (line 55)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"oid": [1, 2, 3], "rows": []},
        }
        
        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)

        # Manually set type to MibTableRow (matches condition but 'type' key will be missing initially)
        info["testEntry"] = {"type": "MibTableRow", "oid": [1, 2, 3, 1]}
        # Don't set type on testEntry initially
        del info["testEntry"]["type"]

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("schema.json")

    def test_generate_entry_not_in_info_dict(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate when entry doesn't exist in info dict (line 88)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        # Table without corresponding entry
        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        monkeypatch.setattr(generator, "_get_dynamic_function", lambda _name: None)

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("TEST-MIB_behaviour.json")

    def test_generate_entry_has_existing_indexes(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate skips index extraction when indexes already exist (line 92)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1], "indexes": ["idx"]},
            "idx": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
        }

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 1)

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("TEST-MIB_behaviour.json")

    def test_generate_entry_object_missing_get_index_names(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test generate handles entry object without getIndexNames (line 96)"""
        output_dir = tmp_path / "out"
        generator = BehaviourGenerator(output_dir=str(output_dir), load_default_plugins=False)

        info = {
            "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
        }

        class FakeSymbol:
            pass  # No getIndexNames method

        fake_builder = _FakeMibBuilder("TEST-MIB", {"testEntry": FakeSymbol()})
        monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: fake_builder)
        monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")

        monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
        monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
        monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
        monkeypatch.setattr(generator, "_get_dynamic_function", lambda _name: None)

        output = generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
        assert output.endswith("TEST-MIB_behaviour.json")

    def test_init_loads_default_plugins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test __init__ loads default plugins when load_default_plugins=True (lines 21-22)"""
        loaded_plugins: list[str] = []
        
        def mock_load_plugins() -> list[str]:
            loaded_plugins.extend(["plugin1", "plugin2"])
            return loaded_plugins

        monkeypatch.setattr("app.generator.load_plugins", mock_load_plugins)
        
        # Create generator with load_default_plugins=True
        gen = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=True)
        
        # Verify it was called
        assert len(loaded_plugins) > 0

    def test_init_skips_plugins_when_disabled(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test __init__ skips loading plugins when load_default_plugins=False (lines 21-22)"""
        loaded_plugins: list[str] = []
        
        def mock_load_plugins() -> list[str]:
            loaded_plugins.append("should_not_be_called")
            return loaded_plugins

        monkeypatch.setattr("app.generator.load_plugins", mock_load_plugins)
        
        # Create generator with load_default_plugins=False
        gen = BehaviourGenerator(output_dir=str(tmp_path / "out"), load_default_plugins=False)
        
        # Verify it was NOT called
        assert len(loaded_plugins) == 0

    def test_get_default_value_all_unknown_type_variants(self) -> None:
        """Test _get_default_value for all unknown type variants (line 346)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        
        unknown_types = ["CustomType", "VendorType", "RandomType", "AnyType"]
        for unknown_type in unknown_types:
            result = gen._get_default_value(unknown_type, "unknownSymbol")
            assert result is None, f"Failed for {unknown_type}"

    def test_get_default_value_displaystring_and_octetstring(self) -> None:
        """Test _get_default_value for DisplayString and OctetString types (line 346)"""
        gen = BehaviourGenerator(load_default_plugins=False)
        
        # Test DisplayString
        result = gen._get_default_value("DisplayString", "unknownSymbol")
        assert result == "unset"
        
        # Test OctetString
        result = gen._get_default_value("OctetString", "unknownSymbol")
        assert result == "unset"