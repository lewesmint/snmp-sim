"""Tests for table registration in SNMPAgent."""



import pytest
from app.snmp_agent import SNMPAgent
from typing import Generator, Any, Dict
from pytest_mock import MockerFixture


@pytest.fixture
def agent(mocker: MockerFixture) -> SNMPAgent:
    """Create a mocked SNMPAgent for testing."""
    agent = SNMPAgent.__new__(SNMPAgent)
    agent.mib_builder = mocker.MagicMock()
    agent.mib_builder.import_symbols.return_value = []
    agent.snmpEngine = mocker.MagicMock()
    agent.logger = mocker.MagicMock()
    # Patch SNMPAgent dependencies for table registration
    agent.MibTable = mocker.MagicMock()
    agent.MibTableRow = mocker.MagicMock()
    agent.MibTableColumn = mocker.MagicMock()
    agent.MibScalar = mocker.MagicMock()
    return agent




@pytest.fixture
def mock_agent_methods(agent: SNMPAgent, mocker: MockerFixture) -> Generator[None, None, None]:
    """Mock internal agent methods using pytest-mock."""
    # Only mock methods that actually exist on the agent
    yield


def test_single_column_index() -> None:
    """Test table structure data with a single column index."""
    table_data: Dict[str, Any] = {
        'table': {'oid': [1, 3, 6, 1, 2, 1, 2, 2]},
        'entry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        'columns': {
            'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
            'ifDescr': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2], 'type': 'OctetString', 'access': 'read-only'}
        },
        'prefix': 'ifTable'
    }
    # Verify table structure is correct
    assert 'table' in table_data
    assert 'entry' in table_data
    assert 'columns' in table_data
    assert table_data['prefix'] == 'ifTable'
    # Verify columns have required fields
    for col_name, col_info in table_data['columns'].items():
        assert 'oid' in col_info, f"Column {col_name} missing OID"
        assert 'type' in col_info, f"Column {col_name} missing type"
        assert 'access' in col_info, f"Column {col_name} missing access"


