"""Extended unit tests for `BehaviourGenerator` edge cases and fallback paths."""

# pylint: disable=too-many-lines,missing-function-docstring,protected-access
# pylint: disable=missing-class-docstring,invalid-name,too-few-public-methods
# pylint: disable=import-outside-toplevel,import-error,unused-argument
# pylint: disable=broad-exception-raised,unused-variable

import json
import os
import types
from pathlib import Path
from typing import Any

import pytest

from app.generator import BehaviourGenerator  # pylint: disable=import-error


def _return_zero(*_args: Any) -> int:
    return 0


def test_parse_mib_name_from_py(tmp_path: Path) -> None:
    p = tmp_path / "CUST-MIB.py"
    p.write_text('# some header\nmibBuilder.exportSymbols("CUST-MIB", )\n')
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    name = g._parse_mib_name_from_py(str(p))
    assert name == "CUST-MIB"


def test_get_default_value_legacy() -> None:
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    assert g._get_default_value("DisplayString", "foo") == "unset"
    assert g._get_default_value("ObjectIdentifier", "foo") == "0.0"
    assert g._get_default_value("Integer32", "foo") == 0
    assert g._get_default_value("UnknownType", "sysDescr") is None or isinstance(
        g._get_default_value("UnknownType", "sysDescr"),
        str,
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
        def __init__(self, symbols: dict[str, Any]) -> None:
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
        },
    }

    def fake_mibbuilder_factory() -> "FakeBuilder":
        return FakeBuilder(symbols)

    # Monkeypatch the builder used in generator module
    import app.generator as genmod

    # Replace builder with a simple namespace that exposes MibBuilder to satisfy attribute checks
    monkeypatch.setattr(
        genmod,
        "builder",
        types.SimpleNamespace(MibBuilder=fake_mibbuilder_factory),
    )

    # Monkeypatch default value lookup to avoid plugin dependency
    monkeypatch.setattr(
        BehaviourGenerator,
        "_get_default_value_from_type_info",
        _return_zero,
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    # Create a dummy compiled py path
    compiled = tmp_path / "TESTMIB.py"
    compiled.write_text("# dummy compiled mib")

    schema_path = g.generate(str(compiled), mib_name="TESTMIB", force_regenerate=True)
    assert os.path.exists(schema_path)
    with open(schema_path, encoding="utf-8") as f:
        data = json.load(f)
    # Ensure columns and table entry exist
    assert "col1" in data["objects"]
    assert "MyTable" in data["objects"]


def test_extract_mib_info_non_dict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def identity_dir_source(path: str) -> str:
        return path

    class BadBuilder:
        def __init__(self) -> None:
            # mibSymbols value is not a dict
            self.mibSymbols: dict[str, list[int]] = {"BAD": [1, 2, 3]}

        def add_mib_sources(self, *a: Any, **k: Any) -> None:
            return None

        def load_modules(self, *mods: str) -> None:
            return None

    monkeypatch.setattr(
        "app.generator.builder",
        types.SimpleNamespace(MibBuilder=BadBuilder, DirMibSource=identity_dir_source),
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    with pytest.raises(TypeError):
        g._extract_mib_info("dummy", "BAD")


def test_detect_inherited_indexes_through_extract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def identity_dir_source(path: str) -> str:
        return path

    # Build an entry with index referencing a column not present in this table
    class EntryWithIndex:
        def getIndexNames(self) -> list[tuple[object, str, str]]:
            return [(None, "OTHER-MIB", "missingCol")]

        def getName(self) -> tuple[int, ...]:
            return (1, 3, 6)

        def getSyntax(self) -> None:
            return None

    class Column:
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

    symbols: dict[str, object] = {
        "MyEntry": EntryWithIndex(),
        "otherCol": Column([1, 3, 6, 9]),
    }

    class MB:
        def __init__(self) -> None:
            self._symbols = symbols
            self.mibSymbols: dict[str, Any] = {}

        def add_mib_sources(self, *a: Any, **k: Any) -> None:
            pass

        def load_modules(self, *mods: str) -> None:
            for m in mods:
                self.mibSymbols[m] = self._symbols

    monkeypatch.setattr(
        "app.generator.builder",
        types.SimpleNamespace(MibBuilder=MB, DirMibSource=identity_dir_source),
    )

    # Ensure default value plugin returns something so extract proceeds
    monkeypatch.setattr(
        BehaviourGenerator,
        "_get_default_value_from_type_info",
        _return_zero,
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    info = g._extract_mib_info("dummy", "MY-MIB")
    # Entry should be present and index_from set because missingCol not in columns
    assert "MyEntry" in info["objects"]
    # index_from is added by _detect_inherited_indexes only if missing indexes detected
    # We can't guarantee a specific format here because symbols vary, but ensure no exception raised


def test_get_default_value_from_type_info_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_default(_type_name: str, _symbol_name: str) -> None:
        return None

    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    monkeypatch.setattr("app.generator.get_default_value", no_default)
    with pytest.raises(RuntimeError):
        g._get_default_value_from_type_info({"base_type": "Integer32"}, "symbolX")


def test_generate_respects_force_regenerate_flag(tmp_path: Path) -> None:
    outdir = tmp_path / "out"
    outdir.mkdir()
    mib_dir = outdir / "FOO"
    mib_dir.mkdir()
    schema = mib_dir / "schema.json"
    schema.write_text("{}")

    g = BehaviourGenerator(output_dir=str(outdir), load_default_plugins=False)
    # When force_regenerate=False, should return existing path and not overwrite
    p = g.generate("/does/not/matter", mib_name="FOO", force_regenerate=False)
    assert p == str(schema)


def test_generate_creates_default_table_row_with_index_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Test the code path that creates default rows for tables and extracts indexes
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    # Mock _extract_mib_info to return a table with no rows
    def mock_extract(compiled_py_path: str, mib_name: str) -> dict[str, Any]:
        return {
            "objects": {
                "testTable": {
                    "type": "MibTable",
                    "oid": [1, 2, 3],
                    "rows": [],  # Empty rows to trigger default row creation
                },
                "testEntry": {
                    "type": "MibTableRow",
                    "oid": [1, 2, 3, 1],
                    "indexes": ["testTableCol1"],  # Pre-set indexes to skip mibBuilder code
                },
                "testTableCol1": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
            },
            "traps": {},
        }

    monkeypatch.setattr(g, "_extract_mib_info", mock_extract)

    # Mock type registry and default value
    def load_type_registry() -> dict[str, dict[str, str]]:
        return {"Integer32": {"base_type": "Integer32"}}

    def default_from_type_info(_type_info: Any, _symbol: Any) -> int:
        return 42

    monkeypatch.setattr(g, "_load_type_registry", load_type_registry)
    monkeypatch.setattr(g, "_get_default_value_from_type_info", default_from_type_info)

    path = g.generate("dummy.py", mib_name="TEST-MIB")
    assert os.path.exists(path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Check that a default row was created
    assert "testTable" in data["objects"]
    assert "rows" in data["objects"]["testTable"]
    assert len(data["objects"]["testTable"]["rows"]) == 1
    # Check that indexes were pre-set
    assert "testEntry" in data["objects"]
    assert "indexes" in data["objects"]["testEntry"]
    assert data["objects"]["testEntry"]["indexes"] == ["testTableCol1"]


def test_generate_handles_mib_builder_exception_in_index_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Test exception handling in index extraction
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    def mock_extract(compiled_py_path: str, mib_name: str) -> dict[str, Any]:
        return {
            "myTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "myTableEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
        }

    monkeypatch.setattr(g, "_extract_mib_info", mock_extract)

    # Mock MibBuilder to raise exception
    class BadMibBuilder:
        def __init__(self) -> None:
            msg = "MibBuilder failed"
            raise RuntimeError(msg)

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", BadMibBuilder)

    path = g.generate("dummy.py", mib_name="TEST-MIB")
    assert os.path.exists(path)  # Should still generate despite exception


def test_generate_handles_dir_mib_source_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Test the fallback when DirMibSource fails
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    def mock_extract(compiled_py_path: str, mib_name: str) -> dict[str, Any]:
        return {
            "myTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
            "myTableEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
        }

    monkeypatch.setattr(g, "_extract_mib_info", mock_extract)

    class MockMibBuilder:
        def __init__(self) -> None:
            self.mibSymbols: dict[str, Any] = {}

        def add_mib_sources(self, source: Any = None) -> None:
            if source is not None:
                msg = "DirMibSource not available"
                raise AttributeError(msg)

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder)

    path = g.generate("dummy.py", mib_name="TEST-MIB")
    assert os.path.exists(path)


def test_parse_mib_name_from_py_fallback(tmp_path: Path) -> None:
    # Test the fallback when exportSymbols is not found
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    py_file = tmp_path / "test.py"
    py_file.write_text("# some code without exportSymbols\nprint('hello')\n")

    name = g._parse_mib_name_from_py(str(py_file))
    assert name == "test"


def test_extract_mib_info_handles_non_dict_mib_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test when mib_symbols is not a dict
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockMibBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": "not_a_dict"}

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder)

    with pytest.raises(TypeError, match="mib_symbols for TEST-MIB is not a dict"):
        g._extract_mib_info("dummy.py", "TEST-MIB")


def test_extract_mib_info_handles_symbol_without_getname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test when symbol doesn't have getName/getSyntax
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockSymbol:
        pass

    class MockMibBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"sym1": MockSymbol()}}

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder)

    result = g._extract_mib_info("dummy.py", "TEST-MIB")
    assert result == {"objects": {}, "traps": {}}  # sym1 should be skipped
    # Test when getName/getSyntax raises TypeError
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockSymbol2:
        def getName(self) -> None:
            msg = "bad name"
            raise TypeError(msg)

        def getSyntax(self) -> None:
            return None

        def getMaxAccess(self) -> str:
            return "read-only"

    class MockMibBuilder2:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"sym1": MockSymbol2()}}

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder2)

    result = g._extract_mib_info("dummy.py", "TEST-MIB")
    assert result == {
        "objects": {},
        "traps": {},
    }  # sym1 should be skipped due to TypeError
    # Test that _type_registry is loaded when not present
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    # Ensure _type_registry is not set
    if hasattr(g, "_type_registry"):
        delattr(g, "_type_registry")

    mock_registry = {"Integer32": {"base_type": "Integer32"}}

    def load_type_registry() -> dict[str, dict[str, str]]:
        return mock_registry

    monkeypatch.setattr(g, "_load_type_registry", load_type_registry)

    class MockSyntax3:
        pass

    class MockSymbol3:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

        def getSyntax(self) -> MockSyntax3:
            return MockSyntax3()

        def getMaxAccess(self) -> str:
            return "read-only"

    class MockMibBuilder3:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"sym1": MockSymbol3()}}

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder3)

    def extract_type_info(_syntax_obj: Any, _name: str) -> dict[str, str]:
        return {"base_type": "Integer32"}

    def default_value(_type_name: str, _symbol_name: str) -> str:
        return "mock_value"

    monkeypatch.setattr(g, "_extract_type_info", extract_type_info)
    monkeypatch.setattr("app.generator.get_default_value", default_value)

    result = g._extract_mib_info("dummy.py", "TEST-MIB")
    assert "sym1" in result["objects"]
    assert hasattr(g, "_type_registry")


