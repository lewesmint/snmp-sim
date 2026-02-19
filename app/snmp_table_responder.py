"""
Custom SNMP table responder for dynamic table queries.

This module implements a responder that handles SNMP requests to table OIDs
by returning data from the behavior JSON files, enabling full SNMP queryability
(GET, GETNEXT, WALK) without relying on pysnmp's native table handling.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from pysnmp.smi import builder

logger = logging.getLogger(__name__)


class SNMPTableResponder:
    """
    Handles SNMP requests for table data from JSON behavior files.

    Implements SNMP variable binding responses for GET and GETNEXT operations
    on table OIDs by traversing JSON table structures and returning appropriate values.
    """

    def __init__(
        self, behavior_jsons: Dict[str, Dict[str, Any]], mib_builder: Optional[builder.MibBuilder]
    ) -> None:
        """
        Initialize the table responder.

        Args:
            behavior_jsons: Dict of MIB name -> behavior JSON structure
            mib_builder: Optional pysnmp MibBuilder instance for type resolution (can be None)
        """
        self.behavior_jsons = behavior_jsons
        self.mib_builder = mib_builder
        self.logger = logging.getLogger(__name__)

        # Build a map of table OIDs to table info for fast lookup
        self.table_oid_map: Dict[Tuple[int, ...], Tuple[str, str, Dict[str, Any]]] = {}
        self._build_table_oid_map()

    def _build_table_oid_map(self) -> None:
        """Build mapping of table OIDs to (mib_name, table_name, table_data)."""
        for mib_name, mib_json in self.behavior_jsons.items():
            objects = mib_json.get("objects", mib_json) if isinstance(mib_json, dict) else {}
            if not isinstance(objects, dict):
                continue
            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                    table_oid = tuple(obj_data["oid"])
                    self.table_oid_map[table_oid] = (mib_name, obj_name, obj_data)
                    self.logger.debug(
                        f"Registered table responder for {mib_name}.{obj_name} OID={table_oid}"
                    )

    def is_table_oid(self, oid: Tuple[int, ...]) -> bool:
        """Check if an OID is a table or within a table."""
        # Check if it's a direct table OID
        if oid in self.table_oid_map:
            return True

        # Check if it's within a table (row or column)
        for table_oid in self.table_oid_map.keys():
            if len(oid) > len(table_oid) and oid[: len(table_oid)] == table_oid:
                return True

        return False

    def get_table_info(
        self, oid: Tuple[int, ...]
    ) -> Optional[Tuple[str, str, Dict[str, Any], Tuple[int, ...]]]:
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
            if len(oid) > len(table_oid) and oid[: len(table_oid)] == table_oid:
                return (mib_name, table_name, table_data, table_oid)

        return None

    def get_next_oid(
        self, requested_oid: Tuple[int, ...]
    ) -> Optional[Tuple[Tuple[int, ...], Any]]:
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
            objects = mib_json.get("objects", mib_json) if isinstance(mib_json, dict) else {}
            if not isinstance(objects, dict):
                continue
            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                    # Find the entry (row) definition by OID structure
                    entry_data = None
                    expected_entry_oid = list(obj_data["oid"]) + [1]
                    for other_name, other_data in objects.items():
                        if isinstance(other_data, dict) and other_data.get("type") == "MibTableRow":
                            if list(other_data.get("oid", [])) == expected_entry_oid:
                                entry_data = other_data
                                break
                    if entry_data:
                        # Get all rows in the table
                        rows = obj_data.get("rows", [])
                        if not isinstance(rows, list):
                            continue

                        entry_oid = tuple(entry_data.get("oid", []))
                        index_columns = entry_data.get("indexes", [])
                        if not isinstance(index_columns, list):
                            index_columns = []

                        # Collect columns by OID prefix
                        columns: dict[str, list[int]] = {}
                        for col_name, col_info in objects.items():
                            if not isinstance(col_info, dict):
                                continue
                            col_oid = col_info.get("oid", [])
                            if (
                                isinstance(col_oid, list)
                                and len(col_oid) == len(entry_oid) + 1
                                and col_oid[: len(entry_oid)] == list(entry_oid)
                            ):
                                columns[col_name] = col_oid

                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            if not index_columns:
                                instance_parts = ["1"]
                            else:
                                instance_parts = []
                                for idx in index_columns:
                                    idx_val = row.get(idx)
                                    if idx_val is None:
                                        continue
                                    if isinstance(idx_val, (list, tuple)):
                                        instance_parts.extend(str(v) for v in idx_val)
                                    else:
                                        instance_parts.extend(str(v) for v in str(idx_val).split("."))
                                if not instance_parts:
                                    instance_parts = ["1"]
                            for col_name, col_oid_list in columns.items():
                                if col_name in row:
                                    try:
                                        full_oid = tuple(col_oid_list + [int(p) for p in instance_parts])
                                    except ValueError:
                                        continue
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
        objects = mib_json.get("objects", mib_json) if isinstance(mib_json, dict) else {}
        if not isinstance(objects, dict):
            return None
        
        # Find entry by OID structure
        entry_data = None
        expected_entry_oid = list(table_data["oid"]) + [1]
        for other_name, other_data in objects.items():
            if isinstance(other_data, dict) and other_data.get("type") == "MibTableRow":
                if list(other_data.get("oid", [])) == expected_entry_oid:
                    entry_data = other_data
                    break
        
        if not entry_data:
            return None
        # Find columns by OID prefix
        columns: dict[str, dict[str, Any]] = {}
        entry_oid = tuple(entry_data.get("oid", []))
        for col_name, col_info in objects.items():
            if not isinstance(col_info, dict):
                continue
            col_oid = col_info.get("oid", [])
            if (
                isinstance(col_oid, list)
                and len(col_oid) == len(entry_oid) + 1
                and col_oid[: len(entry_oid)] == list(entry_oid)
            ):
                columns[col_name] = col_info

        # Find the column by OID
        col_prefix_len = len(table_oid) + 2  # table + entry + column_id
        if len(oid) < col_prefix_len:
            return None

        # Column id is immediately after the table OID (table_oid + [column_id] + [row_indices])
        col_id = oid[len(table_oid)]
        # Instance parts follow the column id
        instance_parts = oid[col_prefix_len:]
        instance_str = ".".join(str(x) for x in instance_parts) if instance_parts else "1"

        # Find which column has this OID
        for col_name, col_info in columns.items():
            if col_info.get("oid", [])[-1] == col_id:
                # Found the column, get the value from table data
                rows = table_data.get("rows", [])
                if not isinstance(rows, list):
                    return None
                index_columns = entry_data.get("indexes", [])
                if not isinstance(index_columns, list):
                    index_columns = []

                if not index_columns:
                    if instance_str != "1":
                        return None
                    for row in rows:
                        if isinstance(row, dict) and col_name in row:
                            return row[col_name]
                elif len(index_columns) == 1:
                    idx_col = index_columns[0]
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        if col_name not in row:
                            continue
                        row_idx_val = row.get(idx_col)
                        row_idx_str = str(row_idx_val) if row_idx_val is not None else ""
                        if row_idx_str == instance_str:
                            return row[col_name]
                else:
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        if col_name not in row:
                            continue
                        row_parts: List[str] = []
                        for idx_col in index_columns:
                            row_val = row.get(idx_col)
                            if row_val is None:
                                row_parts = []
                                break
                            if isinstance(row_val, (list, tuple)):
                                row_parts.extend(str(v) for v in row_val)
                            else:
                                row_parts.extend(str(v) for v in str(row_val).split("."))
                        row_idx_str = ".".join(row_parts)
                        if row_idx_str == instance_str:
                            return row[col_name]
                break

        return None

    def handle_get_request(self, oid: Tuple[int, ...]) -> Optional[Any]:
        """Handle SNMP GET request for an OID."""
        return self._get_oid_value(oid)

    def handle_getnext_request(
        self, oid: Tuple[int, ...]
    ) -> Optional[Tuple[Tuple[int, ...], Any]]:
        """Handle SNMP GETNEXT request for an OID."""
        return self.get_next_oid(oid)
