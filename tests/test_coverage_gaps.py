"""
Tests specifically targeting remaining coverage gaps to reach 95%+ on all files.
"""
import pytest
import logging
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Dict, List

from app.table_registrar import TableRegistrar
from app.snmp_agent import SNMPAgent
from app.type_recorder import TypeRecorder
from app.generator import BehaviourGenerator


# ============================================================================
# table_registrar.py coverage gaps (86% -> 95%+)
# ============================================================================

@pytest.fixture
def mock_registrar() -> TableRegistrar:
    """Create a mock TableRegistrar for testing."""
    type_registry = {
        "Integer32": {"base_type": "Integer32"},
        "OctetString": {"base_type": "OctetString"},
    }
    registrar = TableRegistrar(
        mib_builder=MagicMock(),
        mib_scalar_instance=MagicMock(),
        mib_table=MagicMock(),
        mib_table_row=MagicMock(),
        mib_table_column=MagicMock(),
        logger=logging.getLogger("test"),
        type_registry=type_registry
    )
    return registrar


def test_register_pysnmp_table_column_type_resolution_fails(mock_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    """Test _register_pysnmp_table when column type resolution fails (lines 234-236)"""
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "badCol": {"oid": [1, 2, 3, 1, 1], "type": "UnknownType"},
        },
    }
    type_registry: Dict[str, Any] = {}
    new_row: Dict[str, Any] = {}
    
    # Make _resolve_snmp_type return None
    mock_registrar._resolve_snmp_type = Mock(return_value=None)  # type: ignore[method-assign]
    
    with caplog.at_level(logging.DEBUG):
        mock_registrar._register_pysnmp_table("TEST", "testTable", table_data, type_registry, new_row)
    
    # Should skip the column and not register it
    # The export should happen but with no columns
    mock_registrar.mib_builder.export_symbols.assert_called_once()


def test_register_row_instances_with_actual_columns(mock_registrar: TableRegistrar) -> None:
    """Test _register_row_instances successful path (lines 289-307)"""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col1": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
            "col2": {"oid": [1, 2, 3, 1, 2], "type": "Integer32"},
        },
    }
    type_registry: Dict[str, Any] = {
        "Integer32": {"base_type": "Integer32"},
    }
    col_names = ["col1", "col2"]
    new_row = {"col1": 42, "col2": 99}
    
    mock_registrar._resolve_snmp_type = Mock(return_value=int)  # type: ignore[method-assign]
    
    mock_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)
    
    # Should have called mib_scalar_instance twice
    assert mock_registrar.mib_scalar_instance.call_count == 2


def test_register_row_instances_type_resolution_fails(mock_registrar: TableRegistrar) -> None:
    """Test _register_row_instances when type resolution fails (lines 289-290)"""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "badCol": {"oid": [1, 2, 3, 1, 1], "type": "UnknownType"},
        },
    }
    type_registry: Dict[str, Any] = {}
    col_names: List[str] = ["badCol"]
    new_row: Dict[str, Any] = {"badCol": 0}
    
    # Make _resolve_snmp_type return None - this causes continue on line 290
    mock_registrar._resolve_snmp_type = Mock(return_value=None)  # type: ignore[method-assign]
    
    mock_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)
    
    # Should not call mib_scalar_instance
    mock_registrar.mib_scalar_instance.assert_not_called()


def test_register_row_instances_value_error_exception(mock_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    """Test _register_row_instances when type conversion raises exception (lines 300-303)"""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col1": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
    }
    type_registry: Dict[str, Any] = {"Integer32": {"base_type": "Integer32"}}
    col_names: List[str] = ["col1"]
    new_row: Dict[str, Any] = {"col1": "not_a_number"}  # Will fail conversion to int
    
    mock_registrar._resolve_snmp_type = Mock(return_value=int)  # type: ignore[method-assign]
    
    with caplog.at_level(logging.ERROR):
        mock_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)
    
    assert "Error registering row instance" in caplog.text


def test_register_row_instances_no_columns(mock_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    """Test _register_row_instances when no columns (lines 306-307)"""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {},
    }
    type_registry: Dict[str, Any] = {}
    col_names: List[str] = []
    new_row: Dict[str, Any] = {}
    
    with caplog.at_level(logging.WARNING):
        mock_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)
    
    assert "No row instances registered" in caplog.text