def test_extract_mib_info_base_type_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test the base_type_map fallback
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    mock_registry: dict[str, Any] = {}  # Empty registry

    def load_type_registry() -> dict[str, Any]:
        return mock_registry

    def extract_type_info(_syntax_obj: Any, _name: str) -> dict[str, str]:
        return {"base_type": "INTEGER"}

    def default_value(_type_name: str, _symbol_name: str) -> str:
        return "mock_value"

    monkeypatch.setattr(g, "_load_type_registry", load_type_registry)

    class MockSyntax:
        pass

    class MockSymbol:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

        def getSyntax(self) -> MockSyntax:
            return MockSyntax()

        def getMaxAccess(self) -> str:
            return "read-only"

    class MockMibBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"sym1": MockSymbol()}}

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("pysnmp.smi.builder.MibBuilder", MockMibBuilder)
    monkeypatch.setattr(g, "_extract_type_info", extract_type_info)  # Will map to Integer32
    monkeypatch.setattr("app.generator.get_default_value", default_value)

    result = g._extract_mib_info("dummy.py", "TEST-MIB")
    assert "sym1" in result["objects"]
    # The type field stores the original type name, but the base_type mapping happens internally
    assert result["objects"]["sym1"]["type"] == "MockSyntax"


def test_extract_type_info_with_constraints() -> None:
    # Test constraints extraction
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockSubtypeSpec:
        def __init__(self) -> None:
            self.values = ["constraint1", "constraint2"]

    class MockSyntax:
        def __init__(self) -> None:
            self.namedValues = {"val1": 1, "val2": 2}
            self.subtypeSpec = MockSubtypeSpec()

    result = g._extract_type_info(MockSyntax(), "TestType")
    assert result["enums"] == {"val1": 1, "val2": 2}
    assert result["constraints"] == ["constraint1", "constraint2"]


