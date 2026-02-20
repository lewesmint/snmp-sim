"""Tests for TableRegistrar class."""

import pytest
from app.table_registrar import TableRegistrar
from app.types import TypeRegistry
from typing import Any, Dict
from pytest_mock import MockerFixture
import logging


@pytest.fixture
def logger() -> logging.Logger:
    """Create a test logger."""
    return logging.getLogger("test")


@pytest.fixture
def type_registry() -> TypeRegistry:
    """Create a mock type registry."""
    return {
        "Integer32": {"base_type": "Integer32"},
        "OctetString": {"base_type": "OctetString"},
        "Counter32": {"base_type": "Counter32"},
    }


@pytest.fixture
def table_registrar(mocker: MockerFixture, logger: logging.Logger, type_registry: TypeRegistry) -> TableRegistrar:
    """Create a TableRegistrar instance with mocked dependencies."""
    mib_builder = mocker.MagicMock()
    mib_scalar_instance = mocker.MagicMock()
    mib_table = mocker.MagicMock()
    mib_table_row = mocker.MagicMock()
    mib_table_column = mocker.MagicMock()
    
    return TableRegistrar(
        mib_builder=mib_builder,
        mib_scalar_instance=mib_scalar_instance,
        mib_table=mib_table,
        mib_table_row=mib_table_row,
        mib_table_column=mib_table_column,
        logger=logger,
        type_registry=type_registry,
    )


def test_table_registrar_initialization(table_registrar: TableRegistrar) -> None:
    """Test that TableRegistrar initializes correctly."""
    assert table_registrar.mib_builder is not None
    assert table_registrar.mib_scalar_instance is not None
    assert table_registrar.mib_table is not None
    assert table_registrar.mib_table_row is not None
    assert table_registrar.mib_table_column is not None
    assert table_registrar.logger is not None


def test_find_table_related_objects_identifies_tables(table_registrar: TableRegistrar) -> None:
    """Test that find_table_related_objects correctly identifies table structures."""
    mib_json = {
        'ifTable': {'oid': [1, 3, 6, 1, 2, 1, 2, 2], 'access': 'not-accessible'},
        'ifEntry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
        'ifDescr': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2], 'type': 'OctetString', 'access': 'read-only'},
        'sysDescr': {'oid': [1, 3, 6, 1, 1, 1, 0], 'type': 'OctetString', 'access': 'read-only'},
    }
    
    table_related = table_registrar.find_table_related_objects(mib_json)
    
    # Table components should be identified
    assert 'ifTable' in table_related
    assert 'ifEntry' in table_related
    assert 'ifIndex' in table_related
    assert 'ifDescr' in table_related
    
    # Scalars should not be identified
    assert 'sysDescr' not in table_related


def test_find_table_related_objects_identifies_columns_by_oid_hierarchy(table_registrar: TableRegistrar) -> None:
    """Test that columns are identified by OID hierarchy."""
    mib_json = {
        'ifTable': {'oid': [1, 3, 6, 1, 2, 1, 2, 2], 'access': 'not-accessible'},
        'ifEntry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        # Column - direct child of entry
        'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32'},
        # Not a column - not direct child (too deep)
        'ifAliasExtra': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1], 'type': 'OctetString'},
        # Not a column - not in entry hierarchy
        'ifMtu': {'oid': [1, 3, 6, 1, 2, 1, 2, 1, 1], 'type': 'Integer32'},
    }
    
    table_related = table_registrar.find_table_related_objects(mib_json)
    
    # Direct child of entry should be identified as column
    assert 'ifIndex' in table_related
    # Not direct child should not be identified
    assert 'ifAliasExtra' not in table_related
    # Not in hierarchy should not be identified
    assert 'ifMtu' not in table_related


def test_get_default_value_for_integer_type(table_registrar: TableRegistrar) -> None:
    """Test default value generation for integer types."""
    col_info: Dict[str, Any] = {}
    type_info = {'base_type': 'Integer32'}
    
    value = table_registrar._get_default_value_for_type(col_info, 'Integer32', type_info, 'Integer32')
    assert value == 0


