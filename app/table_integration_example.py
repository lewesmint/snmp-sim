"""
Integration example: How to add table support to the snmpmore agent.

This module shows how to convert table data from behavior JSONs into
MibScalarInstance objects and export them properly.
"""

from typing import Dict, List, Tuple, Any, TYPE_CHECKING
from pysnmp.smi import builder

if TYPE_CHECKING:
    from pysnmp.entity.engine import SnmpEngine


def create_table_instances(
    mib_builder: builder.MibBuilder,
    table_name: str,
    table_data: Dict[str, Any]
) -> List[Tuple[str, Any]]:
    """
    Convert table data from behavior JSON to MibScalarInstance objects.
    
    Args:
        mib_builder: MIB builder instance from snmp engine
        table_name: Name of the table (e.g., "systemTable")
        table_data: Table metadata including base OID and rows
        
    Returns:
        List of (name, MibScalarInstance) tuples ready for export
    """
    # Import MIB classes
    (MibScalarInstance,) = mib_builder.import_symbols(
        'SNMPv2-SMI',
        'MibScalarInstance'
    )
    
    # Get base OID from table data
    base_oid_list = table_data.get('oid', [])
    if not base_oid_list:
        raise ValueError(f"Table {table_name} has no OID defined")
    
    # Assuming base_oid points to table entry (e.g., .1.3.6.1.2.1.1.1)
    base_oid = tuple(base_oid_list)
    
    instances = []
    rows = table_data.get('rows', [])
    
    for row_idx, row_data in enumerate(rows, start=1):
        # Get index value from row (usually first column)
        row_index = row_data.get('index', row_idx)
        
        # Iterate through columns
        for col_idx, (col_name, col_value) in enumerate(row_data.items(), start=1):
            if col_name == 'index':
                col_idx = 1  # Index is always column 1
            
            # Build full OID for this cell
            # table_entry_oid.column_id.row_index
            cell_oid = base_oid + (col_idx, row_index)
            
            # Convert value to appropriate pysnmp type
            syntax_value = convert_value_to_pysnmp_type(
                mib_builder,
                col_value,
                col_name
            )
            
            # Create scalar instance
            instance_name = f"{table_name}_row{row_index}_{col_name}"
            instance = MibScalarInstance(
                cell_oid,
                (row_index,),  # indices tuple
                syntax_value
            )
            
            instances.append((instance_name, instance))
    
    return instances


def convert_value_to_pysnmp_type(
    mib_builder: builder.MibBuilder,
    value: Any,
    column_name: str
) -> Any:
    """
    Convert Python value to pysnmp type.
    
    Args:
        mib_builder: MIB builder for importing types
        value: Python value to convert
        column_name: Column name (for type inference)
        
    Returns:
        pysnmp type instance
    """
    # Simple type inference based on value type
    if isinstance(value, int):
        (Integer32,) = mib_builder.import_symbols('SNMPv2-SMI', 'Integer32')
        return Integer32(value)
    elif isinstance(value, str):
        (DisplayString,) = mib_builder.import_symbols('SNMPv2-TC', 'DisplayString')
        return DisplayString(value)
    elif isinstance(value, bool):
        (Integer32,) = mibBuilder.import_symbols('SNMPv2-SMI', 'Integer32')
        return Integer32(1 if value else 0)
    else:
        # Default to string representation
        (DisplayString,) = mibBuilder.import_symbols('SNMPv2-TC', 'DisplayString')
        return DisplayString(str(value))


# Example behavior JSON for a table
EXAMPLE_TABLE_DATA = {
    "table_name": "systemTable",
    "description": "Example system information table",
    "oid": [1, 3, 6, 1, 2, 1, 1, 1],  # .iso.org.dod.internet.mgmt.mib-2.system.sysEntry
    "rows": [
        {
            "index": 1,
            "sysDescr": "System A",
            "sysObjectID": "1.3.6.1.4.1.9.9.1.1.1",
            "sysUpTime": 1234567,
            "sysContact": "admin@example.com",
            "sysName": "router-1",
            "sysLocation": "DC1",
            "sysServices": 72
        },
        {
            "index": 2,
            "sysDescr": "System B",
            "sysObjectID": "1.3.6.1.4.1.9.9.2.2.1",
            "sysUpTime": 9876543,
            "sysContact": "admin@example.org",
            "sysName": "switch-1",
            "sysLocation": "DC2",
            "sysServices": 58
        }
    ]
}


# Example integration in SNMPAgent
def setup_tables_in_agent(snmpEngine: "SnmpEngine", mib_jsons: Dict[str, Dict[str, Any]]) -> None:
    """
    Example: How to integrate table setup in the SNMPAgent class.
    
    This would go in SNMPAgent._register_mib_objects() or similar.
    """
    mibBuilder = snmpEngine.get_mib_builder()
    
    # Process each loaded MIB
    for mib_name, mib_json in mib_jsons.items():
        # Find tables in the MIB
        tables = {
            name: info 
            for name, info in mib_json.items()
            if isinstance(info, dict) and name.endswith('Table')
        }
        
        # Create instances for each table
        for table_name, table_info in tables.items():
            try:
                instances = create_table_instances(
                    mibBuilder,
                    table_name,
                    table_info
                )
                
                # Export instances
                mibBuilder.export_symbols(
                    mib_name,
                    *instances
                )
                
                print(f"Registered {len(instances)} instances for {table_name}")
                
            except Exception as e:
                print(f"Failed to register table {table_name}: {e}")


if __name__ == '__main__':
    # Example usage
    from pysnmp.entity import engine, config
    from pysnmp.entity.rfc3413 import cmdrsp, context
    from pysnmp.carrier.asyncio.dgram import udp
    
    # Setup SNMP engine
    snmpEngine = engine.SnmpEngine()
    config.add_v1_system(snmpEngine, 'public', 'public')
    config.add_transport(
        snmpEngine,
        udp.DOMAIN_NAME,
        udp.UdpTransport().open_server_mode(('127.0.0.1', 11161))
    )
    
    mibBuilder = snmpEngine.get_mib_builder()
    mibBuilder.load_modules('SNMPv2-SMI', 'SNMPv2-TC')
    
    # Create instances from example data
    instances = create_table_instances(
        mibBuilder,
        'systemTable',
        EXAMPLE_TABLE_DATA
    )
    
    print(f"Created {len(instances)} instances:")
    for name, inst in instances:
        print(f"  {name}")