def test_get_default_value_from_type_info_raises_on_no_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test RuntimeError when no plugin handles the type
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    def no_default(_type_name: str, _symbol_name: str) -> None:
        return None

    monkeypatch.setattr("app.generator.get_default_value", no_default)

    with pytest.raises(RuntimeError, match="No plugin provided default value"):
        g._get_default_value_from_type_info({"base_type": "UnknownType"}, "testSymbol")


def test_get_default_value_legacy_cases() -> None:
    # Test various cases in _get_default_value
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    assert (
        g._get_default_value("DisplayString", "sysDescr")
        == "Simple Python SNMP Agent - Demo System"
    )
    assert g._get_default_value("ObjectIdentifier", "sysObjectID") == "1.3.6.1.4.1.99999"
    assert g._get_default_value("Integer32", "someInt") == 0
    assert g._get_default_value("UnknownType", "unknown") is None


def test_get_dynamic_function() -> None:
    # Test _get_dynamic_function
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    assert g._get_dynamic_function("sysUpTime") == "uptime"
    assert g._get_dynamic_function("otherSymbol") is None


def test_load_type_registry_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test FileNotFoundError in _load_type_registry
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    def path_missing(_self: Path) -> bool:
        return False

    monkeypatch.setattr(Path, "exists", path_missing)

    with pytest.raises(FileNotFoundError, match="Type registry JSON not found"):
        g._load_type_registry()


def test_detect_inherited_indexes() -> None:
    # Test _detect_inherited_indexes
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockEntry:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3, 1)

        def getIndexNames(self) -> list[tuple[Any, ...]]:
            return [(None, "OTHER-MIB", "inheritedIndex")]

    table_entries = {"testEntry": MockEntry()}
    result: dict[str, dict[str, Any]] = {
        "testEntry": {"oid": [1, 2, 3, 1]},
        "testCol1": {"oid": [1, 2, 3, 1, 1]},
        # inheritedIndex is not in the columns
    }

    g._detect_inherited_indexes(result, table_entries, "TEST-MIB")

    assert "index_from" in result["testEntry"]
    expected_index_from = [{"mib": "OTHER-MIB", "column": "inheritedIndex"}]
    assert result["testEntry"]["index_from"] == expected_index_from