def test_get_default_value_for_string_type(table_registrar: TableRegistrar) -> None:
    """Test default value generation for string types."""
    col_info: Dict[str, Any] = {}
    type_info = {'base_type': 'OctetString'}
    
    value = table_registrar._get_default_value_for_type(col_info, 'DisplayString', type_info, 'OctetString')
    assert value == 'Unset'


def test_get_default_value_uses_initial_if_present(table_registrar: TableRegistrar) -> None:
    """Test that initial value is used if present."""
    col_info = {'initial': 42}
    type_info = {'base_type': 'Integer32'}
    
    value = table_registrar._get_default_value_for_type(col_info, 'Integer32', type_info, 'Integer32')
    assert value == 42


def test_get_default_value_for_enumerated_type(table_registrar: TableRegistrar) -> None:
    """Test default value for enumerated types uses first enum value."""
    col_info: Dict[str, Any] = {}
    type_info = {
        'base_type': 'Integer32',
        'enums': [
            {'name': 'up', 'value': 1},
            {'name': 'down', 'value': 2},
        ]
    }
    
    value = table_registrar._get_default_value_for_type(col_info, 'InterfaceStatus', type_info, 'Integer32')
    assert value == 1


def test_get_default_value_for_constrained_type(table_registrar: TableRegistrar) -> None:
    """Test default value for constrained types."""
    col_info: Dict[str, Any] = {}
    type_info = {
        'base_type': 'Integer32',
        'constraints': [
            {'type': 'ValueRangeConstraint', 'min': 0, 'max': 100}
        ]
    }
    
    value = table_registrar._get_default_value_for_type(col_info, 'PercentageType', type_info, 'Integer32')
    assert value == 0