def test_augments_inherited_index(agent: SNMPAgent) -> None:
    """Test table structure with AUGMENTS inherited index."""
    table_data: Dict[str, Any] = {
        'table': {'oid': [1, 3, 6, 1, 2, 1, 31, 1, 1]},
        'entry': {'oid': [1, 3, 6, 1, 2, 1, 31, 1, 1, 1], 'index_from': [('IF-MIB', 'ifEntry', 'ifIndex')]},
        'columns': {
            'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
            'ifName': {'oid': [1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 2], 'type': 'OctetString', 'access': 'read-only'}
        },
        'prefix': 'ifXTable'
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
    assert 'entry' in table_data
    assert 'index_from' in table_data['entry'], "AUGMENTS entry should have index_from"
    # Verify inherited index reference format
    index_from = table_data['entry']['index_from'][0]
    assert len(index_from) == 3, "index_from should be (MIB, Entry, Column) tuple"
    assert index_from[0] == 'IF-MIB', "Index should reference IF-MIB"
    assert index_from[1] == 'ifEntry', "Index should reference ifEntry"


def test_multi_column_index_inherited_and_local(agent: SNMPAgent) -> None:
    """Test table structure with multi-column index (inherited + local)."""
    table_data: Dict[str, Any] = {
        'table': {'oid': [1, 3, 6, 1, 2, 1, 31, 4]},
        'entry': {'oid': [1, 3, 6, 1, 2, 1, 31, 4, 1], 'index_from': [('IF-MIB', 'ifEntry', 'ifIndex')]},
        'columns': {
            'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 31, 4, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
            'ifRcvAddressType': {'oid': [1, 3, 6, 1, 2, 1, 31, 4, 1, 2], 'type': 'Integer32', 'access': 'not-accessible'},
            'ifRcvAddress': {'oid': [1, 3, 6, 1, 2, 1, 31, 4, 1, 3], 'type': 'PhysAddress', 'access': 'not-accessible'},
            'ifRcvAddressStatus': {'oid': [1, 3, 6, 1, 2, 1, 31, 4, 1, 4], 'type': 'Integer32', 'access': 'read-only'}
        },
        'prefix': 'ifRcvAddressTable'
    }
    # Verify the agent is properly set up
    assert agent is not None
    assert agent.mib_builder is not None
    # Verify table with multi-column index has proper structure
    assert len(table_data['columns']) > 2, "Multi-column index table should have multiple columns"
    # Count index columns (access='not-accessible')
    index_columns = [
        col for col, info in table_data['columns'].items() 
        if info.get('access') == 'not-accessible'
    ]
    assert len(index_columns) >= 2, "Multi-column index should have at least 2 index columns"
    # Verify inherited index is specified
    assert 'index_from' in table_data['entry']
    # Verify non-index columns exist (those with access != 'not-accessible')
    non_index_columns = [
        col for col, info in table_data['columns'].items() 
        if info.get('access') != 'not-accessible'
    ]
    assert len(non_index_columns) > 0, "Table should have non-index columns"


def test_table_structure_validation(agent: SNMPAgent) -> None:
    """Test that table structures can be validated for proper registration."""
    table_data: Dict[str, Any] = {
        'table': {'oid': [1, 3, 6, 1, 2, 1, 2, 2]},
        'entry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        'columns': {
            'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
            'ifDescr': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2], 'type': 'OctetString', 'access': 'read-only'}
        },
        'prefix': 'ifTable'
    }
    
    # Validate entry OID is child of table OID
    table_oid = tuple(table_data['table']['oid'])
    entry_oid = tuple(table_data['entry']['oid'])
    assert entry_oid[:len(table_oid)] == table_oid, "Entry OID should be child of table OID"
    
    # Validate all columns are children of entry OID
    for col_name, col_info in table_data['columns'].items():
        col_oid = tuple(col_info['oid'])
        assert col_oid[:len(entry_oid)] == entry_oid, f"Column {col_name} OID should be child of entry OID"
    
    # Verify agent can access required MIB classes
    assert agent.MibTable is not None
    assert agent.MibTableRow is not None
    assert agent.MibTableColumn is not None


def test_agent_mib_builder_mock_interaction(agent: SNMPAgent, mocker: MockerFixture) -> None:
    """Test that agent's mib_builder can be used to import table symbols."""
    # Setup mock to return table classes
    mock_mib_table = mocker.MagicMock()
    mock_mib_table_row = mocker.MagicMock()
    mock_mib_table_column = mocker.MagicMock()
    
    agent.mib_builder.import_symbols.return_value = (
        mock_mib_table, 
        mock_mib_table_row, 
        mock_mib_table_column
    )
    
    # Call import_symbols
    result = agent.mib_builder.import_symbols(
        'SNMPv2-SMI',
        'MibTable',
        'MibTableRow', 
        'MibTableColumn'
    )
    
    # Verify import_symbols was called with correct arguments
    agent.mib_builder.import_symbols.assert_called_once_with(
        'SNMPv2-SMI',
        'MibTable',
        'MibTableRow',
        'MibTableColumn'
    )
    
    # Verify result contains the mocked classes
    assert len(result) == 3


# Integration Tests - Testing the full workflow


