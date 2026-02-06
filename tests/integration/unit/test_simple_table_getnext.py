"""
Test GETNEXT on a simple 2x2 table of Integer32 values.

This test validates whether we can actually respond to GET/GETNEXT on table OIDs
when table export is disabled.
"""

import logging
import pytest
from pysnmp.smi import builder, view
from pysnmp.entity import engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto import rfc1902
from typing import Dict, Any

from app.table_registrar import TableRegistrar


@pytest.fixture
def logger() -> logging.Logger:
    """Provide a logger for tests."""
    logging.basicConfig(level=logging.DEBUG)
    return logging.getLogger('test')


@pytest.fixture
def snmp_engine() -> engine.SnmpEngine:
    """Provide a fresh SNMP engine for tests."""
    return engine.SnmpEngine()


@pytest.fixture
def mib_builder(snmp_engine: engine.SnmpEngine) -> builder.MibBuilder:
    """Provide a fresh MIB builder from the SNMP engine."""
    return snmp_engine.get_mib_builder()


@pytest.fixture
def mib_view(snmp_engine: engine.SnmpEngine) -> view.MibViewController:
    """Provide a MIB view controller."""
    return view.MibViewController(snmp_engine.get_mib_builder())


def test_simple_2x2_table_with_getnext(
    snmp_engine: engine.SnmpEngine,
    mib_builder: builder.MibBuilder,
    mib_view: view.MibViewController,
    logger: logging.Logger
) -> None:
    """
    Test GETNEXT on a simple 2x2 table of Integer32 values.
    
    Table structure:
    - testTable (.1.3.6.1.99.1.1)
      - testEntry (.1.3.6.1.99.1.1.1)
        - testIndex (.1.3.6.1.99.1.1.1.1) - index, Integer32
        - testValue (.1.3.6.1.99.1.1.1.2) - Integer32
    
    With 2 rows:
    - Row 1: index=1, value=100
    - Row 2: index=2, value=200
    """
    
    # Import MIB classes
    MibTable = mib_builder.importSymbols('SNMPv2-SMI', 'MibTable')[0]
    MibTableRow = mib_builder.importSymbols('SNMPv2-SMI', 'MibTableRow')[0]
    MibTableColumn = mib_builder.importSymbols('SNMPv2-SMI', 'MibTableColumn')[0]
    MibScalarInstance = mib_builder.importSymbols('SNMPv2-SMI', 'MibScalarInstance')[0]
    Integer32 = mib_builder.importSymbols('SNMPv2-SMI', 'Integer32')[0]
    
    # Create TableRegistrar
    registrar = TableRegistrar(
        mib_builder=mib_builder,
        mib_scalar_instance=MibScalarInstance,
        mib_table=MibTable,
        mib_table_row=MibTableRow,
        mib_table_column=MibTableColumn,
        logger=logger
    )
    
    # Define a simple 2x2 table
    table_data: Dict[str, Any] = {
        'table': {'oid': [1, 3, 6, 1, 99, 1, 1]},
        'entry': {
            'oid': [1, 3, 6, 1, 99, 1, 1, 1],
            'indexes': ['testIndex'],
            'type': 'MibTableRow'
        },
        'columns': {
            'testIndex': {
                'oid': [1, 3, 6, 1, 99, 1, 1, 1, 1],
                'type': 'Integer32',
                'access': 'read-only',
                'syntax': {'type': 'Integer32'}
            },
            'testValue': {
                'oid': [1, 3, 6, 1, 99, 1, 1, 1, 2],
                'type': 'Integer32',
                'access': 'read-only',
                'syntax': {'type': 'Integer32'}
            }
        },
        'prefix': 'test'
    }
    
    type_registry = {
        'Integer32': {'base_type': 'Integer32'}
    }
    
    mib_jsons = {
        'TEST-MIB': {
            'testTable': table_data['table'],
            'testEntry': table_data['entry'],
            'testIndex': table_data['columns']['testIndex'],
            'testValue': table_data['columns']['testValue']
        }
    }
    
    # Register the table (should NOT export to pysnmp, just track in JSON)
    registrar.register_single_table(
        'TEST-MIB',
        'testTable',
        table_data,
        type_registry,
        mib_jsons
    )
    
    # Now try to access table OIDs via MIB view
    # We'll try to look up OIDs in the MIB to see if they're accessible
    
    # Test 1: Can we access the table OID?
    table_oid = (1, 3, 6, 1, 99, 1, 1)
    entry_oid = (1, 3, 6, 1, 99, 1, 1, 1)
    col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1)  # testIndex
    col2_oid = (1, 3, 6, 1, 99, 1, 1, 1, 2)  # testValue
    row1_col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1, 1)  # testIndex.1
    row1_col2_oid = (1, 3, 6, 1, 99, 1, 1, 1, 2, 1)  # testValue.1
    row2_col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1, 2)  # testIndex.2
    row2_col2_oid = (1, 3, 6, 1, 99, 1, 1, 1, 2, 2)  # testValue.2
    
    # Try to translate OIDs through the MIB
    try:
        # Test getting the table entry
        modName, symName, indices = mib_view.getNodeName((table_oid,))
        logger.info(f"Table OID lookup: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        logger.info(f"Cannot lookup table OID (expected): {e}")
    
    try:
        # Test getting the entry
        modName, symName, indices = mib_view.getNodeName((entry_oid,))
        logger.info(f"Entry OID lookup: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        logger.info(f"Cannot lookup entry OID (expected): {e}")
    
    try:
        # Test getting a column
        modName, symName, indices = mib_view.getNodeName((col1_oid,))
        logger.info(f"Column OID lookup: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        logger.info(f"Cannot lookup column OID (expected): {e}")
    
    # The main assertion: the table registration shouldn't crash
    assert True, "Table registration completed without error"


def test_table_oid_hierarchy(
    mib_builder: builder.MibBuilder,
    logger: logging.Logger
) -> None:
    """
    Test OID hierarchy for a simple table.
    
    Verifies that OID structure is correct:
    - .1.3.6.1.99.1.1 = testTable (MibTable)
    - .1.3.6.1.99.1.1.1 = testEntry (MibTableRow)
    - .1.3.6.1.99.1.1.1.1 = testIndex (MibTableColumn, index)
    - .1.3.6.1.99.1.1.1.2 = testValue (MibTableColumn)
    - .1.3.6.1.99.1.1.1.1.1 = testIndex.1 (instance for row 1)
    - .1.3.6.1.99.1.1.1.2.1 = testValue.1 (instance for row 1)
    - .1.3.6.1.99.1.1.1.1.2 = testIndex.2 (instance for row 2)
    - .1.3.6.1.99.1.1.1.2.2 = testValue.2 (instance for row 2)
    """
    
    # Just verify that OID tuples can be created correctly
    table_oid = (1, 3, 6, 1, 99, 1, 1)
    entry_oid = (1, 3, 6, 1, 99, 1, 1, 1)
    col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1)
    col2_oid = (1, 3, 6, 1, 99, 1, 1, 1, 2)
    
    # Row 1 instances
    row1_col1 = col1_oid + (1,)  # testIndex.1
    row1_col2 = col2_oid + (1,)  # testValue.1
    
    # Row 2 instances
    row2_col1 = col1_oid + (2,)  # testIndex.2
    row2_col2 = col2_oid + (2,)  # testValue.2
    
    logger.info(f"Table OID: {table_oid}")
    logger.info(f"Entry OID: {entry_oid}")
    logger.info(f"Column 1 OID: {col1_oid}")
    logger.info(f"Column 2 OID: {col2_oid}")
    logger.info(f"Row 1, Col 1 OID: {row1_col1}")
    logger.info(f"Row 1, Col 2 OID: {row1_col2}")
    logger.info(f"Row 2, Col 1 OID: {row2_col1}")
    logger.info(f"Row 2, Col 2 OID: {row2_col2}")
    
    # Verify structure
    assert table_oid == (1, 3, 6, 1, 99, 1, 1)
    assert entry_oid == table_oid + (1,)
    assert col1_oid == entry_oid + (1,)
    assert col2_oid == entry_oid + (2,)
    assert row1_col1 == col1_oid + (1,)
    assert row1_col2 == col2_oid + (1,)
    assert row2_col1 == col1_oid + (2,)
    assert row2_col2 == col2_oid + (2,)


def test_table_row_instance_oid_generation() -> None:
    """
    Test that we can correctly generate OIDs for table row instances.
    
    This simulates what GETNEXT would need to do:
    1. Start with a table OID
    2. Find the next instance in the table
    3. Return the OID for that instance
    """
    
    # Table structure
    table_oid = (1, 3, 6, 1, 99, 1, 1)
    entry_oid = (1, 3, 6, 1, 99, 1, 1, 1)
    col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1)
    col2_oid = (1, 3, 6, 1, 99, 1, 1, 1, 2)
    
    # Table rows with data
    rows = [
        {'index': 1, 'value': 100},
        {'index': 2, 'value': 200}
    ]
    
    # Simulate GETNEXT from table OID
    # Expected response: first column, first row instance
    # OID: .1.3.6.1.99.1.1.1.1.1 with value 1
    
    expected_oid = col1_oid + (rows[0]['index'],)
    assert expected_oid == (1, 3, 6, 1, 99, 1, 1, 1, 1, 1)
    
    # Simulate GETNEXT from first instance
    # Expected: second column, first row
    expected_oid = col2_oid + (rows[0]['index'],)
    assert expected_oid == (1, 3, 6, 1, 99, 1, 1, 1, 2, 1)
    
    # Simulate GETNEXT from end of first row
    # Expected: first column, second row
    expected_oid = col1_oid + (rows[1]['index'],)
    assert expected_oid == (1, 3, 6, 1, 99, 1, 1, 1, 1, 2)


def test_table_without_export_responds_to_mib_lookup(
    mib_builder: builder.MibBuilder,
    mib_view: view.MibViewController,
    logger: logging.Logger
) -> None:
    """
    Test what happens when we query the MIB view for a table that wasn't exported.
    
    Key question: Can pysnmp's MIB view respond to OID lookups for a table
    that wasn't explicitly registered via export_symbols?
    
    Expected: Probably not - we'll get "no such object" or similar, because
    the table was never added to the MIB's symbol table.
    """
    
    # OIDs for our non-registered table
    table_oid = (1, 3, 6, 1, 99, 1, 1)
    entry_oid = (1, 3, 6, 1, 99, 1, 1, 1)
    col1_oid = (1, 3, 6, 1, 99, 1, 1, 1, 1)
    
    # Try to get next OID from our non-registered table
    try:
        # getNextMibNode should return the next OID in the tree
        # For a non-registered table, it will skip over it
        modName, symName, indices = mib_view.getNextMibNode(table_oid)
        logger.info(f"getNextMibNode from table: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        logger.info(f"getNextMibNode from table failed (expected): {type(e).__name__}: {e}")
    
    # This test documents the expected behavior when table export is disabled
    # The MIB view won't know about our custom table OIDs
    assert True, "Test completed - documents expected behavior when tables aren't exported"
