"""State loading and schema reconciliation helpers for SNMPAgent."""

# ruff: noqa: D102,TC001

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from app.model_paths import mib_state_file
from app.snmp_agent_table_state_mixin import JsonValue, TableInstance
from app.value_links import get_link_manager

if TYPE_CHECKING:
    from logging import Logger


class SNMPAgentStateLoadingMixin:
    """Mixin containing unified state loading and schema reconciliation logic."""

    logger: Logger
    overrides: dict[str, JsonValue]
    table_instances: dict[str, dict[str, TableInstance]]
    deleted_instances: list[str]
    mib_jsons: dict[str, dict[str, JsonValue]]

    def _migrate_legacy_state_files(self) -> None:
        return None

    def save_mib_state(self) -> None:
        return None

    def _schema_objects(
        self,
        schema: dict[str, JsonValue],
    ) -> dict[str, dict[str, JsonValue]]:
        raw_objects = schema.get("objects")
        if not isinstance(raw_objects, dict):
            return {}
        return {
            str(name): obj
            for name, obj in raw_objects.items()
            if isinstance(obj, dict)
        }

    def _oid_list_parts(self, value: JsonValue | None) -> list[int | str]:
        if isinstance(value, (list, tuple)):
            return [part for part in value if isinstance(part, (int, str))]
        return []

    def _string_list(self, value: JsonValue | None) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if item is not None]
        return []

    def _find_table_object_for_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid: str,
    ) -> tuple[dict[str, JsonValue] | None, list[int | str] | None]:
        table_oid_list: list[int | str] = [
            int(part) if part.isdigit() else part
            for part in table_oid.split(".")
            if part
        ]
        for obj in objects.values():
            if obj.get("type") != "MibTable":
                continue
            obj_oid = self._oid_list_parts(obj.get("oid"))
            if obj_oid == table_oid_list:
                return obj, obj_oid
        return None, table_oid_list or None

    def _find_table_entry_object(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid_list: Sequence[int | str],
    ) -> dict[str, JsonValue] | None:
        wanted_prefix = list(table_oid_list)
        for obj in objects.values():
            if obj.get("type") != "MibTableRow":
                continue
            obj_oid = self._oid_list_parts(obj.get("oid"))
            if obj_oid[:-1] == wanted_prefix:
                return obj
        return None

    def _schema_rows_match_indexes(
        self,
        rows: list[JsonValue],
        index_columns: list[str],
        index_values: dict[str, JsonValue],
    ) -> bool:
        if not rows:
            return False
        row_keys = {
            str(k)
            for row in rows
            if isinstance(row, dict)
            for k in row
        }
        return all(col in row_keys or col in index_values for col in index_columns)

    def _normalize_loaded_table_instances(self) -> None:
        return None

    def _materialize_index_columns(self) -> None:
        return None

    def _fill_missing_table_defaults(self) -> None:
        return None

    def _state_file_path(self) -> str:
        """Return path to unified state file (scalars, tables, deletions)."""
        return str(mib_state_file(__file__))

    def _coerce_state_scalars(self, value: JsonValue | None) -> dict[str, JsonValue]:
        """Coerce persisted scalar overrides into dict[str, JsonValue]."""
        if not isinstance(value, dict):
            return {}
        return {str(key): val for key, val in value.items()}

    def _coerce_state_tables(self, value: JsonValue | None) -> dict[str, dict[str, TableInstance]]:
        """Coerce persisted table instance state into typed structure."""
        if not isinstance(value, dict):
            return {}

        tables: dict[str, dict[str, TableInstance]] = {}
        for table_oid, instances_raw in value.items():
            if not isinstance(table_oid, str) or not isinstance(instances_raw, dict):
                continue

            table_instances: dict[str, TableInstance] = {}
            for instance_key, instance_raw in instances_raw.items():
                if not isinstance(instance_key, str) or not isinstance(instance_raw, dict):
                    continue

                entry: TableInstance = {}
                column_values_raw = instance_raw.get("column_values")
                if isinstance(column_values_raw, dict):
                    entry["column_values"] = {
                        str(col_name): col_val
                        for col_name, col_val in column_values_raw.items()
                    }

                index_values_raw = instance_raw.get("index_values")
                if isinstance(index_values_raw, dict):
                    entry["index_values"] = {
                        str(index_name): index_val
                        for index_name, index_val in index_values_raw.items()
                    }

                table_instances[instance_key] = entry

            tables[table_oid] = table_instances

        return tables

    def _load_mib_state(self) -> None:
        """Load unified MIB state (scalars, tables, deletions) from disk."""
        path = Path(self._state_file_path())
        mib_state: dict[str, JsonValue] = {}

        if path.exists():
            try:
                with path.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    mib_state = {
                        str(key): cast("JsonValue", val)
                        for key, val in loaded.items()
                    }
                self.logger.info("Loaded MIB state from %s", path)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.exception("Failed to load MIB state from %s", path)
        else:
            try:
                self._migrate_legacy_state_files()
                if path.exists():
                    with path.open(encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        mib_state = {
                            str(key): cast("JsonValue", val)
                            for key, val in loaded.items()
                        }
                    self.logger.info("Migrated legacy state files to %s", path)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.warning("No legacy state files to migrate: %s", e)

        self.overrides = self._coerce_state_scalars(mib_state.get("scalars"))

        self.table_instances = self._coerce_state_tables(mib_state.get("tables"))
        self._normalize_loaded_table_instances()
        self._materialize_index_columns()
        self._fill_missing_table_defaults()

        deleted_instances_raw = mib_state.get("deleted_instances")
        if isinstance(deleted_instances_raw, list):
            self.deleted_instances = [oid for oid in deleted_instances_raw if isinstance(oid, str)]
        else:
            self.deleted_instances = []
        self._filter_deleted_instances_against_schema()

        try:
            link_manager = get_link_manager()
            links_raw = mib_state.get("links")
            links: list[dict[str, object]] = []
            if isinstance(links_raw, list):
                links = [
                    cast("dict[str, object]", link)
                    for link in links_raw
                    if isinstance(link, dict)
                ]
            link_manager.load_links_from_state(links)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Failed to load link state")

        self.logger.info(
            "%s", f"Loaded state: {len(self.overrides)} scalars, "
            f"{sum(len(v) for v in self.table_instances.values())} table instances, "
            f"{len(self.deleted_instances)} deleted instances"
        )

    def _filter_deleted_instances_against_schema(self) -> None:
        """Drop deleted instances that are not present in schema files."""
        if not self.deleted_instances:
            return

        schema_instance_oids, saw_table = self._collect_schema_instance_oids()
        if not saw_table:
            return

        before = len(self.deleted_instances)
        self.deleted_instances = [
            oid for oid in self.deleted_instances if oid in schema_instance_oids
        ]
        if len(self.deleted_instances) != before:
            self.save_mib_state()
            self.logger.info(
                "Filtered deleted instances against schema: %s -> %s",
                before,
                len(self.deleted_instances),
            )

    def _collect_schema_instance_oids(self) -> tuple[set[str], bool]:
        """Collect all instance OIDs that are defined in schema table rows."""
        instance_oids: set[str] = set()
        if not self.mib_jsons:
            return instance_oids, False

        saw_table = False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)
            for obj_data in objects.values():
                if obj_data.get("type") != "MibTable":
                    continue
                saw_table = True
                self._collect_table_instance_oids(
                    objects=objects,
                    table_obj=obj_data,
                    out=instance_oids,
                )

        return instance_oids, saw_table

    def _collect_table_instance_oids(
        self,
        *,
        objects: dict[str, dict[str, JsonValue]],
        table_obj: dict[str, JsonValue],
        out: set[str],
    ) -> None:
        table_oid_list = self._oid_list_parts(table_obj.get("oid"))
        if not table_oid_list:
            return

        table_oid = ".".join(str(x) for x in table_oid_list)
        entry_obj = self._find_table_entry_object(objects, table_oid_list)
        if not entry_obj:
            return

        index_columns = self._string_list(entry_obj.get("indexes"))
        columns_meta = self._build_index_columns_meta(objects, index_columns)
        rows = table_obj.get("rows", [])
        if not isinstance(rows, list):
            return

        for row in rows:
            if not isinstance(row, dict):
                continue
            instance_str = self._build_instance_str_from_row(row, index_columns, columns_meta)
            if instance_str:
                out.add(f"{table_oid}.{instance_str}")

    def _build_index_columns_meta(
        self,
        objects: dict[str, dict[str, JsonValue]],
        index_columns: list[str],
    ) -> dict[str, dict[str, JsonValue]]:
        columns_meta: dict[str, dict[str, JsonValue]] = {}
        for col_name in index_columns:
            col_obj = objects.get(col_name)
            if col_obj is not None:
                columns_meta[col_name] = col_obj
        return columns_meta

    def _build_instance_str_from_row(
        self,
        row: dict[str, JsonValue],
        index_columns: list[str],
        columns_meta: dict[str, dict[str, JsonValue]],
    ) -> str:
        """Build a dotted instance string from a schema table row."""
        if not index_columns:
            return "1"
        parts: list[str] = []
        for col_name in index_columns:
            raw_val = row.get(col_name)
            col_type = str(columns_meta.get(col_name, {}).get("type", "")).lower()
            if col_type == "ipaddress":
                if isinstance(raw_val, (list, tuple)):
                    parts.extend(str(v) for v in raw_val)
                else:
                    raw_str = str(raw_val) if raw_val is not None else ""
                    if raw_str:
                        parts.extend(p for p in raw_str.split(".") if p)
                    else:
                        parts.append("")
            else:
                parts.append(str(raw_val) if raw_val is not None else "")
        return ".".join(p for p in parts if p != "")

    def _instance_defined_in_schema(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
    ) -> bool:
        """Return True if a table instance exists in schema rows."""
        if not self.mib_jsons:
            return False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            table_obj, table_oid_list = self._find_table_object_for_oid(objects, table_oid)
            if table_obj is None or table_oid_list is None:
                continue

            entry_obj = self._find_table_entry_object(objects, table_oid_list)
            if not entry_obj:
                return False

            index_columns = self._string_list(entry_obj.get("indexes"))
            rows = table_obj.get("rows", [])
            if not isinstance(rows, list):
                return False

            if not index_columns:
                return any(isinstance(row, dict) for row in rows)

            if self._schema_rows_match_indexes(rows, index_columns, index_values):
                return True

        return False
