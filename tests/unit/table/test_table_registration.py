"""Tests for table registration in SNMPAgent."""

from typing import Any, Dict

import pytest
from pytest_mock import MockerFixture

from app.snmp_agent import SNMPAgent


def _if_table_data() -> Dict[str, Any]:
    """Return canonical IF-MIB-like single-index table data used by multiple tests."""
    return {
        "table": {"oid": [1, 3, 6, 1, 2, 1, 2, 2]},
        "entry": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        "columns": {
            "ifIndex": {
                "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
                "type": "Integer32",
                "access": "not-accessible",
            },
            "ifDescr": {
                "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
                "type": "OctetString",
                "access": "read-only",
            },
        },
        "prefix": "ifTable",
    }


def _assert_basic_table_data(table_data: Dict[str, Any]) -> None:
    """Assert table data has required top-level and per-column fields."""
    assert "table" in table_data
    assert "entry" in table_data
    assert "columns" in table_data
    for col_name, col_info in table_data["columns"].items():
        assert "oid" in col_info, f"Column {col_name} missing OID"
        assert "type" in col_info, f"Column {col_name} missing type"
        assert "access" in col_info, f"Column {col_name} missing access"


@pytest.fixture
def agent(mocker: MockerFixture) -> Any:
    """Create a mocked SNMPAgent for testing."""
    agent = SNMPAgent.__new__(SNMPAgent)
    agent.mib_builder = mocker.MagicMock()
    agent.mib_builder.import_symbols.return_value = []
    agent.snmpEngine = mocker.MagicMock()
    agent.logger = mocker.MagicMock()
    # Patch SNMPAgent dependencies for table registration (use setattr to satisfy mypy)
    setattr(agent, "MibTable", mocker.MagicMock())
    setattr(agent, "MibTableRow", mocker.MagicMock())
    setattr(agent, "MibTableColumn", mocker.MagicMock())
    setattr(agent, "MibScalar", mocker.MagicMock())
    return agent

def test_single_column_index() -> None:
    """Test table structure data with a single column index."""
    table_data = _if_table_data()
    _assert_basic_table_data(table_data)
    assert table_data["prefix"] == "ifTable"


def test_augments_inherited_index(agent: Any) -> None:
    """Test table structure with AUGMENTS inherited index."""
    table_data: Dict[str, Any] = {
        "table": {"oid": [1, 3, 6, 1, 2, 1, 31, 1, 1]},
        "entry": {
            "oid": [1, 3, 6, 1, 2, 1, 31, 1, 1, 1],
            "index_from": [("IF-MIB", "ifEntry", "ifIndex")],
        },
        "columns": {
            "ifIndex": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 1],
                "type": "Integer32",
                "access": "not-accessible",
            },
            "ifName": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 2],
                "type": "OctetString",
                "access": "read-only",
            },
        },
        "prefix": "ifXTable",
    }
    # Verify the agent is properly set up
    assert agent is not None
    # Verify agent has mib_builder available
    assert agent.mib_builder is not None
    # Verify agent has table classes available
    assert agent.MibTable is not None
    assert agent.MibTableRow is not None
    assert agent.MibTableColumn is not None
    # Verify table data structure
    assert "entry" in table_data
    assert "index_from" in table_data["entry"], "AUGMENTS entry should have index_from"
    # Verify inherited index reference format
    index_from = table_data["entry"]["index_from"][0]
    assert len(index_from) == 3, "index_from should be (MIB, Entry, Column) tuple"
    assert index_from[0] == "IF-MIB", "Index should reference IF-MIB"
    assert index_from[1] == "ifEntry", "Index should reference ifEntry"


def test_multi_column_index_inherited_and_local(agent: Any) -> None:
    """Test table structure with multi-column index (inherited + local)."""
    table_data: Dict[str, Any] = {
        "table": {"oid": [1, 3, 6, 1, 2, 1, 31, 4]},
        "entry": {
            "oid": [1, 3, 6, 1, 2, 1, 31, 4, 1],
            "index_from": [("IF-MIB", "ifEntry", "ifIndex")],
        },
        "columns": {
            "ifIndex": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 4, 1, 1],
                "type": "Integer32",
                "access": "not-accessible",
            },
            "ifRcvAddressType": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 4, 1, 2],
                "type": "Integer32",
                "access": "not-accessible",
            },
            "ifRcvAddress": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 4, 1, 3],
                "type": "PhysAddress",
                "access": "not-accessible",
            },
            "ifRcvAddressStatus": {
                "oid": [1, 3, 6, 1, 2, 1, 31, 4, 1, 4],
                "type": "Integer32",
                "access": "read-only",
            },
        },
        "prefix": "ifRcvAddressTable",
    }
    # Verify the agent is properly set up
    assert agent is not None
    assert agent.mib_builder is not None
    # Verify table with multi-column index has proper structure
    assert len(table_data["columns"]) > 2, "Multi-column index table should have multiple columns"
    # Count index columns (access='not-accessible')
    index_columns = [
        col for col, info in table_data["columns"].items() if info.get("access") == "not-accessible"
    ]
    assert len(index_columns) >= 2, "Multi-column index should have at least 2 index columns"
    # Verify inherited index is specified
    assert "index_from" in table_data["entry"]
    # Verify non-index columns exist (those with access != 'not-accessible')
    non_index_columns = [
        col for col, info in table_data["columns"].items() if info.get("access") != "not-accessible"
    ]
    assert len(non_index_columns) > 0, "Table should have non-index columns"