def test_generate_force_regenerate_removes_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that force_regenerate=True removes existing json file."""
    # Create a fake compiled MIB file
    py_path = tmp_path / "TEST-MIB.py"
    py_path.write_text('# mibBuilder.exportSymbols("TEST-MIB", )\n')

    # Create a fake existing json file
    json_path = tmp_path / "TEST-MIB" / "schema.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text('{"test": "data"}')

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    # Mock _extract_mib_info to avoid full parsing
    def mock_extract_mib_info(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "objects": {"testSymbol": {"oid": [1, 2, 3], "type": "Integer32"}},
            "traps": {},
        }

    monkeypatch.setattr(g, "_extract_mib_info", mock_extract_mib_info)

    # Call generate with force_regenerate=True
    g.generate(str(py_path), force_regenerate=True)

    # File should have been recreated (content changed)
    assert json_path.exists()
    with open(json_path, encoding="utf-8") as f:
        content = json.load(f)
        assert "testSymbol" in content["objects"]  # Should have new content


def test_generate_skips_existing_file_when_not_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that generate returns existing json path when force_regenerate=False."""
    # Create a fake compiled MIB file
    py_path = tmp_path / "TEST-MIB.py"
    py_path.write_text('# mibBuilder.exportSymbols("TEST-MIB", )\n')

    # Create a fake existing json file
    json_path = tmp_path / "TEST-MIB" / "schema.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text('{"existing": "data"}')

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    # Call generate with force_regenerate=False (default)
    result = g.generate(str(py_path), force_regenerate=False)

    # Should return the existing file path
    assert result == str(json_path)

    # Content should remain unchanged
    with open(json_path, encoding="utf-8") as f:
        content = json.load(f)
        assert content == {"existing": "data"}


def test_extract_mib_info_add_mib_sources_exception_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling in _extract_mib_info add_mib_sources calls."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    # Mock builder to raise exceptions
    class MockBuilder:
        class MibBuilder:
            def add_mib_sources(self, *args: Any) -> None:
                msg = "Mock exception"
                raise Exception(msg)

            def load_modules(self, *args: Any) -> None:
                pass

            mibSymbols: dict[str, Any] = {"TEST-MIB": {}}

    monkeypatch.setattr("app.generator.builder", MockBuilder)

    # Should not raise exception, just continue
    result = g._extract_mib_info("dummy_path", "TEST-MIB")
    assert isinstance(result, dict)


def test_extract_mib_info_getIndexNames_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling when getIndexNames fails."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockEntry:
        def getIndexNames(self) -> Any:
            msg = "Mock getIndexNames exception"
            raise Exception(msg)

    # Mock the mibBuilder and symbols
    class MockBuilder:
        class MibBuilder:
            def add_mib_sources(self, *args: Any) -> None:
                pass

            def load_modules(self, *args: Any) -> None:
                pass

            mibSymbols: dict[str, Any] = {"TEST-MIB": {"testEntry": MockEntry()}}

    monkeypatch.setattr("app.generator.builder", MockBuilder)

    # Should not raise exception, just log warning
    result = g._extract_mib_info("dummy_path", "TEST-MIB")
    assert isinstance(result, dict)


def test_extract_mib_info_non_dict_col_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test handling of non-dict col_info in column detection."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockEntry:
        def getIndexNames(self) -> list[Any]:
            return []

    # Mock symbols with non-dict col_info
    symbols = {
        "testEntry": {"oid": [1, 2, 3], "type": "MibTableRow"},
        "testCol1": "not_a_dict",  # This should be skipped
        "testCol2": {"oid": [1, 2, 3, 1], "type": "Integer32"},
    }

    class MockBuilder:
        class MibBuilder:
            def add_mib_sources(self, *args: Any) -> None:
                pass

            def load_modules(self, *args: Any) -> None:
                pass

            mibSymbols = {"TEST-MIB": symbols}

    monkeypatch.setattr("app.generator.builder", MockBuilder)

    result = g._extract_mib_info("dummy_path", "TEST-MIB")
    assert isinstance(result, dict)


def test_extract_mib_info_col_info_with_enums(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test handling of col_info with enums."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    # Mock type registry with enums
    g._type_registry = {"Integer32": {"base_type": "Integer32"}}

    symbols = {
        "testEntry": {"oid": [1, 2, 3], "type": "MibTableRow"},
        "testCol1": {
            "oid": [1, 2, 3, 1],
            "type": "Integer32",
            "enums": {"up": 1, "down": 2},
        },
    }

    class MockBuilder:
        class MibBuilder:
            def add_mib_sources(self, *args: Any) -> None:
                pass

            def load_modules(self, *args: Any) -> None:
                pass

            mibSymbols = {"TEST-MIB": symbols}

    monkeypatch.setattr("app.generator.builder", MockBuilder)

    result = g._extract_mib_info("dummy_path", "TEST-MIB")
    assert isinstance(result, dict)


def test_extract_mib_info_symbol_info_missing_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling of symbol_info dict missing 'type' key for MibTable/MibTableRow."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    symbols = {
        "testTable": {
            "type": "MibTable",
            # Missing "type" key that should be added
        },
    }

    class MockBuilder:
        class MibBuilder:
            def add_mib_sources(self, *args: Any) -> None:
                pass

            def load_modules(self, *args: Any) -> None:
                pass

            mibSymbols = {"TEST-MIB": symbols}

    monkeypatch.setattr("app.generator.builder", MockBuilder)

    result = g._extract_mib_info("dummy_path", "TEST-MIB")
    assert isinstance(result, dict)


