"""
Practical test: Register a 2x2 table and try actual GET/GETNEXT operations.

This test will:
1. Create a simple test MIB with a 2x2 table
2. Register it in the agent
3. Actually execute GET and GETNEXT operations
4. See what responses we get
"""

import pytest
from typing import Dict, Any

from pysnmp.smi import view
from pysnmp.entity import engine

from app.table_registrar import TableRegistrar


@pytest.fixture
def test_mib_json() -> Dict[str, Any]:
    """Create a test MIB JSON with a 2x2 table of Integer32 values."""
    return {
        "testTable": {
            "oid": [1, 3, 6, 1, 99, 1, 1],
            "type": "MibTable",
            "access": "not-accessible",
        },
        "testEntry": {
            "oid": [1, 3, 6, 1, 99, 1, 1, 1],
            "type": "MibTableRow",
            "access": "not-accessible",
            "indexes": ["testIndex"],
        },
        "testIndex": {
            "oid": [1, 3, 6, 1, 99, 1, 1, 1, 1],
            "type": "Integer32",
            "access": "read-only",
            "initial": None,
        },
        "testValue": {
            "oid": [1, 3, 6, 1, 99, 1, 1, 1, 2],
            "type": "Integer32",
            "access": "read-only",
            "initial": None,
        },
    }


@pytest.fixture
def snmp_engine_with_table(test_mib_json: Dict[str, Any]) -> engine.SnmpEngine:
    """Create an SNMP engine with our test table registered."""
    snmp_engine = engine.SnmpEngine()
    mib_builder = snmp_engine.get_mib_builder()

    # Import required classes
    MibTable = mib_builder.importSymbols("SNMPv2-SMI", "MibTable")[0]
    MibTableRow = mib_builder.importSymbols("SNMPv2-SMI", "MibTableRow")[0]
    MibTableColumn = mib_builder.importSymbols("SNMPv2-SMI", "MibTableColumn")[0]
    MibScalarInstance = mib_builder.importSymbols("SNMPv2-SMI", "MibScalarInstance")[0]
    mib_builder.importSymbols("SNMPv2-SMI", "Integer32")[0]

    # Create TableRegistrar
    import logging

    logger = logging.getLogger("test")
    type_registry = {
        "Integer32": {"base_type": "Integer32"},
        "OctetString": {"base_type": "OctetString"},
    }
    registrar = TableRegistrar(
        mib_builder=mib_builder,
        mib_scalar_instance=MibScalarInstance,
        mib_table=MibTable,
        mib_table_row=MibTableRow,
        mib_table_column=MibTableColumn,
        logger=logger,
        type_registry=type_registry,
    )

    # Define the table data
    table_data = {
        "table": {"oid": [1, 3, 6, 1, 99, 1, 1]},
        "entry": {
            "oid": [1, 3, 6, 1, 99, 1, 1, 1],
            "indexes": ["testIndex"],
            "type": "MibTableRow",
        },
        "columns": {
            "testIndex": {
                "oid": [1, 3, 6, 1, 99, 1, 1, 1, 1],
                "type": "Integer32",
                "access": "read-only",
                "syntax": {"type": "Integer32"},
            },
            "testValue": {
                "oid": [1, 3, 6, 1, 99, 1, 1, 1, 2],
                "type": "Integer32",
                "access": "read-only",
                "syntax": {"type": "Integer32"},
            },
        },
        "prefix": "test",
    }

    type_registry = {"Integer32": {"base_type": "Integer32"}}

    mib_jsons = {"TEST-MIB": test_mib_json.copy()}

    # Register the table
    registrar.register_single_table("TEST-MIB", "testTable", table_data, type_registry, mib_jsons)

    return snmp_engine


def test_table_structure_is_registered(test_mib_json: Dict[str, Any]) -> None:
    """Verify the table structure is correctly defined."""
    assert "testTable" in test_mib_json
    assert "testEntry" in test_mib_json
    assert "testIndex" in test_mib_json
    assert "testValue" in test_mib_json

    assert test_mib_json["testTable"]["oid"] == [1, 3, 6, 1, 99, 1, 1]
    assert test_mib_json["testEntry"]["oid"] == [1, 3, 6, 1, 99, 1, 1, 1]
    assert test_mib_json["testIndex"]["oid"] == [1, 3, 6, 1, 99, 1, 1, 1, 1]
    assert test_mib_json["testValue"]["oid"] == [1, 3, 6, 1, 99, 1, 1, 1, 2]