def test_table_structure_validation(agent: Any) -> None:
    """Test that table structures can be validated for proper registration."""
    table_data = _if_table_data()
    _assert_basic_table_data(table_data)

    # Validate entry OID is child of table OID
    table_oid = tuple(table_data["table"]["oid"])
    entry_oid = tuple(table_data["entry"]["oid"])
    assert entry_oid[: len(table_oid)] == table_oid, "Entry OID should be child of table OID"

    # Validate all columns are children of entry OID
    for col_name, col_info in table_data["columns"].items():
        col_oid = tuple(col_info["oid"])
        assert col_oid[: len(entry_oid)] == entry_oid, (
            f"Column {col_name} OID should be child of entry OID"
        )

    # Verify agent can access required MIB classes
    assert agent.MibTable is not None
    assert agent.MibTableRow is not None
    assert agent.MibTableColumn is not None


def test_agent_mib_builder_mock_interaction(agent: Any, mocker: MockerFixture) -> None:
    """Test that agent's mib_builder can be used to import table symbols."""
    # Setup mock to return table classes
    mock_mib_table = mocker.MagicMock()
    mock_mib_table_row = mocker.MagicMock()
    mock_mib_table_column = mocker.MagicMock()

    agent.mib_builder.import_symbols.return_value = (
        mock_mib_table,
        mock_mib_table_row,
        mock_mib_table_column,
    )

    # Call import_symbols
    result = agent.mib_builder.import_symbols(
        "SNMPv2-SMI", "MibTable", "MibTableRow", "MibTableColumn"
    )

    # Verify import_symbols was called with correct arguments
    agent.mib_builder.import_symbols.assert_called_once_with(
        "SNMPv2-SMI", "MibTable", "MibTableRow", "MibTableColumn"
    )

    # Verify result contains the mocked classes
    assert len(result) == 3


# Integration Tests - Testing the full workflow


def test_find_table_related_objects_integration(agent: Any, mocker: MockerFixture) -> None:
    """Test that table discovery correctly identifies table components via TableRegistrar."""
    # Since _find_table_related_objects was refactored to TableRegistrar,
    # this test validates the pattern with the new architecture
    from app.table_registrar import TableRegistrar

    # Simulate a MIB JSON with table structures
    table_data = _if_table_data()
    mib_json: Dict[str, Any] = {
        "ifTable": {
            "oid": table_data["table"]["oid"],
            "access": "not-accessible",
        },
        "ifEntry": {"oid": table_data["entry"]["oid"]},
        **table_data["columns"],
        "sysDescr": {
            "oid": [1, 3, 6, 1, 1, 1, 0],
            "type": "OctetString",
            "access": "read-only",
        },
        "sysObjectID": {
            "oid": [1, 3, 6, 1, 1, 2, 0],
            "type": "ObjectIdentifier",
            "access": "read-only",
        },
    }

    # Create a TableRegistrar to test table discovery
    registrar = TableRegistrar(
        mib_builder=agent.mib_builder,
        mib_scalar_instance=mocker.MagicMock(),
        mib_table=agent.MibTable,
        mib_table_row=agent.MibTableRow,
        mib_table_column=agent.MibTableColumn,
        logger=agent.logger,
    )

    table_related = registrar.find_table_related_objects(mib_json)

    # Verify all table components are identified
    assert "ifTable" in table_related, "Table should be identified"
    assert "ifEntry" in table_related, "Entry should be identified"
    assert "ifIndex" in table_related, "Index column should be identified"
    assert "ifDescr" in table_related, "Table column should be identified"

    # Verify scalar objects are NOT in table_related
    assert "sysDescr" not in table_related, "Scalar should not be in table_related"
    assert "sysObjectID" not in table_related, "Scalar should not be in table_related"


def test_table_column_type_resolution_in_registration(agent: Any, mocker: MockerFixture) -> None:
    """Test registration resolves DisplayString through its OctetString base type."""
    from app.table_registrar import TableRegistrar

    type_registry: Dict[str, Dict[str, Any]] = {
        "Integer32": {"base_type": "Integer32"},
        "OctetString": {"base_type": "OctetString"},
        "DisplayString": {
            "base_type": "OctetString",
            "display_hint": "255a",
            "constraints": {"size": {"max": 255}},
        },
    }

    table_data = _if_table_data()
    table_data["entry"]["indexes"] = ["ifIndex"]
    table_data["columns"]["ifDescr"]["type"] = "DisplayString"

    mib_jsons: Dict[str, Dict[str, Any]] = {"TEST-MIB": {"ifTable": {"rows": []}}}
    registrar = TableRegistrar(
        mib_builder=agent.mib_builder,
        mib_scalar_instance=agent.MibScalar,
        mib_table=agent.MibTable,
        mib_table_row=agent.MibTableRow,
        mib_table_column=agent.MibTableColumn,
        logger=agent.logger,
        type_registry=type_registry,
    )

    mocker.patch.object(registrar, "_register_pysnmp_table")
    registrar.register_single_table("TEST-MIB", "ifTable", table_data, type_registry, mib_jsons)

    rows = mib_jsons["TEST-MIB"]["ifTable"]["rows"]
    assert rows and rows[0]["ifIndex"] == 1
    assert rows[0]["ifDescr"] == "Unset"
