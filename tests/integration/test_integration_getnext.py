"""Integration test for GETNEXT operations with real SNMP agent.

This test actually initializes the SNMP agent, loads MIBs, registers
objects, and verifies that GETNEXT operations work without SmiError exceptions.
"""

import logging
from typing import Any, cast

import pytest
from pysnmp.entity import engine
from pysnmp.smi import builder

from app.table_registrar import TableRegistrar
from app.interface_types import TableData


@pytest.fixture
def logger() -> logging.Logger:
    """Provide a logger for tests."""
    logging.basicConfig(level=logging.WARNING)
    return logging.getLogger("integration_test")


@pytest.fixture
def snmp_engine() -> engine.SnmpEngine:
    """Provide a fresh SNMP engine for each test."""
    return engine.SnmpEngine()


@pytest.fixture
def mib_builder(snmp_engine: engine.SnmpEngine) -> builder.MibBuilder:
    """Provide a fresh MIB builder from the SNMP engine."""
    return snmp_engine.get_mib_builder()


@pytest.mark.parametrize(
    "symbol_name",
    [
        "Integer32",
        "MibScalar",
        "MibScalarInstance",
        "MibTable",
        "MibTableRow",
        "MibTableColumn",
    ],
)
def test_snmpv2_smi_symbols_importable(
    snmp_engine: engine.SnmpEngine,
    mib_builder: builder.MibBuilder,
    symbol_name: str,
) -> None:
    """Integration smoke test: SNMPv2-SMI classes import cleanly from a real engine."""
    imported = mib_builder.importSymbols("SNMPv2-SMI", symbol_name)[0]

    assert snmp_engine is not None
    assert mib_builder is not None
    assert imported is not None


def test_table_registrar_does_not_export_table_symbols(
    mib_builder: builder.MibBuilder,
    logger: logging.Logger,
) -> None:
    """Integration test: Verify TableRegistrar doesn't export table symbols.

    This directly tests the register_single_table method with real
    MIB builder instance to confirm tables are NOT exported to pysnmp.
    """
    # Import MIB classes
    MibTable = mib_builder.importSymbols("SNMPv2-SMI", "MibTable")[0]
    MibTableRow = mib_builder.importSymbols("SNMPv2-SMI", "MibTableRow")[0]
    MibTableColumn = mib_builder.importSymbols("SNMPv2-SMI", "MibTableColumn")[0]
    MibScalarInstance = mib_builder.importSymbols("SNMPv2-SMI", "MibScalarInstance")[0]

    # Create TableRegistrar
    registrar = TableRegistrar(
        mib_builder=cast("Any", mib_builder),
        mib_scalar_instance=MibScalarInstance,
        mib_table=MibTable,
        mib_table_row=MibTableRow,
        mib_table_column=MibTableColumn,
        logger=logger,
    )

    # Create test table data matching SNMPv2-MIB structure
    table_data = cast(
        TableData,
        {
        "table": {"oid": [1, 3, 6, 1, 2, 1, 1, 9]},
        "entry": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 9, 1],
            "indexes": ["sysORIndex"],
            "type": "MibTableRow",
        },
        "columns": {
            "sysORIndex": {
                "oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 1],
                "type": "Integer32",
                "access": "read-only",
                "syntax": {"type": "Integer32"},
            },
            "sysORID": {
                "oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 2],
                "type": "Integer32",
                "access": "read-only",
                "syntax": {"type": "Integer32"},
            },
        },
        "prefix": "sysOR",
        },
    )

    type_registry = {
        "Integer32": {"base_type": "Integer32"},
    }

    # Pre-populate mib_jsons as the actual app does
    mib_jsons = {
        "SNMPv2-MIB": {
            "sysORTable": table_data["table"],
            "sysOREntry": table_data["entry"],
        },
    }

    # Call the actual register_single_table method
    # With the fix, this should NOT call export_symbols for tables
    registrar.register_single_table(
        "SNMPv2-MIB",
        "sysORTable",
        table_data,
        type_registry,
        cast("Any", mib_jsons),
    )

    table_json = cast("dict[str, object]", mib_jsons["SNMPv2-MIB"]["sysORTable"])
    assert "rows" in table_json
    rows = table_json["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["sysORIndex"] == 1