def test_register_tables_creates_table_structure(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test that register_tables processes tables correctly."""
    mib_json = {
        'testTable': {'oid': [1, 3, 6, 1, 4, 1, 9999, 1, 1], 'access': 'not-accessible', 'type': 'MibTable'},
        'testEntry': {'oid': [1, 3, 6, 1, 4, 1, 9999, 1, 1, 1], 'type': 'MibTableRow'},
        'testIndex': {'oid': [1, 3, 6, 1, 4, 1, 9999, 1, 1, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
        'testValue': {'oid': [1, 3, 6, 1, 4, 1, 9999, 1, 1, 1, 2], 'type': 'OctetString', 'access': 'read-only'},
    }
    
    mib_jsons = {'TEST-MIB': mib_json.copy()}
    type_registry = {
        'Integer32': {'base_type': 'Integer32'},
        'OctetString': {'base_type': 'OctetString'},
    }
    
    # Mock register_single_table to verify it gets called
    mock_register = mocker.patch.object(table_registrar, 'register_single_table')
    
    table_registrar.register_tables('TEST-MIB', mib_json, type_registry, mib_jsons)
    
    # Verify register_single_table was called for the table
    mock_register.assert_called_once()
    call_args = mock_register.call_args
    assert call_args[0][0] == 'TEST-MIB'
    assert call_args[0][1] == 'testTable'


def test_register_tables_skips_when_classes_missing(logger: logging.Logger, caplog: pytest.LogCaptureFixture) -> None:
    type_registry: TypeRegistry = {}
    registrar = TableRegistrar(
        mib_builder=None,
        mib_scalar_instance=None,
        mib_table=None,
        mib_table_row=None,
        mib_table_column=None,
        logger=logger,
        type_registry=type_registry,
    )
    with caplog.at_level(logging.WARNING):
        registrar.register_tables("TEST-MIB", {}, {}, {})
    assert "Skipping table registration" in caplog.text


def test_register_single_table_missing_mib_json(table_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1], "indexes": []},
        "columns": {},
        "prefix": "test",
    }
    with caplog.at_level(logging.ERROR):
        table_registrar.register_single_table("TEST-MIB", "testTable", table_data, {}, {})
    assert "No in-memory JSON found" in caplog.text


def test_register_single_table_creates_row(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    mib_jsons: Dict[str, Any] = {"TEST-MIB": {"placeholder": {}}}
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1], "indexes": ["idx"]},
        "columns": {
            "idx": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
            "val": {"oid": [1, 2, 3, 1, 2], "type": "OctetString"},
        },
        "prefix": "test",
    }
    type_registry = {
        "Integer32": {"base_type": "Integer32"},
        "OctetString": {"base_type": "OctetString"},
    }
    mock_register = mocker.patch.object(table_registrar, "_register_pysnmp_table")

    table_registrar.register_single_table("TEST-MIB", "testTable", table_data, type_registry, mib_jsons)

    rows = mib_jsons["TEST-MIB"]["testTable"]["rows"]
    assert rows and rows[0]["idx"] == 1
    assert rows[0]["val"] == 'Unset'
    mock_register.assert_called_once()


def test_register_pysnmp_table_no_builder(logger: logging.Logger) -> None:
    type_registry : TypeRegistry = {}
    registrar = TableRegistrar(
        mib_builder=None,
        mib_scalar_instance=None,
        mib_table=None,
        mib_table_row=None,
        mib_table_column=None,
        logger=logger,
        type_registry=type_registry,
    )
    registrar._register_pysnmp_table("TEST", "testTable", {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {},
    }, {}, {})


def test_register_pysnmp_table_export_error(table_registrar: TableRegistrar, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    table_registrar.mib_builder.export_symbols.side_effect = Exception("boom")
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
    }
    mocker.patch.object(table_registrar, "_resolve_snmp_type", return_value=int)
    mocker.patch.object(table_registrar, "_register_row_instances")

    with caplog.at_level(logging.ERROR):
        table_registrar._register_pysnmp_table("TEST", "testTable", table_data, {"Integer32": {"base_type": "Integer32"}}, {"col": 1})
    # TableRegistrar does not export table symbols; ensure we did not attempt to call export_symbols
    table_registrar.mib_builder.export_symbols.assert_not_called()


def test_register_row_instances_empty_columns(table_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {},
    }
    with caplog.at_level(logging.WARNING):
        table_registrar._register_row_instances("TEST", "testTable", table_data, {}, [], {})
    assert "No row instances registered" in caplog.text


def test_resolve_snmp_type_import_error(table_registrar: TableRegistrar, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    table_registrar.mib_builder.import_symbols.side_effect = Exception("fail")

    original_import = __import__

    def fake_import(name: str, globals: Dict[str, Any] | None = None, locals: Dict[str, Any] | None = None, fromlist: tuple[str, ...] = (), level: int = 0) -> Any:
        if name == "pysnmp.proto":
            raise ImportError("boom")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with caplog.at_level(logging.ERROR):
        result = table_registrar._resolve_snmp_type("Integer32", "col", "table")
    assert result is None
    assert "Error resolving SNMP type" in caplog.text


def test_get_default_value_for_size_constraints(table_registrar: TableRegistrar) -> None:
    col_info: Dict[str, Any] = {}
    type_info: Dict[str, Any] = {
        "constraints": [
            {"type": "ValueSizeConstraint", "min": 4, "max": 4}
        ]
    }
    value = table_registrar._get_default_value_for_type(col_info, "IpAddress", type_info, "")
    assert value == "0.0.0.0"

    type_info_2: Dict[str, Any] = {"size": {"type": "set", "allowed": [4]}}
    value = table_registrar._get_default_value_for_type(col_info, "IpAddress", type_info_2, "")
    assert value == "0.0.0.0"


def test_register_row_instances_handles_errors(table_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    table_registrar.mib_scalar_instance.side_effect = Exception("boom")
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
    }
    col_names = ["col"]
    new_row = {"col": 5}
    type_registry = {"Integer32": {"base_type": "Integer32"}}

    with caplog.at_level(logging.ERROR):
        table_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)
    assert "Error registering row instance" in caplog.text


def test_resolve_snmp_type_empty_base(table_registrar: TableRegistrar) -> None:
    result = table_registrar._resolve_snmp_type("", "col", "table")
    assert result is None


def test_resolve_snmp_type_returns_type_or_none(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test that _resolve_snmp_type handles resolution correctly."""
    # Setup mock to return a type
    mock_type = mocker.MagicMock()
    table_registrar.mib_builder.import_symbols.return_value = (mock_type,)
    
    result = table_registrar._resolve_snmp_type('Integer32', 'testCol', 'testTable')
    
    # Verify import_symbols was called
    table_registrar.mib_builder.import_symbols.assert_called()
    assert result == mock_type


def test_resolve_snmp_type_tries_multiple_modules(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test that _resolve_snmp_type tries SNMPv2-SMI then SNMPv2-TC."""
    # Setup mock to fail on first attempt, succeed on second
    mock_type = mocker.MagicMock()
    table_registrar.mib_builder.import_symbols.side_effect = [
        Exception("Not in SNMPv2-SMI"),
        (mock_type,)
    ]
    
    result = table_registrar._resolve_snmp_type('DisplayString', 'testCol', 'testTable')
    
    # Should have called import_symbols twice
    assert table_registrar.mib_builder.import_symbols.call_count == 2
    assert result == mock_type


def test_register_tables_missing_entry(table_registrar: TableRegistrar) -> None:
    """Test register_tables skips tables without corresponding entry"""
    mib_json = {
        'testTable': {'oid': [1, 2, 3], 'access': 'not-accessible'},
        # No testEntry - should be skipped
    }
    
    mib_jsons = {'TEST-MIB': mib_json}
    
    # Should not raise exception, should skip the table
    table_registrar.register_tables('TEST-MIB', mib_json, {}, mib_jsons)


def test_register_tables_no_columns(table_registrar: TableRegistrar) -> None:
    """Test register_tables skips tables with no columns"""
    mib_json = {
        'testTable': {'oid': [1, 2, 3], 'access': 'not-accessible'},
        'testEntry': {'oid': [1, 2, 3, 1]},
        # No columns - should be skipped
    }
    
    mib_jsons = {'TEST-MIB': mib_json}
    
    # Should not process table without columns
    table_registrar.register_tables('TEST-MIB', mib_json, {}, mib_jsons)


def test_register_single_table_no_rows_in_json(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test register_single_table when table_json exists but has no rows key"""
    mib_jsons = {"TEST-MIB": {"testTable": {"oid": [1, 2, 3]}}}  # No 'rows' key
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1], "indexes": ["idx"]},
        "columns": {
            "idx": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
        "prefix": "test",
    }
    type_registry = {"Integer32": {"base_type": "Integer32"}}
    mocker.patch.object(table_registrar, "_register_pysnmp_table")

    table_registrar.register_single_table("TEST-MIB", "testTable", table_data, type_registry, mib_jsons)

    # Should create rows key
    assert "rows" in mib_jsons["TEST-MIB"]["testTable"]


