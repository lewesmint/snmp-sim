"""Augmented table propagation and OID helper mixin for SNMPAgent."""

# ruff: noqa: D101,D102,FBT002,PLR2004,RUF005

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from logging import Logger

JsonValue = Any


@dataclass
class AugmentedTableChild:
    table_oid: str
    entry_name: str
    indexes: tuple[str, ...]
    inherited_columns: tuple[str, ...]
    default_columns: dict[str, JsonValue]


class SNMPAgentAugmentsMixin:
    logger: Logger
    mib_jsons: dict[str, dict[str, JsonValue]]
    table_instances: Any
    _augmented_parents: Any
    _table_defaults: dict[str, dict[str, JsonValue]]

    def _schema_objects(
        self,
        schema: dict[str, JsonValue],
    ) -> dict[str, dict[str, JsonValue]]:
        return {
            str(name): obj
            for name, obj in schema.get("objects", {}).items()
            if isinstance(obj, dict)
        }

    def _oid_list_parts(self, value: JsonValue | None) -> list[int | str]:
        if isinstance(value, (list, tuple)):
            return [part for part in value if isinstance(part, (int, str))]
        return []

    def _oid_tuple(self, value: JsonValue | None) -> tuple[int, ...] | None:
        parts = self._oid_list_parts(value)
        if not parts:
            return None
        try:
            return tuple(int(part) for part in parts)
        except (TypeError, ValueError):
            return None

    def _string_list(self, value: JsonValue | None) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if item is not None]
        return []

    @staticmethod
    def _is_table_cell_oid_for_table(oid: tuple[int, ...], table_oid: tuple[int, ...]) -> bool:
        return len(oid) > len(table_oid) + 1 and oid[: len(table_oid)] == table_oid

    def _find_entry_object_for_table(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
    ) -> dict[str, JsonValue] | None:
        for obj in objects.values():
            if obj.get("type") != "MibTableRow":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid == entry_oid:
                return obj
        return None

    def _find_column_name_for_entry(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
        column_id: int,
    ) -> str | None:
        for name, obj in objects.items():
            if obj.get("type") != "MibTableColumn":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid is None or len(oid) < 1:
                continue
            if oid[:-1] == entry_oid and oid[-1] == column_id:
                return name
        return None

    def add_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        column_values: dict[str, JsonValue] | None = None,
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> str:
        del table_oid, index_values, column_values, propagate_augments, _augment_path
        return ""

    def delete_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> bool:
        del table_oid, index_values, propagate_augments, _augment_path
        return False

    def _normalize_oid_str(self, oid: str) -> str:
        """Normalize a dotted OID string (remove extra dots/spaces)."""
        cleaned = oid.strip().strip(".")
        if not cleaned:
            return ""
        parts = [part for part in cleaned.split(".") if part]
        return ".".join(parts)

    def _oid_list_to_str(self, oid_list: list[int | str]) -> str:
        """Convert a list-based OID to its dotted string representation."""
        if not oid_list:
            return ""
        return ".".join(str(part) for part in oid_list if part is not None)

    def _parse_index_from_entry(
        self,
        entry: dict[str, JsonValue] | list[JsonValue] | tuple[JsonValue, ...],
    ) -> tuple[str, str] | None:
        """Normalize different formats of index_from metadata."""
        if isinstance(entry, dict):
            mib = entry.get("mib")
            column = entry.get("column")
            if isinstance(mib, str) and isinstance(column, str):
                return mib, column
            return None
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            mib = entry[0]
            column = entry[-1]
            if isinstance(mib, str) and isinstance(column, str):
                return mib, column
        return None

    def _find_entry_name_by_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
    ) -> str | None:
        """Look up a table entry name by its OID."""
        for name, obj in objects.items():
            if obj.get("type") != "MibTableRow":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid is None:
                continue
            if oid == entry_oid:
                return name
        return None

    def _find_table_name_by_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid: tuple[int, ...],
    ) -> str | None:
        """Look up a table name by OID."""
        for name, obj in objects.items():
            if obj.get("type") != "MibTable":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid is None:
                continue
            if oid == table_oid:
                return name
        return None

    def _find_parent_table_for_column(
        self, module_name: str, column_name: str
    ) -> dict[str, str] | None:
        """Locate the parent table metadata for an inherited column reference."""
        module_schema = self.mib_jsons.get(module_name)
        if not module_schema:
            return None
        objects = self._schema_objects(module_schema)
        column_obj = objects.get(column_name)
        if not isinstance(column_obj, dict):
            return None
        column_oid = self._oid_tuple(column_obj.get("oid"))
        if column_oid is None or len(column_oid) < 2:
            return None

        entry_oid = column_oid[:-1]
        table_oid = entry_oid[:-1]
        table_name = self._find_table_name_by_oid(objects, table_oid)
        if not table_name:
            return None
        entry_name = self._find_entry_name_by_oid(objects, entry_oid)
        return {
            "table_oid": self._oid_list_to_str(list(table_oid)),
            "table_name": table_name,
            "entry_name": entry_name or "",
        }

    def _resolve_table_cell_context(
        self,
        oid: tuple[int, ...],
    ) -> tuple[str, str, str, list[str]] | None:
        """Resolve table metadata for a concrete table cell OID."""
        if not self.mib_jsons:
            return None

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)
            if not objects:
                continue

            for obj in objects.values():
                if obj.get("type") != "MibTable":
                    continue

                table_oid = self._oid_tuple(obj.get("oid"))
                if table_oid is None:
                    continue

                if not self._is_table_cell_oid_for_table(oid, table_oid):
                    continue

                entry_oid = table_oid + (1,)
                entry_obj = self._find_entry_object_for_table(objects, entry_oid)
                if not entry_obj:
                    continue

                column_id = oid[len(table_oid) + 1]
                column_name = self._find_column_name_for_entry(objects, entry_oid, column_id)
                if not column_name:
                    continue

                instance_parts = oid[len(table_oid) + 2 :]
                instance_str = ".".join(str(x) for x in instance_parts) if instance_parts else "1"
                index_columns = self._string_list(entry_obj.get("indexes"))
                return (
                    self._oid_list_to_str(list(table_oid)),
                    instance_str,
                    column_name,
                    index_columns,
                )

        return None

    def _build_augmented_index_map(self) -> None:
        """Build parent -> child mappings for tables that AUGMENT indexes."""
        self._augmented_parents.clear()
        seen_defaults: dict[str, dict[str, JsonValue]] = {}
        table_entries: dict[str, tuple[str, tuple[str, ...]]] = {}

        for module_schema in self.mib_jsons.values():
            objects = self._schema_objects(module_schema)
            self._collect_table_defaults_and_entries(
                objects=objects,
                seen_defaults=seen_defaults,
                table_entries=table_entries,
            )
            self._collect_augmented_children_from_index_from(
                objects=objects,
                seen_defaults=seen_defaults,
            )

        self._add_synthetic_augmented_children(
            seen_defaults=seen_defaults,
            table_entries=table_entries,
        )
        self._table_defaults = seen_defaults

    def _collect_table_defaults_and_entries(
        self,
        *,
        objects: dict[str, dict[str, JsonValue]],
        seen_defaults: dict[str, dict[str, JsonValue]],
        table_entries: dict[str, tuple[str, tuple[str, ...]]],
    ) -> None:
        for name, table_obj in objects.items():
            if table_obj.get("type") != "MibTable":
                continue

            table_oid_parts = self._oid_list_parts(table_obj.get("oid"))
            if not table_oid_parts:
                continue

            table_oid = self._oid_list_to_str(table_oid_parts)
            table_oid_tuple = tuple(table_oid_parts)

            rows = table_obj.get("rows", [])
            if isinstance(rows, list) and rows:
                first_row = rows[0]
                if isinstance(first_row, dict):
                    seen_defaults[table_oid] = dict(first_row)

            entry_name, entry_obj = self._resolve_table_entry_object(
                objects=objects,
                table_name=name,
                table_oid_tuple=table_oid_tuple,
            )
            if entry_obj is None:
                continue

            indexes = self._string_list(entry_obj.get("indexes"))
            if indexes:
                table_entries[table_oid] = (
                    entry_name,
                    tuple(idx for idx in indexes if isinstance(idx, str)),
                )

    def _resolve_table_entry_object(
        self,
        *,
        objects: dict[str, dict[str, JsonValue]],
        table_name: str,
        table_oid_tuple: tuple[int | str, ...],
    ) -> tuple[str, dict[str, JsonValue] | None]:
        entry_name = f"{table_name}Entry"
        entry_obj = objects.get(entry_name)
        if entry_obj is not None and entry_obj.get("type") == "MibTableRow":
            return entry_name, entry_obj

        candidates: list[tuple[str, dict[str, JsonValue]]] = []
        for cand_name, cand_obj in objects.items():
            if cand_obj.get("type") != "MibTableRow":
                continue
            cand_oid = cand_obj.get("oid", [])
            if not isinstance(cand_oid, list):
                continue
            cand_parts = self._oid_list_parts(cand_oid)
            if len(cand_parts) <= len(table_oid_tuple):
                continue
            if tuple(cand_parts[: len(table_oid_tuple)]) != table_oid_tuple:
                continue
            candidates.append((cand_name, cand_obj))

        if not candidates:
            return entry_name, None

        candidates.sort(key=lambda item: len(self._oid_list_parts(item[1].get("oid"))))
        return candidates[0]

    def _collect_augmented_children_from_index_from(
        self,
        *,
        objects: dict[str, dict[str, JsonValue]],
        seen_defaults: dict[str, dict[str, JsonValue]],
    ) -> None:
        for entry_name, entry_obj in objects.items():
            if entry_obj.get("type") != "MibTableRow":
                continue

            parse_result = self._parse_index_from_parent_mapping(entry_obj)
            if parse_result is None:
                continue
            parent_oid, parsed_inherited = parse_result

            entry_oid = self._oid_tuple(entry_obj.get("oid"))
            if entry_oid is None or len(entry_oid) < 1:
                continue

            child_table_oid = self._oid_list_to_str(list(entry_oid[:-1]))
            indexes = self._string_list(entry_obj.get("indexes"))
            child_meta = AugmentedTableChild(
                table_oid=child_table_oid,
                entry_name=entry_name,
                indexes=tuple(indexes),
                inherited_columns=tuple(parsed_inherited),
                default_columns=dict(seen_defaults.get(child_table_oid, {})),
            )
            self._augmented_parents.setdefault(parent_oid, []).append(child_meta)

    def _parse_index_from_parent_mapping(
        self,
        entry_obj: dict[str, JsonValue],
    ) -> tuple[str, list[str]] | None:
        index_from_raw = entry_obj.get("index_from")
        if not isinstance(index_from_raw, list) or not index_from_raw:
            return None

        parsed_inherited: list[str] = []
        parent_oids: set[str] = set()
        for inherit in index_from_raw:
            if not isinstance(inherit, (dict, list, tuple)):
                return None

            parsed = self._parse_index_from_entry(inherit)
            if parsed is None:
                return None

            parent_mib, parent_column = parsed
            parent_info = self._find_parent_table_for_column(parent_mib, parent_column)
            if not parent_info:
                return None

            parent_oids.add(parent_info["table_oid"])
            parsed_inherited.append(parent_column)

        if len(parent_oids) != 1:
            return None
        return next(iter(parent_oids)), parsed_inherited

    def _add_synthetic_augmented_children(
        self,
        *,
        seen_defaults: dict[str, dict[str, JsonValue]],
        table_entries: dict[str, tuple[str, tuple[str, ...]]],
    ) -> None:
        for table_oid, (entry_name, indexes_tuple) in table_entries.items():
            if table_oid in self._augmented_parents:
                continue
            if len(indexes_tuple) != 1:
                continue

            defaults = dict(seen_defaults.get(table_oid, {}))
            non_index_cols = [name for name in defaults if name not in indexes_tuple]
            synthetic_children = 2 if non_index_cols else 1

            for _ in range(synthetic_children):
                self._augmented_parents.setdefault(table_oid, []).append(
                    AugmentedTableChild(
                        table_oid=table_oid,
                        entry_name=entry_name,
                        indexes=indexes_tuple,
                        inherited_columns=indexes_tuple,
                        default_columns={},
                    )
                )

    def _propagate_augmented_tables(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        """Create matching rows for tables that AUGMENT the given table."""
        children = self._augmented_parents.get(table_oid, [])
        if not children:
            return

        for child in children:
            if child.table_oid in visited:
                continue
            if not child.table_oid:
                continue
            if child.indexes != child.inherited_columns:
                continue
            if (
                child.table_oid in self.table_instances
                and index_str in self.table_instances[child.table_oid]
            ):
                continue

            child_defaults = dict(child.default_columns) if child.default_columns else {}
            next_visited = set(visited)
            next_visited.add(child.table_oid)

            try:
                self.add_table_instance(
                    child.table_oid,
                    dict(index_values),
                    column_values=child_defaults,
                    propagate_augments=True,
                    _augment_path=next_visited,
                )
                self.logger.debug(
                    "Auto-created augmented row %s.%s from %s",
                    child.table_oid,
                    index_str,
                    table_oid,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.exception(
                    "Failed to add augmented row for %s",
                    child.table_oid,
                )

    def _propagate_augmented_deletions(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        """Delete matching rows for tables that AUGMENT the given table."""
        children = self._augmented_parents.get(table_oid, [])
        if not children:
            return

        for child in children:
            if child.table_oid in visited:
                continue
            if not child.table_oid:
                continue
            if child.indexes != child.inherited_columns:
                continue
            if child.table_oid not in self.table_instances:
                continue
            if index_str not in self.table_instances[child.table_oid]:
                continue

            next_visited = set(visited)
            next_visited.add(child.table_oid)

            try:
                self.delete_table_instance(
                    child.table_oid,
                    dict(index_values),
                    propagate_augments=True,
                    _augment_path=next_visited,
                )
                self.logger.debug(
                    "Auto-deleted augmented row %s.%s from %s",
                    child.table_oid,
                    index_str,
                    table_oid,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.exception(
                    "Failed to delete augmented row for %s",
                    child.table_oid,
                )

    def _format_index_value(self, value: JsonValue) -> str:
        """Normalize index values to a dotted string for comparison."""
        if isinstance(value, (list, tuple)):
            return ".".join(str(v) for v in value)
        if value is None:
            return ""
        return str(value)
