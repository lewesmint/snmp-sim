"""Custom SNMP table responder for dynamic table queries.

This module implements a responder that handles SNMP requests to table OIDs
by returning data from the behavior JSON files, enabling full SNMP queryability
(GET, GETNEXT, WALK) without relying on pysnmp's native table handling.
"""

# pylint: disable=logging-fstring-interpolation,unused-variable

import logging
from typing import Any, cast

from pysnmp.smi import builder

logger = logging.getLogger(__name__)


class SNMPTableResponder:
    """Handles SNMP requests for table data from JSON behavior files.

    Implements SNMP variable binding responses for GET and GETNEXT operations
    on table OIDs by traversing JSON table structures and returning appropriate values.
    """

    def __init__(
        self,
        behavior_jsons: dict[str, dict[str, Any]],
        mib_builder: builder.MibBuilder | None,
    ) -> None:
        """Initialize the table responder.

        Args:
            behavior_jsons: Dict of MIB name -> behavior JSON structure
            mib_builder: Optional pysnmp MibBuilder instance for type resolution (can be None)

        """
        self.behavior_jsons = behavior_jsons
        self.mib_builder = mib_builder
        self.logger = logging.getLogger(__name__)

        # Build a map of table OIDs to table info for fast lookup
        self.table_oid_map: dict[tuple[int, ...], tuple[str, str, dict[str, Any]]] = {}
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
                        "Registered table responder for %s.%s OID=%s", mib_name, obj_name, table_oid
                    )

    def _find_entry_for_table(
        self,
        objects: dict[str, Any],
        table_oid: tuple[int, ...],
        table_name: str,
    ) -> dict[str, Any] | None:
        """Find table entry metadata for a table OID.

        Supports canonical tableEntry naming and OID-prefix matching.
        """
        entry_name = f"{table_name}Entry"
        candidate = objects.get(entry_name)
        if isinstance(candidate, dict) and candidate.get("type") == "MibTableRow":
            return candidate

        matches: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        for other_data in objects.values():
            if not isinstance(other_data, dict):
                continue
            if other_data.get("type") != "MibTableRow":
                continue
            oid_list = other_data.get("oid", [])
            if not isinstance(oid_list, list):
                continue
            oid_tuple = tuple(oid_list)
            if len(oid_tuple) > len(table_oid) and oid_tuple[: len(table_oid)] == table_oid:
                matches.append((oid_tuple, other_data))

        if not matches:
            return None

        matches.sort(key=lambda item: (len(item[0]), item[0]))
        return matches[0][1]

    def is_table_oid(self, oid: tuple[int, ...]) -> bool:
        """Check if an OID is a table or within a table."""
        # Check if it's a direct table OID
        if oid in self.table_oid_map:
            return True

        # Check if it's within a table (row or column)
        return any(
            len(oid) > len(table_oid) and oid[: len(table_oid)] == table_oid
            for table_oid in self.table_oid_map
        )

    def get_table_info(
        self, oid: tuple[int, ...]
    ) -> tuple[str, str, dict[str, Any], tuple[int, ...]] | None:
        """Get table info for an OID.

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

    def get_next_oid(self, requested_oid: tuple[int, ...]) -> tuple[tuple[int, ...], object] | None:
        """Find the next OID after the requested one in lexicographic order.

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

    def _get_all_table_oids(self) -> list[tuple[int, ...]]:
        """Get all OIDs in tables, sorted lexicographically."""
        oids = []

        for mib_json in self.behavior_jsons.values():
            objects = mib_json.get("objects", mib_json) if isinstance(mib_json, dict) else {}
            if not isinstance(objects, dict):
                continue
            for obj_name, obj_data in objects.items():
                if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                    table_oid = tuple(obj_data.get("oid", []))
                    if not table_oid:
                        continue
                    entry_data = self._find_entry_for_table(objects, table_oid, obj_name)
                    if entry_data:
                        # Get all rows in the table
                        rows = obj_data.get("rows", [])
                        if not isinstance(rows, list):
                            continue
                        default_row = self._default_row(rows)

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
                                    idx_val = self._index_value_with_default(row, idx, default_row)
                                    if idx_val is None:
                                        continue
                                    if isinstance(idx_val, (list, tuple)):
                                        instance_parts.extend(str(v) for v in idx_val)
                                    else:
                                        instance_parts.extend(
                                            str(v) for v in str(idx_val).split(".")
                                        )
                                if not instance_parts:
                                    instance_parts = ["1"]
                            if len(columns) == 1:
                                col_oid_list = next(iter(columns.values()))
                                try:
                                    full_oid = tuple(
                                        col_oid_list + [int(p) for p in instance_parts]
                                    )
                                except ValueError:
                                    continue
                                oids.append(full_oid)
                                continue

                            for col_name, col_oid_list in columns.items():
                                if self._row_value_with_default(row, col_name, default_row) is None:
                                    continue
                                try:
                                    full_oid = tuple(
                                        col_oid_list + [int(p) for p in instance_parts]
                                    )
                                except ValueError:
                                    continue
                                oids.append(full_oid)

        return sorted(oids)

    @staticmethod
    def _default_row(rows: list[Any]) -> dict[str, Any]:
        """Return the table default row (first dict row), if present."""
        if rows and isinstance(rows[0], dict):
            return rows[0]
        return {}

    @staticmethod
    def _row_value_with_default(
        row: dict[str, Any],
        col_name: str,
        default_row: dict[str, Any],
    ) -> object | None:
        """Resolve a row column value, falling back to table defaults."""
        if col_name in row:
            return cast("object", row[col_name])
        if col_name in default_row:
            return cast("object", default_row[col_name])
        return None

    @staticmethod
    def _index_value_with_default(
        row: dict[str, Any],
        index_name: str,
        default_row: dict[str, Any],
    ) -> object | None:
        """Resolve an index value from row data with default-row fallback."""
        if index_name in row:
            return cast("object", row[index_name])
        if index_name in default_row:
            return cast("object", default_row[index_name])
        return None

    @staticmethod
    def _collect_entry_columns(
        objects: dict[str, Any],
        entry_oid: tuple[int, ...],
    ) -> dict[str, dict[str, Any]]:
        columns: dict[str, dict[str, Any]] = {}
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
        return columns

    @staticmethod
    def _build_instance_str(instance_parts: tuple[int, ...]) -> str:
        return ".".join(str(x) for x in instance_parts) if instance_parts else "1"

    @staticmethod
    def _build_row_index_string(
        row: dict[str, Any],
        index_columns: list[str],
        default_row: dict[str, Any],
    ) -> str | None:
        if not index_columns:
            return "1"
        if len(index_columns) == 1:
            idx_name = index_columns[0]
            row_idx_val = row[idx_name] if idx_name in row else default_row.get(idx_name)
            return str(row_idx_val) if row_idx_val is not None else ""

        row_parts: list[str] = []
        for idx_col in index_columns:
            row_val = row[idx_col] if idx_col in row else default_row.get(idx_col)
            if row_val is None:
                return None
            if isinstance(row_val, (list, tuple)):
                row_parts.extend(str(v) for v in row_val)
            else:
                row_parts.extend(str(v) for v in str(row_val).split("."))
        return ".".join(row_parts)

    def _lookup_single_column_value(
        self,
        rows: list[Any],
        col_name: str,
        index_columns: list[str],
        instance_str: str,
        default_row: dict[str, Any],
    ) -> object | None:
        if not index_columns:
            if instance_str != "1":
                return None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = self._row_value_with_default(row, col_name, default_row)
                if value is not None:
                    return value
            return None

        for row in rows:
            if not isinstance(row, dict):
                continue
            row_idx_str = self._build_row_index_string(row, index_columns, default_row)
            if row_idx_str == instance_str:
                value = self._row_value_with_default(row, col_name, default_row)
                return value if value is not None else None
        return None

    def _lookup_multi_column_value(
        self,
        columns: dict[str, dict[str, Any]],
        rows: list[Any],
        index_columns: list[str],
        col_id: int,
        instance_str: str,
        default_row: dict[str, Any],
    ) -> object | None:
        for col_name, col_info in columns.items():
            if col_info.get("oid", [])[-1] != col_id:
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_idx_str = self._build_row_index_string(row, index_columns, default_row)
                if row_idx_str == instance_str:
                    value = self._row_value_with_default(row, col_name, default_row)
                    return value if value is not None else None
            return None
        return None

    def _get_oid_value(self, oid: tuple[int, ...]) -> object | None:
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

        entry_data = self._find_entry_for_table(objects, table_oid, table_name)

        if not entry_data:
            return None

        entry_oid = tuple(entry_data.get("oid", []))
        if not entry_oid:
            return None

        columns = self._collect_entry_columns(objects, entry_oid)
        rows = table_data.get("rows", [])
        if not isinstance(rows, list):
            return None
        default_row = self._default_row(rows)
        index_columns = entry_data.get("indexes", [])
        if not isinstance(index_columns, list):
            index_columns = []

        if len(columns) == 1:
            col_name, col_info = next(iter(columns.items()))
            col_oid = tuple(col_info.get("oid", []))
            if col_oid and len(oid) >= len(col_oid) + 1 and oid[: len(col_oid)] == col_oid:
                instance_parts = oid[len(col_oid) :]
            elif len(oid) >= len(entry_oid) + 1 and oid[: len(entry_oid)] == entry_oid:
                instance_parts = oid[len(entry_oid) :]
            else:
                return None
            instance_str = self._build_instance_str(instance_parts)
            return self._lookup_single_column_value(
                rows,
                col_name,
                index_columns,
                instance_str,
                default_row,
            )

        if len(oid) < len(entry_oid) + 1:
            return None
        if oid[: len(entry_oid)] != entry_oid:
            return None

        # Column id is immediately after entry OID
        col_id = oid[len(entry_oid)]
        # Instance parts follow the column id
        instance_parts = oid[len(entry_oid) + 1 :]
        instance_str = self._build_instance_str(instance_parts)

        return self._lookup_multi_column_value(
            columns=columns,
            rows=rows,
            index_columns=index_columns,
            col_id=col_id,
            instance_str=instance_str,
            default_row=default_row,
        )

    def handle_get_request(self, oid: tuple[int, ...]) -> object | None:
        """Handle SNMP GET request for an OID."""
        return self._get_oid_value(oid)

    def handle_getnext_request(self, oid: tuple[int, ...]) -> tuple[tuple[int, ...], object] | None:
        """Handle SNMP GETNEXT request for an OID."""
        return self.get_next_oid(oid)