def test_find_table_related_objects_with_non_dict_column_info(table_registrar: TableRegistrar) -> None:
    """Test find_table_related_objects handles non-dict column info"""
    mib_json = {
        'testEntry': {'oid': [1, 2, 3, 1]},
        'invalidCol': "not a dict",  # Should be skipped
    }
    
    table_related = table_registrar.find_table_related_objects(mib_json)
    
    assert 'testEntry' in table_related
    assert 'invalidCol' not in table_related


def test_register_tables_logs_warning_on_exception(table_registrar: TableRegistrar, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    """Test register_tables logs warning when register_single_table fails."""
    mib_json = {
        'testTable': {'oid': [1, 2, 3], 'access': 'not-accessible', 'type': 'MibTable'},
        'testEntry': {'oid': [1, 2, 3, 1], 'type': 'MibTableRow'},
        'testCol': {'oid': [1, 2, 3, 1, 1], 'type': 'Integer32'},
        'badCol': "not a dict",
    }
    mib_jsons = {'TEST-MIB': mib_json.copy()}
    mocker.patch.object(table_registrar, 'register_single_table', side_effect=RuntimeError("boom"))

    with caplog.at_level(logging.WARNING):
        table_registrar.register_tables('TEST-MIB', mib_json, {}, mib_jsons)

    assert "Could not register table testTable" in caplog.text


def test_register_single_table_skips_missing_index(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test register_single_table ignores index names not present in row."""
    mib_jsons: Dict[str, Any] = {"TEST-MIB": {"testTable": {"rows": []}}}
    table_data = {
        "table": {"oid": [1, 2, 3]},
        "entry": {"oid": [1, 2, 3, 1], "indexes": ["missingIdx"]},
        "columns": {
            "val": {"oid": [1, 2, 3, 1, 2], "type": "OctetString"},
        },
        "prefix": "test",
    }
    type_registry = {"OctetString": {"base_type": "OctetString"}}
    mocker.patch.object(table_registrar, "_register_pysnmp_table")

    table_registrar.register_single_table("TEST-MIB", "testTable", table_data, type_registry, mib_jsons)

    rows = mib_jsons["TEST-MIB"]["testTable"]["rows"]
    assert rows and rows[0]["val"] == 'Unset'
    assert "missingIdx" not in rows[0]


def test_register_row_instances_uses_default_when_missing_value(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test _register_row_instances falls back to default when value is None."""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
    }
    col_names = ["col"]
    new_row: Dict[str, Any] = {}
    type_registry = {"Integer32": {"base_type": "Integer32"}}

    mocker.patch.object(table_registrar, "_resolve_snmp_type", return_value=int)
    mocker.patch.object(table_registrar, "_get_default_value_for_type", return_value=7)

    table_registrar._register_row_instances("TEST", "testTable", table_data, type_registry, col_names, new_row)

    table_registrar.mib_scalar_instance.assert_called_once()
    table_registrar.mib_builder.export_symbols.assert_called_once()


def test_register_row_instances_skips_unresolved_type(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test _register_row_instances skips columns when type cannot be resolved."""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "col": {"oid": [1, 2, 3, 1, 1], "type": "UnknownType"},
        },
    }
    col_names = ["col"]
    new_row = {"col": 1}

    mocker.patch.object(table_registrar, "_resolve_snmp_type", return_value=None)

    table_registrar._register_row_instances("TEST", "testTable", table_data, {}, col_names, new_row)

    table_registrar.mib_scalar_instance.assert_not_called()


def test_get_default_value_for_object_identifier(table_registrar: TableRegistrar) -> None:
    """Test default value for ObjectIdentifier base type."""
    col_info: Dict[str, Any] = {}
    type_info = {"base_type": "ObjectIdentifier"}

    value = table_registrar._get_default_value_for_type(col_info, "MyOid", type_info, "ObjectIdentifier")
    assert value == (0, 0)


def test_get_default_value_for_value_size_constraint_non_ip(table_registrar: TableRegistrar) -> None:
    """Test ValueSizeConstraint returns empty string when size is not IP."""
    col_info: Dict[str, Any] = {}
    type_info = {"constraints": [{"type": "ValueSizeConstraint", "min": 1, "max": 10}]}

    value = table_registrar._get_default_value_for_type(col_info, "OctetString", type_info, "")
    assert value == 'Unset'


def test_get_default_value_for_size_set_non_ip(table_registrar: TableRegistrar) -> None:
    """Test size set constraint returns empty string for non-IP sizes."""
    col_info: Dict[str, Any] = {}
    type_info = {"size": {"type": "set", "allowed": [8]}}

    value = table_registrar._get_default_value_for_type(col_info, "OctetString", type_info, "")
    assert value == 'Unset'


def test_get_default_value_for_size_range(table_registrar: TableRegistrar) -> None:
    """Test size range constraint returns empty string."""
    col_info: Dict[str, Any] = {}
    type_info = {"size": {"type": "range", "min": 1, "max": 255}}

    value = table_registrar._get_default_value_for_type(col_info, "OctetString", type_info, "")
    assert value == 'Unset'


def test_register_tables_ignores_non_child_columns(table_registrar: TableRegistrar, mocker: MockerFixture) -> None:
    """Test register_tables skips columns that are not direct children of entry OID."""
    mib_json = {
        'testTable': {'oid': [1, 2, 3], 'access': 'not-accessible', 'type': 'MibTable'},
        'testEntry': {'oid': [1, 2, 3, 1], 'type': 'MibTableRow'},
        'goodCol': {'oid': [1, 2, 3, 1, 1], 'type': 'Integer32'},
        'badCol': {'oid': [1, 2, 4, 1, 1], 'type': 'Integer32'},
    }
    mib_jsons = {'TEST-MIB': mib_json.copy()}

    mock_register = mocker.patch.object(table_registrar, 'register_single_table')

    table_registrar.register_tables('TEST-MIB', mib_json, {'Integer32': {'base_type': 'Integer32'}}, mib_jsons)

    mock_register.assert_called_once()
    _, _, table_data, _, _ = mock_register.call_args[0]
    assert 'goodCol' in table_data['columns']
    assert 'badCol' not in table_data['columns']


def test_register_row_instances_handles_outer_exception(table_registrar: TableRegistrar, caplog: pytest.LogCaptureFixture) -> None:
    """Test _register_row_instances logs outer exceptions (e.g., missing column)."""
    table_data = {
        "entry": {"oid": [1, 2, 3, 1]},
        "columns": {
            "present": {"oid": [1, 2, 3, 1, 1], "type": "Integer32"},
        },
    }
    col_names = ["missing"]

    with caplog.at_level(logging.ERROR):
        table_registrar._register_row_instances("TEST", "testTable", table_data, {}, col_names, {})

    assert "Error registering row instances" in caplog.text


def test_get_default_value_for_enums_non_list(table_registrar: TableRegistrar) -> None:
    """Test enums present but not a list returns 0."""
    col_info: Dict[str, Any] = {}
    type_info = {"enums": {"up": 1}}

    value = table_registrar._get_default_value_for_type(col_info, "CustomType", type_info, "CustomType")
    assert value == 0


def test_get_default_value_for_value_range_without_base_type(table_registrar: TableRegistrar) -> None:
    """Test ValueRangeConstraint returns 0 when base_type is empty."""
    col_info: Dict[str, Any] = {}
    type_info = {"constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 10}]}

    value = table_registrar._get_default_value_for_type(col_info, "RangeType", type_info, "")
    assert value == 0


def test_get_default_value_unknown_base_no_constraints(table_registrar: TableRegistrar) -> None:
    """Test unknown base type with no constraints falls back to 0."""
    col_info: Dict[str, Any] = {}
    type_info: Dict[str, Any] = {}

    value = table_registrar._get_default_value_for_type(col_info, "CustomType", type_info, "UnknownBase")
    assert value == 0


def test_get_default_value_unknown_constraint_type(table_registrar: TableRegistrar) -> None:
    """Test unknown constraint type falls through to default."""
    col_info: Dict[str, Any] = {}
    type_info = {"constraints": [{"type": "OtherConstraint"}]}

    value = table_registrar._get_default_value_for_type(col_info, "CustomType", type_info, "")
    assert value == 0


def test_get_default_value_size_not_dict(table_registrar: TableRegistrar) -> None:
    """Test size value that is not a dict falls through to default."""
    col_info: Dict[str, Any] = {}
    type_info = {"size": "not-a-dict"}

    value = table_registrar._get_default_value_for_type(col_info, "CustomType", type_info, "")
    assert value == 0


def test_get_default_value_size_unknown_type(table_registrar: TableRegistrar) -> None:
    """Test size dict with unknown type falls through to default."""
    col_info: Dict[str, Any] = {}
    type_info = {"size": {"type": "unknown"}}

    value = table_registrar._get_default_value_for_type(col_info, "CustomType", type_info, "")
    assert value == 0
