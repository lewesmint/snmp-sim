"""Table/schema state helper mixin for SNMPAgent."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class TableInstance(TypedDict, total=False):
    """Persisted table row data for one instance."""

    column_values: dict[str, JsonValue]
    index_values: dict[str, JsonValue]


class SNMPAgentTableStateMixin:
    """Mixin containing table-schema and table-instance helper methods."""

    table_instances: dict[str, dict[str, TableInstance]]

    def _format_index_value(self, value: JsonValue | None) -> str:
        raise NotImplementedError

    def _oid_tuple(self, value: JsonValue | None) -> tuple[int, ...] | None:
        raise NotImplementedError

    def _find_table_object_for_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid: str,
    ) -> tuple[dict[str, JsonValue] | None, list[int | str] | None]:
        for obj_data in objects.values():
            if obj_data.get("type") != "MibTable":
                continue

            table_oid_list = self._oid_list_parts(obj_data.get("oid"))
            if not table_oid_list:
                continue
            if ".".join(str(x) for x in table_oid_list) == table_oid:
                return obj_data, table_oid_list
        return None, None

    def _find_table_entry_object(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid_list: Sequence[int | str],
    ) -> dict[str, JsonValue] | None:
        entry_oid_list = [*table_oid_list, 1]
        for other_data in objects.values():
            if other_data.get("type") == "MibTableRow" and other_data.get("oid") == entry_oid_list:
                return other_data
        return None

    def _schema_rows_match_indexes(
        self,
        rows: list[JsonValue],
        index_columns: list[str],
        index_values: dict[str, JsonValue],
    ) -> bool:
        for row in rows:
            if not isinstance(row, dict):
                continue

            if all(
                self._format_index_value(row.get(col_name))
                == self._format_index_value(index_values.get(col_name))
                for col_name in index_columns
            ):
                return True
        return False

    def _extract_default_row_dict(self, table_obj: dict[str, JsonValue]) -> dict[str, JsonValue]:
        rows = table_obj.get("rows", [])
        if not isinstance(rows, list) or not rows:
            return {}
        return rows[0] if isinstance(rows[0], dict) else {}

    @staticmethod
    def _needs_default_fill(current_val: JsonValue | None) -> bool:
        return current_val is None or (
            isinstance(current_val, str) and current_val.strip().lower() == "unset"
        )

    def _apply_default_row_to_instances(
        self,
        table_oid: str,
        index_columns: list[str],
        default_row: dict[str, JsonValue],
    ) -> bool:
        updated = False
        for instance_data in self.table_instances.get(table_oid, {}).values():
            col_values = instance_data.get("column_values", {})
            for col_name, default_val in default_row.items():
                if col_name in index_columns:
                    continue
                if self._needs_default_fill(col_values.get(col_name)):
                    col_values[col_name] = default_val
                    updated = True
        return updated

    def _materialize_table_index_columns(
        self,
        table_oid: str,
        index_columns: list[str],
    ) -> bool:
        updated = False
        for instance_str, instance_data in self.table_instances.get(table_oid, {}).items():
            if self._materialize_instance_index_columns(instance_str, instance_data, index_columns):
                updated = True
        return updated

    @staticmethod
    def _index_value_from_part(part: str) -> JsonValue:
        return int(part) if part.isdigit() else part

    def _materialize_instance_index_columns(
        self,
        instance_str: str,
        instance_data: TableInstance,
        index_columns: list[str],
    ) -> bool:
        col_values = instance_data.get("column_values", {})
        parts = [part for part in instance_str.split(".") if part]
        if len(parts) != len(index_columns):
            return False

        updated = False
        for idx_col_name, idx_part in zip(index_columns, parts, strict=True):
            if idx_col_name in col_values:
                continue
            col_values[idx_col_name] = self._index_value_from_part(idx_part)
            updated = True
        return updated

    @staticmethod
    def _is_table_cell_oid_for_table(oid: tuple[int, ...], table_oid: tuple[int, ...]) -> bool:
        if len(oid) <= len(table_oid) + 2:
            return False
        if oid[: len(table_oid)] != table_oid:
            return False
        return oid[len(table_oid)] == 1

    def _find_entry_object_for_table(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
    ) -> dict[str, JsonValue] | None:
        for candidate in objects.values():
            if candidate.get("type") != "MibTableRow":
                continue
            if self._oid_tuple(candidate.get("oid")) == entry_oid:
                return candidate
        return None

    def _find_column_name_for_entry(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
        column_id: int,
    ) -> str | None:
        target_oid = (*entry_oid, column_id)
        for candidate_name, candidate in objects.items():
            col_oid = self._oid_tuple(candidate.get("oid"))
            if col_oid == target_oid:
                return candidate_name
        return None

    def _oid_list_parts(self, value: JsonValue | None) -> list[int | str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, (int, str))]