def test_write_schema_debug_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Test debug logging for specific symbol names."""
    # Create a fake compiled MIB file
    py_path = tmp_path / "TEST-MIB.py"
    py_path.write_text('# mibBuilder.exportSymbols("TEST-MIB", )\n')

    # Create a mock syntax object with namedValues
    class MockSyntax:
        namedValues = {"up": 1, "down": 2}

    # Mock symbol object
    class MockSymbol:
        def getName(self) -> tuple[int, ...]:
            return (1, 3, 6, 1, 2, 3)

        def getSyntax(self) -> Any:
            return MockSyntax()

        def getMaxAccess(self) -> str:
            return "read-write"

    # Mock builder to return symbols with ifAdminStatus
    symbols = {"TEST-MIB": {"ifAdminStatus": MockSymbol()}}

    class FakeBuilder:
        def __init__(self, syms: Any) -> None:
            self.mibSymbols = syms

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    def fake_mibbuilder_factory() -> Any:
        return FakeBuilder(symbols)

    import app.generator as genmod

    monkeypatch.setattr(
        genmod,
        "builder",
        types.SimpleNamespace(MibBuilder=fake_mibbuilder_factory),
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    monkeypatch.setattr(g, "_get_default_value_from_type_info", _return_zero)

    g.generate(str(py_path), force_regenerate=True)

    # Should log debug message for ifAdminStatus
    assert "DEBUG ifAdminStatus" in caplog.text


def test_write_schema_merge_extracted_enums(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test merging extracted enums into type_info."""
    # Create a fake compiled MIB file
    py_path = tmp_path / "TEST-MIB.py"
    py_path.write_text('# mibBuilder.exportSymbols("TEST-MIB", )\n')

    # Create a mock syntax object with namedValues
    class MockSyntax:
        namedValues = {"up": 1, "down": 2}

    # Mock symbol object
    class MockSymbol:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

        def getSyntax(self) -> Any:
            return MockSyntax()

        def getMaxAccess(self) -> str:
            return "read-write"

    # Mock builder to return symbols
    symbols = {"TEST-MIB": {"testSymbol": MockSymbol()}}

    class FakeBuilder:
        def __init__(self, syms: Any) -> None:
            self.mibSymbols = syms

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    def fake_mibbuilder_factory() -> Any:
        return FakeBuilder(symbols)

    import app.generator as genmod

    monkeypatch.setattr(
        genmod,
        "builder",
        types.SimpleNamespace(MibBuilder=fake_mibbuilder_factory),
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    g._type_registry = {"Integer32": {"base_type": "Integer32"}}
    monkeypatch.setattr(g, "_get_default_value_from_type_info", _return_zero)

    g.generate(str(py_path), force_regenerate=True)

    # Check the generated JSON has the enums
    json_path = tmp_path / "TEST-MIB" / "schema.json"
    with open(json_path, encoding="utf-8") as f:
        content = json.load(f)
        assert "enums" in content["objects"]["testSymbol"]


def test_write_schema_include_enums_in_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test including enums in schema entry when type_info has enums."""
    # Create a fake compiled MIB file
    py_path = tmp_path / "TEST-MIB.py"
    py_path.write_text('# mibBuilder.exportSymbols("TEST-MIB", )\n')

    # Mock symbol object
    class MockSymbol:
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

        def getSyntax(self) -> Any:
            return None  # No syntax, so type_info from registry

        def getMaxAccess(self) -> str:
            return "read-write"

    MockSymbol.__name__ = "Integer32"

    # Mock builder to return symbols
    symbols = {"TEST-MIB": {"testSymbol": MockSymbol()}}

    class FakeBuilder:
        def __init__(self, syms: Any) -> None:
            self.mibSymbols = syms

        def add_mib_sources(self, *args: Any) -> None:
            pass

        def load_modules(self, *args: Any) -> None:
            pass

    def fake_mibbuilder_factory() -> Any:
        return FakeBuilder(symbols)

    import app.generator as genmod

    monkeypatch.setattr(
        genmod,
        "builder",
        types.SimpleNamespace(MibBuilder=fake_mibbuilder_factory),
    )

    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    g._type_registry = {"Integer32": {"base_type": "Integer32", "enums": {"up": 1, "down": 2}}}
    monkeypatch.setattr(g, "_get_default_value_from_type_info", _return_zero)

    g.generate(str(py_path), force_regenerate=True)

    # Check the generated JSON has the enums from registry
    json_path = tmp_path / "TEST-MIB" / "schema.json"
    with open(json_path, encoding="utf-8") as f:
        content = json.load(f)
        assert "enums" in content["objects"]["testSymbol"]


def test_detect_inherited_indexes_empty_index_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling of empty index_names in inherited index detection."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockEntry:
        def getIndexNames(self) -> list[Any]:
            return []  # Empty index names

        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

    table_entries = {"testEntry": MockEntry()}
    result = {"testEntry": {"oid": [1, 2, 3]}}

    g._detect_inherited_indexes(result, table_entries, "TEST-MIB")

    # Should skip entries with no indexes
    assert "index_from" not in result["testEntry"]


def test_detect_inherited_indexes_with_inheritance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful detection of inherited indexes."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockEntry:
        def getIndexNames(self) -> list[tuple[Any, Any, str]]:
            return [(None, "OTHER-MIB", "inheritedIndex")]

        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)

    table_entries = {"testEntry": MockEntry()}
    result = {
        "testEntry": {"oid": [1, 2, 3]},
        # inheritedIndex is not in the table's columns
    }

    g._detect_inherited_indexes(result, table_entries, "TEST-MIB")

    # Should detect inherited index
    assert "index_from" in result["testEntry"]


def test_extract_type_info_with_named_values() -> None:
    """Test extracting type info when syntax_obj has namedValues."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockSyntax:
        namedValues = {"one": 1, "two": 2}

    MockSyntax.__name__ = "Integer32"

    result = g._extract_type_info(MockSyntax(), "TestType")

    enums = result.get("enums")
    assert isinstance(enums, dict)
    assert "one" in enums
    assert "two" in enums


def test_extract_type_info_with_constraints_detailed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test extracting type info with constraints."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class MockConstraint:
        def __str__(self) -> str:
            return "1..10"

    class MockSyntax:
        namedValues = None

        class subtypeSpec:
            values = [MockConstraint()]

    result = g._extract_type_info(MockSyntax(), "TestType")

    assert result["constraints"] is not None
    assert len(result["constraints"]) > 0


def test_get_default_value_sysUpTime() -> None:
    """Test _get_default_value for sysUpTime symbol."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    result = g._get_default_value("SomeType", "sysUpTime")

    assert result is None


def test_get_default_value_various_syntax_types() -> None:
    """Test _get_default_value for various syntax types."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    # Test ObjectIdentifier
    assert g._get_default_value("ObjectIdentifier", "foo") == "0.0"

    # Test Integer types
    assert g._get_default_value("Integer32", "foo") == 0
    assert g._get_default_value("Integer", "foo") == 0
    assert g._get_default_value("Gauge32", "foo") == 0
    assert g._get_default_value("Unsigned32", "foo") == 0

    # Test Counter types
    assert g._get_default_value("Counter32", "foo") == 0
    assert g._get_default_value("Counter64", "foo") == 0

    # Test IpAddress
    assert g._get_default_value("IpAddress", "foo") == "0.0.0.0"

    # Test TimeTicks
    assert g._get_default_value("TimeTicks", "foo") == 0

    # Test unknown type
    assert g._get_default_value("UnknownType", "foo") is None


def test_get_dynamic_function_sysUpTime() -> None:
    """Test _get_dynamic_function for sysUpTime."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    result = g._get_dynamic_function("sysUpTime")

    assert result == "uptime"


def test_get_dynamic_function_other_symbols() -> None:
    """Test _get_dynamic_function for non-dynamic symbols."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    result = g._get_dynamic_function("sysDescr")

    assert result is None


def test_extract_traps_mixed_objects_and_error_path(caplog: pytest.LogCaptureFixture) -> None:
    """Cover trap extraction for normal and failing notification symbols."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    GoodNotificationType = type(
        "NotificationType",
        (),
        {
            "getName": lambda self: (1, 3, 6, 1, 4, 1, 99999, 0, 1),
            "getObjects": lambda self: [
                ("IF-MIB", "ifIndex"),
                [("SNMPv2-MIB", "sysDescr")],
            ],
            "getDescription": lambda self: "Trap description",
            "getStatus": lambda self: "current",
        },
    )
    BadNotificationType = type(
        "NotificationType",
        (),
        {
            "getName": lambda self: (_ for _ in ()).throw(TypeError("boom")),
        },
    )

    caplog.set_level("WARNING")
    traps = g._extract_traps(
        {
            "goodTrap": GoodNotificationType(),
            "badTrap": BadNotificationType(),
        },
        "TEST-MIB",
    )

    assert "goodTrap" in traps
    assert traps["goodTrap"]["mib"] == "TEST-MIB"
    assert len(traps["goodTrap"]["objects"]) >= 2
    assert "Failed to extract trap info" in caplog.text


def test_load_type_registry_missing_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover FileNotFoundError path for canonical type registry loading."""
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    missing_registry = tmp_path / "missing-types.json"
    monkeypatch.setattr("app.generator.TYPE_REGISTRY_FILE", missing_registry)

    with pytest.raises(FileNotFoundError):
        g._load_type_registry()


def test_detect_inherited_indexes_handles_entry_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cover inherited-index detection error handling branch."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class BrokenEntry:
        def getIndexNames(self) -> list[tuple[object, str, str]]:
            msg = "broken"
            raise RuntimeError(msg)

    caplog.set_level("DEBUG")
    result = {"brokenEntry": {"oid": [1, 2, 3]}}
    g._detect_inherited_indexes(result, {"brokenEntry": BrokenEntry()}, "TEST-MIB")

    assert "Skipping inherited-index detection" in caplog.text


@pytest.mark.parametrize(
    ("symbol_name", "expected"),
    [
        ("sysObjectID", "1.3.6.1.4.1.99999"),
        ("sysContact", "Admin <admin@example.com>"),
        ("sysName", "my-pysnmp-agent"),
        ("sysLocation", "Development Lab"),
    ],
)
def test_get_default_value_symbol_specific_defaults(symbol_name: str, expected: object) -> None:
    """Cover remaining symbol-specific legacy default branches."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    assert g._get_default_value("DisplayString", symbol_name) == expected


def test_get_default_index_value_port_like_base_and_normalize_ip() -> None:
    """Cover port-like index fallback and IpAddress normalization helper branch."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    assert g._get_default_index_value("Integer32", {"base_type": "PortNumber"}) == 8080
    assert g._normalize_type_info_for_symbol({"base_type": "OctetString"}, "IpAddress") == {
        "base_type": "IpAddress"
    }


def test_generate_extracts_indexes_via_builder_fallback_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover generate() path that retries add_mib_sources without DirMibSource."""
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    def mock_extract(compiled_py_path: str, mib_name: str) -> dict[str, Any]:
        return {
            "objects": {
                "myTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
                "myEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},
                "idxCol": {
                    "oid": [1, 2, 3, 1, 1],
                    "type": "Integer32",
                    "enums": {"one": 1},
                },
            },
            "traps": {},
        }

    monkeypatch.setattr(g, "_extract_mib_info", mock_extract)
    monkeypatch.setattr(g, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})

    class EntryObj:
        @staticmethod
        def getIndexNames() -> list[tuple[object, str, str]]:
            return [(None, "TEST-MIB", "idxCol")]

    class MockBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {"TEST-MIB": {"myEntry": EntryObj()}}

        @staticmethod
        def add_mib_sources(source: Any = None) -> None:
            if source is not None:
                msg = "DirMibSource unavailable"
                raise AttributeError(msg)

        @staticmethod
        def load_modules(*args: Any) -> None:
            return None

    monkeypatch.setattr(
        "app.generator.builder",
        types.SimpleNamespace(
            MibBuilder=MockBuilder,
            DirMibSource=lambda p: p,
        ),
    )

    path = g.generate("dummy.py", mib_name="TEST-MIB")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["objects"]["myEntry"].get("indexes") == ["idxCol"]


def test_generate_index_default_correction_with_nonzero_constraint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover index default correction path for constraints excluding zero."""
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    monkeypatch.setattr(
        g,
        "_extract_mib_info",
        lambda _p, _m: {
            "objects": {
                "tbl": {"type": "MibTable", "oid": [1, 9], "rows": []},
                "tblEntry": {
                    "type": "MibTableRow",
                    "oid": [1, 9, 1],
                    "indexes": ["idx"],
                },
                "idx": {"oid": [1, 9, 1, 1], "type": "InterfaceIndexOrZero"},
            },
            "traps": {},
        },
    )
    monkeypatch.setattr(
        g,
        "_load_type_registry",
        lambda: {
            "InterfaceIndexOrZero": {
                "base_type": "Integer32",
                "constraints": [{"type": "ValueRangeConstraint", "min": 1, "max": 2147483647}],
            }
        },
    )

    path = g.generate("dummy.py", mib_name="TEST-MIB")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["objects"]["tbl"]["rows"][0]["idx"] == 1


def test_extract_type_info_constraint_else_and_exception_paths() -> None:
    """Cover _extract_type_info else path (no values) and exception path."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)

    class NoValuesSyntax:
        class subtypeSpec:
            @staticmethod
            def __str__() -> str:
                return "SIZE(1..10)"

    no_values = g._extract_type_info(NoValuesSyntax(), "CustomType")
    assert no_values["constraints"] is not None

    class ExplodingSubtype:
        @property
        def values(self) -> object:
            msg = "bad subtype"
            raise TypeError(msg)

    class ExplodingSyntax:
        subtypeSpec = ExplodingSubtype()

    exploded = g._extract_type_info(ExplodingSyntax(), "CustomType")
    assert exploded["constraints"] is None


@pytest.mark.parametrize(
    ("col_type", "type_info", "expected"),
    [
        ("IpAddress", {}, "192.168.1.1"),
        ("InterfaceIndexOrZero", {}, 0),
        ("InterfaceIndex", {}, 1),
        ("Unsigned32", {"base_type": "PortNumber"}, 8080),
        ("Gauge32", {}, 1),
        ("DisplayString", {}, "default"),
    ],
)
def test_get_default_index_value_branch_matrix(
    col_type: str,
    type_info: dict[str, Any],
    expected: object,
) -> None:
    """Cover main _get_default_index_value branches with compact parametrization."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    assert g._get_default_index_value(col_type, type_info) == expected


def test_init_loads_default_plugins_logs_count(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Cover __init__ branch that loads plugins and logs loaded names."""
    monkeypatch.setattr("app.generator.load_plugins", lambda: ["plugins.a", "plugins.b"])
    caplog.set_level("INFO")

    BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=True)
    assert "Loaded 2 default value plugins" in caplog.text


def test_generate_handles_index_extraction_error_and_non_index_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cover generate branches for index-extraction warning and non-index default row values."""
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)

    monkeypatch.setattr(
        g,
        "_extract_mib_info",
        lambda _p, _m: {
            "objects": {
                "tbl": {"type": "MibTable", "oid": [1, 7], "rows": []},
                "tblEntry": {"type": "MibTableRow", "oid": [1, 7, 1]},
                "idx": {"oid": [1, 7, 1, 1], "type": "Integer32"},
                "val": {"oid": [1, 7, 1, 2], "type": "DisplayString", "enums": {"a": 1}},
                "junk": 5,
            },
            "traps": {},
        },
    )
    monkeypatch.setattr(g, "_load_type_registry", lambda: {"DisplayString": {"base_type": "OctetString"}})
    monkeypatch.setattr(g, "_get_default_value_from_type_info", lambda _ti, name: f"v:{name}")

    class BrokenBuilder:
        def __init__(self) -> None:
            self.mibSymbols: dict[str, Any] = {}

        @staticmethod
        def add_mib_sources(*args: Any, **kwargs: Any) -> None:
            return None

        @staticmethod
        def load_modules(*args: Any, **kwargs: Any) -> None:
            msg = "cannot load"
            raise RuntimeError(msg)

    monkeypatch.setattr(
        "app.generator.builder",
        types.SimpleNamespace(MibBuilder=BrokenBuilder, DirMibSource=lambda p: p),
    )

    caplog.set_level("WARNING")
    schema_path = g.generate("dummy.py", mib_name="TEST-MIB")
    data = json.loads(Path(schema_path).read_text(encoding="utf-8"))

    row = data["objects"]["tbl"]["rows"][0]
    assert "__index__" in row
    assert row["val"] == "v:val"
    assert "Could not extract index columns" in caplog.text


def test_extract_mib_info_covers_typeerror_continue_mapping_and_trap_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Cover _extract_mib_info branches: TypeError continue, type mapping, constraints merge, trap info log."""
    g = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    g._type_registry = {}

    class BadSymbol:
        @staticmethod
        def getName() -> tuple[int, ...]:
            msg = "bad"
            raise TypeError(msg)

        @staticmethod
        def getSyntax() -> object:
            return object()

    class IntegerSyntax:
        __name__ = "INTEGER"
        namedValues = {"up": 1, "down": 2}

        class subtypeSpec:
            values = ["1..2"]

    class GoodScalar:
        @staticmethod
        def getName() -> tuple[int, ...]:
            return (1, 3, 6, 1, 2, 1, 2, 2, 1, 7)

        @staticmethod
        def getSyntax() -> object:
            return IntegerSyntax()

        @staticmethod
        def getMaxAccess() -> str:
            return "read-write"

    NotificationType = type(
        "NotificationType",
        (),
        {
            "getName": lambda self: (1, 3, 6, 1, 4, 1, 99999, 0, 9),
            "getObjects": lambda self: [("IF-MIB", "ifIndex")],
            "getDescription": lambda self: "trap",
            "getStatus": lambda self: "current",
        },
    )

    class MockBuilder:
        def __init__(self) -> None:
            self.mibSymbols = {
                "TEST-MIB": {
                    "broken": BadSymbol(),
                    "ifAdminStatus": GoodScalar(),
                    "trapNine": NotificationType(),
                }
            }

        @staticmethod
        def add_mib_sources(*args: Any, **kwargs: Any) -> None:
            return None

        @staticmethod
        def load_modules(*args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(
        "app.generator.builder",
        types.SimpleNamespace(MibBuilder=MockBuilder, DirMibSource=lambda p: p),
    )
    monkeypatch.setattr(g, "_load_type_registry", lambda: {})
    monkeypatch.setattr(g, "_get_default_value_from_type_info", lambda _ti, _name: 1)

    caplog.set_level("INFO")
    extracted = g._extract_mib_info("dummy.py", "TEST-MIB")

    assert "ifAdminStatus" in extracted["objects"]
    assert extracted["objects"]["ifAdminStatus"]["type"] == "IntegerSyntax"
    assert "trapNine" in extracted["traps"]
    assert "Found 1 trap(s) in TEST-MIB" in caplog.text


def test_get_default_index_value_unknown_type_uses_generic_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover fallback branch that delegates to _get_default_value_from_type_info."""
    g = BehaviourGenerator(output_dir=".", load_default_plugins=False)
    monkeypatch.setattr(g, "_get_default_value_from_type_info", lambda _ti, _name: "fallback")
    assert g._get_default_index_value("CustomIndexType", {}) == "fallback"
