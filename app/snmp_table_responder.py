"""
Custom SNMP table responder for dynamic table queries.

This module implements a responder that handles SNMP requests to table OIDs
by returning data from the behavior JSON files, enabling full SNMP queryability
(GET, GETNEXT, WALK) without relying on pysnmp's native table handling.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from pysnmp.proto import rfc1902, api
from pysnmp.smi import builder, view
from pysnmp.proto.api import v2c

logger = logging.getLogger(__name__)


class SNMPTableResponder:
    """
    Handles SNMP requests for table data from JSON behavior files.
    
    Implements SNMP variable binding responses for GET and GETNEXT operations
    on table OIDs by traversing JSON table structures and returning appropriate values.
    """

    def __init__(self, behavior_jsons: Dict[str, Dict[str, Any]], mib_builder: builder.MibBuilder):
        """
        Initialize the table responder.
        
        Args:
            behavior_jsons: Dict of MIB name -> behavior JSON structure
            mib_builder: pysnmp MibBuilder instance for type resolution
        """
        self.behavior_jsons = behavior_jsons
        self.mib_builder = mib_builder
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Build a map of table OIDs to table info for fast lookup
        self.table_oid_map: Dict[Tuple[int, ...], Tuple[str, str, Dict[str, Any]]] = {}
        self._build_table_oid_map()

    def _build_table_oid_map(self) -> None:
        """Build mapping of table OIDs to (mib_name, table_name, table_data)."""
        for mib_name, mib_json in self.behavior_jsons.items():
            for obj_name, obj_data in mib_json.items():
                if isinstance(obj_data, dict) and obj_data.get('type') == 'MibTable':
                    table_oid = tuple(obj_data['oid'])
                    self.table_oid_map[table_oid] = (mib_name, obj_name, obj_data)
                    self.logger.debug(f"Registered table responder for {mib_name}.{obj_name} OID={table_oid}")

    def is_table_oid(self, oid: Tuple[int, ...]) -> bool:
        """Check if an OID is a table or within a table."""
        # Check if it's a direct table OID
        if oid in self.table_oid_map:
            return True
        
        # Check if it's within a table (row or column)
        for table_oid in self.table_oid_map.keys():
            if len(oid) > len(table_oid) and oid[:len(table_oid)] == table_oid:
                return True
        
        return False

    def get_table_info(self, oid: Tuple[int, ...]) -> Optional[Tuple[str, str, Dict[str, Any], Tuple[int, ...]]]:
        """
        Get table info for an OID.
        
        Returns: (mib_name, table_name, table_data, table_oid) or None
        """
        # Direct table OID
        if oid in self.table_oid_map:
            mib_name, table_name, table_data = self.table_oid_map[oid]
            return (mib_name, table_name, table_data, oid)
        
        # Within a table
        for table_oid, (mib_name, table_name, table_data) in self.table_oid_map.items():
            if len(oid) > len(table_oid) and oid[:len(table_oid)] == table_oid:
                return (mib_name, table_name, table_data, table_oid)
        
        return None

    def get_next_oid(self, requested_oid: Tuple[int, ...]) -> Optional[Tuple[Tuple[int, ...], Any]]:
        """
        Find the next OID after the requested one in lexicographic order.
        
        This supports SNMP GETNEXT operations.
        
        Returns: (next_oid, value) or None if not found
        """
        # Get all available OIDs from tables (sorted)
        available_oids = self._get_all_table_oids()
        
        # Find the next OID after the requested one
        for oid in available_oids:
            if oid > requested_oid:
                value = self._get_oid_value(oid)
                if value is not None:
                    return (oid, value)
        
        return None

    def _get_all_table_oids(self) -> List[Tuple[int, ...]]:
        """Get all OIDs in tables, sorted lexicographically."""
        oids = []
        
        for mib_name, mib_json in self.behavior_jsons.items():
            for obj_name, obj_data in mib_json.items():
                if isinstance(obj_data, dict) and obj_data.get('type') == 'MibTable':
                    # Get the entry (row) definition
                    entry_name = obj_name + 'Entry'
                    if entry_name in mib_json:
                        entry_data = mib_json[entry_name]
                        if entry_data.get('type') == 'MibTableRow':
                            # Get all rows in the table
                            rows = obj_data.get('initial', {})
                            if isinstance(rows, dict):
                                for row_index, row_data in rows.items():
                                    # Get all columns in this row
                                    if isinstance(row_data, dict):
                                        for col_name, col_value in row_data.items():
                                            # Look up column OID
                                            col_obj_name = col_name
                                            if col_obj_name in mib_json:
                                                col_oid_list = mib_json[col_obj_name].get('oid', [])
                                                if col_oid_list:
                                                    # Add row index to column OID
                                                    full_oid = tuple(col_oid_list + [int(row_index)])
                                                    oids.append(full_oid)
        
        return sorted(oids)

    def _get_oid_value(self, oid: Tuple[int, ...]) -> Optional[Any]:
        """Get the value for a specific OID."""
        table_info = self.get_table_info(oid)
        if not table_info:
            return None
        
        mib_name, table_name, table_data, table_oid = table_info
        
        # Parse the OID to get table, column, and row index
        # Format: table_oid + [column_id] + [row_indices...]
        # We need to find which column and row this refers to
        
        mib_json = self.behavior_jsons[mib_name]
        entry_name = table_name + 'Entry'
        
        if entry_name not in mib_json:
            return None
        
        entry_data = mib_json[entry_name]
        columns = entry_data.get('columns', {})
        
        # Find the column by OID
        col_prefix_len = len(table_oid) + 2  # table + entry + column_id
        if len(oid) < col_prefix_len:
            return None
        
        col_id = oid[len(table_oid) + 1]
        row_index = str(oid[-1]) if len(oid) > col_prefix_len else '1'
        
        # Find which column has this OID
        for col_name, col_info in columns.items():
            if col_info.get('oid', [])[-1] == col_id:
                # Found the column, get the value from table data
                rows = table_data.get('initial', {})
                if row_index in rows and col_name in rows[row_index]:
                    return rows[row_index][col_name]
                break
        
        return None

    def handle_get_request(self, oid: Tuple[int, ...]) -> Optional[Any]:
        """Handle SNMP GET request for an OID."""
        return self._get_oid_value(oid)

    def handle_getnext_request(self, oid: Tuple[int, ...]) -> Optional[Tuple[Tuple[int, ...], Any]]:
        """Handle SNMP GETNEXT request for an OID."""
        return self.get_next_oid(oid)