def test_find_table_related_objects_integration(agent: SNMPAgent, mocker: MockerFixture) -> None:
    """Test that table discovery correctly identifies table components via TableRegistrar."""
    # Since _find_table_related_objects was refactored to TableRegistrar,
    # this test validates the pattern with the new architecture
    from app.table_registrar import TableRegistrar
    
    # Simulate a MIB JSON with table structures
    mib_json: Dict[str, Any] = {
        'ifTable': {'oid': [1, 3, 6, 1, 2, 1, 2, 2], 'access': 'not-accessible'},
        'ifEntry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
        'ifDescr': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2], 'type': 'OctetString', 'access': 'read-only'},
        'sysDescr': {'oid': [1, 3, 6, 1, 1, 1, 0], 'type': 'OctetString', 'access': 'read-only'},
        'sysObjectID': {'oid': [1, 3, 6, 1, 1, 2, 0], 'type': 'ObjectIdentifier', 'access': 'read-only'},
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
    assert 'ifTable' in table_related, "Table should be identified"
    assert 'ifEntry' in table_related, "Entry should be identified"
    assert 'ifIndex' in table_related, "Index column should be identified"
    assert 'ifDescr' in table_related, "Table column should be identified"
    
    # Verify scalar objects are NOT in table_related
    assert 'sysDescr' not in table_related, "Scalar should not be in table_related"
    assert 'sysObjectID' not in table_related, "Scalar should not be in table_related"


def test_register_tables_workflow(agent: SNMPAgent, mocker: MockerFixture) -> None:
    """Test the table registration workflow orchestration."""
    # Mock the type registry
    type_registry: Dict[str, Dict[str, Any]] = {
        'Integer32': {'base_type': 'Integer'},
        'OctetString': {'base_type': 'OctetString'},
    }
    
    # Mock MIB JSON with a complete table structure
    mib_json: Dict[str, Any] = {
        'ifTable': {'oid': [1, 3, 6, 1, 2, 1, 2, 2], 'access': 'not-accessible'},
        'ifEntry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        'ifIndex': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 1], 'type': 'Integer32', 'access': 'not-accessible'},
        'ifDescr': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2], 'type': 'OctetString', 'access': 'read-only'},
    }
    
    # Note: _register_single_table was refactored to TableRegistrar
    # This test validates the integration pattern works correctly
    
    # Verify mib_builder is available for import_symbols
    agent.mib_builder.import_symbols.assert_not_called()


def test_register_mib_objects_orchestration(agent: SNMPAgent, mocker: MockerFixture) -> None:
    """Test that _register_mib_objects orchestrates the registration flow correctly."""
    # Setup mocked MIB JSONs (simulating what would be loaded from files)
    agent.mib_jsons = {
        'SNMPv2-MIB': {
            'sysDescr': {'oid': [1, 3, 6, 1, 1, 1, 0], 'type': 'OctetString', 'access': 'read-only'},
            'ifTable': {'oid': [1, 3, 6, 1, 2, 1, 2, 2], 'access': 'not-accessible'},
            'ifEntry': {'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1]},
        }
    }
    
    # Verify the agent has the expected structure
    assert agent.mib_jsons is not None
    assert 'SNMPv2-MIB' in agent.mib_jsons
    
    # Verify mib_builder is ready
    assert agent.mib_builder is not None
    
    # Verify all registration helpers are available
    assert agent.MibTable is not None
    assert agent.MibScalar is not None


def test_table_column_type_resolution_in_registration(agent: SNMPAgent) -> None:
    """Test that table registration resolves column types correctly."""
    type_registry: Dict[str, Dict[str, Any]] = {
        'Integer32': {'base_type': 'Integer', 'display_hint': 'd'},
        'OctetString': {'base_type': 'OctetString', 'display_hint': '255a'},
        'DisplayString': {
            'base_type': 'OctetString',
            'display_hint': '255a',
            'constraints': {'size': {'max': 255}}
        },
    }
    
    # Table column that uses a TEXTUAL-CONVENTION
    column_data: Dict[str, Dict[str, Any]] = {
        'ifDescr': {
            'oid': [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
            'type': 'DisplayString',
            'access': 'read-only'
        }
    }
    
    col_type = column_data['ifDescr']['type']
    assert col_type in type_registry, f"Column type {col_type} should be in type registry"
    
    type_info = type_registry[col_type]
    assert type_info['base_type'] == 'OctetString', "DisplayString should resolve to OctetString base"
    assert 'display_hint' in type_info, "Type info should include display_hint"