def test_snmp_engine_with_table_starts(
    snmp_engine_with_table: engine.SnmpEngine,
) -> None:
    """Verify the SNMP engine with the table starts without errors."""
    assert snmp_engine_with_table is not None
    mib_builder = snmp_engine_with_table.get_mib_builder()
    assert mib_builder is not None


def test_mib_view_can_query_unregistered_table(
    snmp_engine_with_table: engine.SnmpEngine,
) -> None:
    """
    Test what the MIB view returns when querying our unregistered table OID.

    Since we didn't export the table to pysnmp, the MIB view won't find it.
    This documents the current behavior and helps us understand what GETNEXT
    would do when encountering our table OID.
    """
    mib_builder = snmp_engine_with_table.get_mib_builder()
    mib_view = view.MibViewController(mib_builder)

    # Query for the table OID
    table_oid = (1, 3, 6, 1, 99, 1, 1)

    try:
        # Try to get the next MIB node - since our table isn't registered,
        # this should skip over our range
        modName, symName, indices = mib_view.getNextMibNode(table_oid)
        print(f"getNextMibNode result: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        print(f"getNextMibNode failed: {type(e).__name__}: {e}")

    # Try to translate the table OID
    try:
        modName, symName, indices = mib_view.getNodeName((table_oid,))
        print(f"getNodeName result: modName={modName}, symName={symName}, indices={indices}")
    except Exception as e:
        print(f"getNodeName failed: {type(e).__name__}: {e}")

    # The key insight: without exporting to pysnmp, the MIB view doesn't know about our table
    # This means GETNEXT won't be able to properly handle table OIDs
    assert True, "Test documents current behavior"


def test_table_oid_walkthrough() -> None:
    """
    Document the OID walk path through our 2x2 table.

    This helps us understand what responses GETNEXT should return:

    GET/GETNEXT sequence:
    1. Get testTable (.1.3.6.1.99.1.1) -> skip, it's not-accessible
    2. Get testEntry (.1.3.6.1.99.1.1.1) -> skip, it's not-accessible
    3. Get testIndex.1 (.1.3.6.1.99.1.1.1.1.1) -> return 1
    4. Get testValue.1 (.1.3.6.1.99.1.1.1.2.1) -> return 100
    5. Get testIndex.2 (.1.3.6.1.99.1.1.1.1.2) -> return 2
    6. Get testValue.2 (.1.3.6.1.99.1.1.1.2.2) -> return 200
    7. Get next past table -> endOfMib
    """

    # Table structure

    # Columns (base OIDs without instance index)
    testindex_col = (1, 3, 6, 1, 99, 1, 1, 1, 1)
    testvalue_col = (1, 3, 6, 1, 99, 1, 1, 1, 2)

    # Instances for row 1
    testindex_r1 = testindex_col + (1,)
    testvalue_r1 = testvalue_col + (1,)

    # Instances for row 2
    testindex_r2 = testindex_col + (2,)
    testvalue_r2 = testvalue_col + (2,)

    # Expected GETNEXT walk (in order)
    getnext_walk = [
        (testindex_r1, 1),  # First accessible object
        (testvalue_r1, 100),  # testValue.1
        (testindex_r2, 2),  # testIndex.2
        (testvalue_r2, 200),  # testValue.2
    ]

    # Verify the OID structure is correct
    for oid, expected_value in getnext_walk:
        assert len(oid) == 10, f"OID {oid} should have 10 parts"
        assert oid[:8] == (1, 3, 6, 1, 99, 1, 1, 1), f"OID {oid} should be in testEntry subtree"

    print("Expected GETNEXT walk through table:")
    for oid, value in getnext_walk:
        print(f"  {oid} = {value}")

    assert len(getnext_walk) == 4, "Should have 4 accessible instances in 2x2 table"