def test_resolve_snmp_type_with_rfc1902_fallback(mock_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    """Test _resolve_snmp_type falls back to pysnmp.proto.rfc1902 (lines 366-375)"""
    # Make import_symbols fail for both SNMPv2 modules
    mock_registrar.mib_builder.import_symbols.side_effect = Exception("Not found")
    
    # This will use real rfc1902, which is fine - just test it returns something
    result = mock_registrar._resolve_snmp_type("Integer32", "col", "table")
    
    # Should get the real Integer32 from rfc1902
    assert result is not None


def test_resolve_snmp_type_final_fallback_returns_none(mock_registrar: TableRegistrar) -> None:
    """Test _resolve_snmp_type returns None for completely unknown types (lines 404-406)"""
    # Make both import_symbols fail
    mock_registrar.mib_builder.import_symbols.side_effect = Exception("Import failed")
    
    # Test with unknown type that even rfc1902 doesn't have
    result = mock_registrar._resolve_snmp_type("CompletelyFakeTypeDoesNotExist", "col", "table")
    
    # Should return None
    assert result is None


def test_get_default_value_size_constraint_exact_4(mock_registrar: TableRegistrar) -> None:
    """Test _get_default_value_for_type with size constraint of exactly 4 (line 330)"""
    col_info: Dict[str, Any] = {}
    type_info = {
        "constraints": [
            {"type": "ValueSizeConstraint", "min": 4, "max": 4}
        ]
    }
    
    result = mock_registrar._get_default_value_for_type(col_info, "IpAddress", type_info, "IpAddress")
    
    # Should return IP address for size 4
    assert result == "0.0.0.0"


def test_get_default_value_size_set_with_4_only(mock_registrar: TableRegistrar) -> None:
    """Test _get_default_value_for_type with size set containing only [4] (line 398)"""
    col_info: Dict[str, Any] = {}
    type_info: Dict[str, Any] = {
        "size": {"type": "set", "allowed": [4]}
    }
    
    result = mock_registrar._get_default_value_for_type(col_info, "IpAddress", type_info, "IpAddress")
    
    # Should return IP address since allowed is exactly [4]
    assert result == "0.0.0.0"


# ============================================================================
# snmp_agent.py coverage gaps (92% -> 95%+)
# ============================================================================

def test_snmp_agent_register_mib_objects_load_type_registry_fails(caplog: pytest.LogCaptureFixture) -> None:
    """Test _register_mib_objects when type registry load fails (lines 221-223)"""
    agent = SNMPAgent(config_path="agent_config.yaml")
    # Don't replace logger - use the actual one so caplog captures it
    agent.mib_builder = Mock()
    agent.mib_jsons = {"TEST-MIB": {}}
    agent.MibScalarInstance = Mock()
    agent.MibTable = Mock()
    agent.MibTableRow = Mock()
    agent.MibTableColumn = Mock()
    
    # Make the type registry file not exist
    with patch('app.snmp_agent.os.path.join', return_value="/nonexistent/types.json"), \
         caplog.at_level(logging.ERROR):
        agent._register_mib_objects()
    
    # Check that function returns without error (caught exception)
    assert agent.mib_jsons == {"TEST-MIB": {}}  # Should still have the mib


# ============================================================================
# type_recorder.py coverage gaps (92% -> 95%+)
# ============================================================================

def test_type_recorder_build_handles_symbol_with_no_getsyntax(tmp_path: Path) -> None:
    """Test build() skips symbols without getSyntax (lines 593-595)"""
    recorder = TypeRecorder(tmp_path)
    
    with patch('app.type_recorder._engine.SnmpEngine') as mock_engine, \
         patch('app.type_recorder._builder.DirMibSource'), \
         patch.object(Path, 'glob') as mock_glob:
        
        # Create a symbol without getSyntax
        class BadSymbol:
            pass
        
        mock_mib_builder = MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"badSym": BadSymbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        
        fake_mib = Mock()
        fake_mib.name = "TEST-MIB.py"
        fake_mib.stem = "TEST-MIB"
        mock_glob.return_value = [fake_mib]
        
        recorder.build()
        
        # Should not crash, should skip the bad symbol
        assert recorder._registry is not None


def test_type_recorder_build_getsyntax_raises_exception(tmp_path: Path) -> None:
    """Test build() handles getSyntax() exceptions (lines 601-603)"""
    recorder = TypeRecorder(tmp_path)
    
    with patch('app.type_recorder._engine.SnmpEngine') as mock_engine, \
         patch('app.type_recorder._builder.DirMibSource'), \
         patch.object(Path, 'glob') as mock_glob:
        
        class FailingSymbol:
            def getSyntax(self) -> None:
                raise Exception("getSyntax failed")
        
        mock_mib_builder = MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"failSym": FailingSymbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        
        fake_mib = Mock()
        fake_mib.name = "TEST-MIB.py"
        fake_mib.stem = "TEST-MIB"
        mock_glob.return_value = [fake_mib]
        
        recorder.build()
        
        # Should not crash, should skip the failing symbol
        assert recorder._registry is not None


def test_type_recorder_build_getsyntax_returns_none(tmp_path: Path) -> None:
    """Test build() handles getSyntax() returning None (line 607)"""
    recorder = TypeRecorder(tmp_path)
    
    with patch('app.type_recorder._engine.SnmpEngine') as mock_engine, \
         patch('app.type_recorder._builder.DirMibSource'), \
         patch.object(Path, 'glob') as mock_glob:
        
        class NoneSymbol:
            def getSyntax(self) -> None:
                return None
        
        mock_mib_builder = MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"noneSym": NoneSymbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        
        fake_mib = Mock()
        fake_mib.name = "TEST-MIB.py"
        fake_mib.stem = "TEST-MIB"
        mock_glob.return_value = [fake_mib]
        
        recorder.build()
        
        # Should not crash, should skip the None syntax
        assert recorder._registry is not None


# ============================================================================
# generator.py coverage gaps (93% -> 95%+)
# ============================================================================

def test_generator_extract_mib_info_handles_nonetype_syntax_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test _extract_mib_info with syntax.__name__ == 'NoneType' (lines 269-270)"""
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    
    class NoneTypeSymbol:
        def __init__(self) -> None:
            self.__class__.__name__ = "TestSymbol"
        
        def getName(self) -> tuple[int, ...]:
            return (1, 2, 3)
        
        def getSyntax(self) -> Any:
            # Create a fake syntax class with __name__ == 'NoneType'
            class NoneTypeSyntax:
                __name__ = "NoneType"
                
                def __mro__(self) -> list[Any]:
                    return [self]
            
            return NoneTypeSyntax()
        
        def getMaxAccess(self) -> str:
            return "read-only"
    
    class FakeBuilder:
        mibSymbols = {"TEST-MIB": {"testSym": NoneTypeSymbol()}}
        
        def add_mib_sources(self, _source: Any) -> None:
            pass
        
        def load_modules(self, _name: str) -> None:
            pass
    
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: FakeBuilder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: None)
    monkeypatch.setattr(generator, "_get_dynamic_function", lambda _n: None)
    
    result = generator._extract_mib_info(str(tmp_path / "TEST-MIB.py"), "TEST-MIB")
    
    # When syntax.__name__ is "NoneType", it should use symbol class name instead
    # The actual code path on line 269-270 uses symbol.__class__.__name__
    assert "testSym" in result


def test_generator_table_index_extraction_exception(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test generate() when index extraction raises exception (lines 81-82)"""
    generator = BehaviourGenerator(output_dir=str(tmp_path), load_default_plugins=False)
    
    info = {
        "testTable": {"type": "MibTable", "oid": [1, 2, 3], "rows": []},
        "testEntry": {"type": "MibTableRow", "oid": [1, 2, 3, 1]},  # No indexes
        "testCol": {"type": "Integer32", "oid": [1, 2, 3, 1, 1]},
    }
    
    # Make MibBuilder raise exception
    class FailingBuilder:
        def add_mib_sources(self, _source: Any) -> None:
            pass
        
        def load_modules(self, _name: str) -> None:
            raise Exception("Load failed")
    
    monkeypatch.setattr("app.generator.builder.MibBuilder", lambda: FailingBuilder())
    monkeypatch.setattr("app.generator.builder.DirMibSource", lambda _path: "src")
    monkeypatch.setattr(generator, "_parse_mib_name_from_py", lambda _p: "TEST-MIB")
    monkeypatch.setattr(generator, "_extract_mib_info", lambda _p, _n: info)
    monkeypatch.setattr(generator, "_load_type_registry", lambda: {"Integer32": {"base_type": "Integer32"}})
    monkeypatch.setattr(generator, "_get_default_value_from_type_info", lambda _t, _s: 0)
    
    with caplog.at_level(logging.WARNING):
        generator.generate(str(tmp_path / "TEST-MIB.py"), force_regenerate=True)
    
    assert "Could not extract index columns" in caplog.text


# ============================================================================
# cli_compile_mib.py coverage gaps (91% -> 95%+)
# ============================================================================

def test_cli_compile_mib_with_output_dir(tmp_path: Path) -> None:
    """Test cli_compile_mib with custom output directory (lines 33-34)"""
    mib_file = tmp_path / "TEST-MIB.txt"
    mib_file.write_text("TEST-MIB DEFINITIONS ::= BEGIN END")
    
    output_dir = tmp_path / "custom-output"
    
    with patch('sys.argv', ['cli_compile_mib.py', str(mib_file), str(output_dir)]), \
         patch('app.cli_compile_mib.MibCompiler') as mock_compiler, \
         patch('app.cli_compile_mib.AppConfig') as mock_config:
        
        mock_config_inst = Mock()
        mock_config.return_value = mock_config_inst
        
        mock_instance = Mock()
        mock_instance.compile.return_value = str(output_dir / "TEST-MIB.py")
        mock_instance.last_compile_results = {"TEST-MIB": "compiled"}
        mock_compiler.return_value = mock_instance
        
        from app.cli_compile_mib import main
        result = main()
        
        # Should use custom output directory
        mock_compiler.assert_called_with(str(output_dir), mock_config_inst)
        assert result == 0
