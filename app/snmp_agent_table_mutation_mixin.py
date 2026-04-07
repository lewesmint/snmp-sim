"""Table mutation helpers for SNMPAgent."""

# ruff: noqa: ANN401,D102,FBT002,PLR0911,RUF005,TC001,TRY300,TRY400,TRY401

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from app.snmp_agent_table_state_mixin import JsonValue
from app.value_links import get_link_manager

if TYPE_CHECKING:
    from logging import Logger

    from pysnmp_type_wrapper.interfaces import MutableScalarInstance, SupportsClone


class SNMPAgentTableMutationMixin:
    """Mixin for dynamic table cell updates and row lifecycle operations."""

    logger: Logger
    table_instances: Any
    deleted_instances: list[str]
    mib_builder: Any

    def _get_mib_symbols_adapter(self) -> Any:
        return cast("Any", None)

    def _normalize_oid_str(self, oid: str) -> str:
        return ".".join(part for part in oid.strip().strip(".").split(".") if part)

    def _instance_defined_in_schema(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
    ) -> bool:
        del table_oid, index_values
        return False

    def _propagate_augmented_tables(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        del table_oid, index_values, index_str, visited

    def _propagate_augmented_deletions(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        del table_oid, index_values, index_str, visited

    def save_mib_state(self) -> None:
        return None

    def _create_missing_cell_instance(  # noqa: PLR0915
        self,
        column_name: str,
        cell_oid: tuple[int, ...],
        value: JsonValue,
    ) -> bool:
        """Create a missing MibScalarInstance for a table cell if needed.

        This is called when loading state with instances that weren't in the
        original schema. We need to create the MibScalarInstance objects so
        pysnmp can find them during queries.

        Args:
            column_name: The column name (e.g., "ifDescr")
            cell_oid: The full cell OID as tuple (e.g., (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2))
            value: The value to set for this cell

        Returns:
            True if instance was created or already existed, False on error

        """
        if self.mib_builder is None:
            return False

        symbols_adapter = self._get_mib_symbols_adapter()

        mib_scalar_instance_cls = symbols_adapter.load_symbol_class(
            "SNMPv2-SMI",
            "MibScalarInstance",
        )
        if mib_scalar_instance_cls is None:
            self.logger.debug("Could not import MibScalarInstance")
            return False

        existing = symbols_adapter.find_scalar_instance_by_oid(
            cell_oid,
            mib_scalar_instance_cls,
        )
        if existing is not None:
            return True

        template_data = symbols_adapter.find_template_instance_for_column(
            column_name,
            mib_scalar_instance_cls,
        )
        target_module: str | None = None
        column_oid: tuple[int, ...] | None = None
        syntax_source: object | None = None

        if template_data is not None:
            target_module, template_instance, column_oid = template_data
            syntax_source = getattr(template_instance, "syntax", None)
        else:
            # Fresh tables may have no existing row instance to clone from yet.
            # Fall back to cloning the column prototype syntax directly.
            mib_table_column_cls = symbols_adapter.load_symbol_class(
                "SNMPv2-SMI",
                "MibTableColumn",
            )
            symbols = cast(
                "dict[str, dict[str, object]]",
                getattr(self.mib_builder, "mibSymbols", {}),
            )
            for module_name, module_symbols in symbols.items():
                column_obj = module_symbols.get(column_name)
                if (
                    column_obj is None
                    or mib_table_column_cls is None
                    or not isinstance(column_obj, mib_table_column_cls)
                ):
                    continue
                raw_name = getattr(column_obj, "name", None)
                if not isinstance(raw_name, tuple):
                    continue
                if not all(isinstance(part, int) for part in raw_name):
                    continue
                target_module = module_name
                column_oid = cast("tuple[int, ...]", raw_name)
                syntax_source = getattr(column_obj, "syntax", None)
                break

        if target_module is None or column_oid is None or syntax_source is None:
            self.logger.debug(
                "Could not find template or column prototype for %s to determine type",
                column_name,
            )
            return False

        try:
            new_syntax = cast("SupportsClone", syntax_source).clone(value)
            index_tuple = cell_oid[len(column_oid) :]
            instance_ctor: Callable[..., object] = cast(
                "Callable[..., object]", mib_scalar_instance_cls
            )
            new_instance = instance_ctor(column_oid, index_tuple, new_syntax)

            # Register the row cell in the owning table column runtime map.
            # This is the authoritative lookup path used by pysnmp table GETs.
            symbols = cast(
                "dict[str, dict[str, object]]",
                getattr(self.mib_builder, "mibSymbols", {}),
            )
            module_symbols = symbols.get(target_module, {})
            column_symbol = module_symbols.get(column_name)
            vars_dict = getattr(column_symbol, "_vars", None)
            if isinstance(vars_dict, dict):
                vars_dict[cell_oid] = new_instance
                with contextlib.suppress(AttributeError, TypeError):
                    dynamic_column = cast("Any", column_symbol)
                    dynamic_column.branchVersionId += 1
            else:
                self.logger.debug(
                    "Column %s in %s has no _vars map; falling back to symbol export",
                    column_name,
                    target_module,
                )
                instance_name = f"{column_name}Inst_{'_'.join(str(x) for x in index_tuple)}"
                if not symbols_adapter.upsert_symbol(target_module, instance_name, new_instance):
                    self.logger.debug(
                        "Could not upsert new instance %s into module %s",
                        instance_name,
                        target_module,
                    )
                    return False

            self.logger.info(
                "Created missing MibScalarInstance %s for %s = %s",
                cell_oid,
                column_name,
                value,
            )
            return True

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.debug(
                "Failed to create MibScalarInstance for %s: %s",
                cell_oid,
                e,
            )
            return False

    def update_table_cell_values(
        self,
        table_oid: str,
        instance_str: str,
        column_values: dict[str, JsonValue],
        _processed: set[str] | None = None,
    ) -> None:
        """Update the MibScalarInstance objects for table cell values.

        Args:
            table_oid: The table OID (e.g., "1.3.6.1.4.1.99998.1.4")
            instance_str: The instance index as string (e.g., "1")
            column_values: Dict mapping column names to values
            _processed: Internal set of columns already processed in this update session

        """
        if self.mib_builder is None:
            return

        symbols_adapter = self._get_mib_symbols_adapter()

        if _processed is None:
            _processed = set()

        mib_scalar_instance_cls = symbols_adapter.load_symbol_class(
            "SNMPv2-SMI",
            "MibScalarInstance",
        )
        if mib_scalar_instance_cls is None:
            self.logger.error("Failed to import MibScalarInstance")
            return

        table_parts = tuple(int(x) for x in table_oid.split("."))
        entry_oid = table_parts + (1,)

        instance_parts = tuple(int(x) for x in instance_str.split("."))

        link_manager = get_link_manager()
        instance_key = f"{table_oid}:{instance_str}"

        for column_name, value in column_values.items():
            processed_key = f"{table_oid}:{column_name}"
            if processed_key in _processed:
                self.logger.debug(
                    "Skipping %s in %s (already processed via propagation)", column_name, table_oid
                )
                continue

            if not link_manager.should_propagate(column_name, instance_key):
                self.logger.debug("Skipping propagation for %s (already updating)", column_name)
                continue

            try:
                link_manager.begin_update(column_name, instance_key)
                _processed.add(processed_key)
                normalized_value = self._normalize_table_cell_value(column_name, value)
                changed = self._apply_single_table_cell_update(
                    table_oid=table_oid,
                    instance_str=instance_str,
                    column_name=column_name,
                    value=normalized_value,
                    entry_oid=entry_oid,
                    instance_parts=instance_parts,
                    symbols_adapter=symbols_adapter,
                    mib_scalar_instance_cls=mib_scalar_instance_cls,
                )

                if changed:
                    self._propagate_linked_table_cell_update(
                        link_manager=link_manager,
                        table_oid=table_oid,
                        instance_str=instance_str,
                        column_name=column_name,
                        value=normalized_value,
                        processed=_processed,
                    )

            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.exception("Error updating column %s: %s", column_name, e)
            finally:
                link_manager.end_update(column_name, instance_key)

    def _normalize_table_cell_value(self, column_name: str, value: JsonValue) -> JsonValue:
        if isinstance(value, list):
            self.logger.debug(
                "%s", f"Converting list to string for column {column_name}: {value}"
            )
            return ".".join(str(x) for x in value)
        if isinstance(value, dict):
            self.logger.debug(
                "%s", f"Converting dict to string for column {column_name}: {value}"
            )
            return str(value)
        return value

    def _store_table_cell_value(
        self,
        *,
        table_oid: str,
        instance_str: str,
        column_name: str,
        value: JsonValue,
    ) -> bool:
        if table_oid not in self.table_instances:
            return False
        if instance_str not in self.table_instances[table_oid]:
            return False

        instance_data = cast("dict[str, JsonValue]", self.table_instances[table_oid][instance_str])
        column_values = instance_data.get("column_values")
        if not isinstance(column_values, dict):
            column_values = {}
            instance_data["column_values"] = column_values
        column_values[column_name] = value
        return True

    def _update_existing_cell_instance(
        self,
        *,
        symbol_obj: object,
        cell_oid: tuple[int, ...],
        value: JsonValue,
    ) -> bool:
        try:
            typed_symbol = cast("MutableScalarInstance", symbol_obj)
            new_syntax = cast("SupportsClone", typed_symbol.syntax).clone(value)
            typed_symbol.syntax = new_syntax
            self.logger.debug("Updated MibScalarInstance %s = %s", cell_oid, value)
            return True
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.error(
                "Failed to update MibScalarInstance %s with value %r (type: %s): %s",
                cell_oid,
                value,
                type(value).__name__,
                e,
            )
            return False

    def _apply_single_table_cell_update(
        self,
        *,
        table_oid: str,
        instance_str: str,
        column_name: str,
        value: JsonValue,
        entry_oid: tuple[int, ...],
        instance_parts: tuple[int, ...],
        symbols_adapter: Any,
        mib_scalar_instance_cls: type[object],
    ) -> bool:
        stored = self._store_table_cell_value(
            table_oid=table_oid,
            instance_str=instance_str,
            column_name=column_name,
            value=value,
        )

        column_oid = symbols_adapter.find_column_oid_for_entry(column_name, entry_oid)
        if not column_oid:
            self.logger.debug("Could not find column OID for %s", column_name)
            return stored

        cell_oid = column_oid + instance_parts
        symbol_obj = symbols_adapter.find_scalar_instance_by_oid(cell_oid, mib_scalar_instance_cls)

        updated = False
        if symbol_obj is not None:
            updated = self._update_existing_cell_instance(
                symbol_obj=symbol_obj,
                cell_oid=cell_oid,
                value=value,
            )

        if not updated and self._create_missing_cell_instance(column_name, cell_oid, value):
            updated = True
            self.logger.info("Created missing MibScalarInstance for %s", cell_oid)

        return updated or stored

    def _propagate_linked_table_cell_update(
        self,
        *,
        link_manager: Any,
        table_oid: str,
        instance_str: str,
        column_name: str,
        value: JsonValue,
        processed: set[str],
    ) -> None:
        linked_targets = link_manager.get_linked_targets(column_name, table_oid)
        if not linked_targets:
            return

        targets_display = [f"{t.table_oid}:{t.column_name}" for t in linked_targets]
        self.logger.info(
            "Propagating value from %s to linked columns: %s",
            column_name,
            targets_display,
        )
        for target in linked_targets:
            target_table = target.table_oid or table_oid
            linked_values: dict[str, JsonValue] = {target.column_name: value}
            self.update_table_cell_values(target_table, instance_str, linked_values, processed)

    def add_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        column_values: dict[str, JsonValue] | None = None,
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> str:
        """Add a new table instance and persist it, optionally propagating augment tables.

        Args:
            table_oid: The OID of the table (e.g., "1.3.6.1.4.1.99998.1.3.1")
            index_values: Dict mapping index column names to values
            column_values: Optional dict mapping column names to values
            propagate_augments: Whether to create matching rows for AUGMENTS tables
            _augment_path: Internal set used to avoid cycles during propagation

        Returns:
            The instance OID as a string

        """
        if column_values is None:
            column_values = {}

        serialized_column_values: dict[str, JsonValue] = {}
        for col_name, col_value in column_values.items():
            if isinstance(col_value, list):
                serialized_column_values[col_name] = ".".join(str(x) for x in col_value)
            elif isinstance(col_value, dict):
                serialized_column_values[col_name] = str(col_value)
            else:
                serialized_column_values[col_name] = col_value

        table_oid = self._normalize_oid_str(table_oid)

        index_str = self._build_index_str(index_values)
        instance_oid = f"{table_oid}.{index_str}"

        if table_oid not in self.table_instances:
            self.table_instances[table_oid] = {}

        self.table_instances[table_oid][index_str] = {"column_values": serialized_column_values}

        if instance_oid in self.deleted_instances:
            self.deleted_instances.remove(instance_oid)

        self.update_table_cell_values(table_oid, index_str, serialized_column_values)

        self.save_mib_state()

        self.logger.info("Added table instance: %s", instance_oid)

        if propagate_augments:
            visited = set(_augment_path) if _augment_path else set()
            if table_oid not in visited:
                visited.add(table_oid)
                self._propagate_augmented_tables(
                    table_oid,
                    dict(index_values),
                    index_str,
                    visited,
                )
        return instance_oid

    def _build_index_str(self, index_values: dict[str, JsonValue]) -> str:
        """Build an instance index string, supporting implied/faux indices and multi-part indexes.

        Supports:
        - __index__: "5" → "5"
        - __index__, __index_2__: builds "5.10" from parts
        - Regular index columns: joins all values with dots
        """
        if not index_values:
            return "1"

        index_parts = []
        i = 1
        while True:
            key = "__index__" if i == 1 else f"__index_{i}__"
            if key in index_values:
                index_parts.append(str(index_values[key]))
                i += 1
            else:
                break

        if index_parts:
            return ".".join(index_parts)

        if "__instance__" in index_values:
            return str(index_values["__instance__"])

        return ".".join(str(v) for v in index_values.values())

    def delete_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> bool:
        """Mark a table instance as deleted and optionally cascade to AUGMENTS children."""
        table_oid = self._normalize_oid_str(table_oid)
        index_str = self._build_index_str(index_values)
        instance_oid = f"{table_oid}.{index_str}"

        if table_oid in self.table_instances and index_str in self.table_instances[table_oid]:
            del self.table_instances[table_oid][index_str]

            if not self.table_instances[table_oid]:
                del self.table_instances[table_oid]

        if self._instance_defined_in_schema(table_oid, index_values):
            if instance_oid not in self.deleted_instances:
                self.deleted_instances.append(instance_oid)
                self.save_mib_state()
                self.logger.info("Deleted table instance: %s", instance_oid)
        else:
            self.logger.info("Skipping deleted_instances for %s (not in schema rows)", instance_oid)

        if propagate_augments:
            visited = set(_augment_path) if _augment_path else set()
            if table_oid not in visited:
                visited.add(table_oid)
                self._propagate_augmented_deletions(
                    table_oid,
                    dict(index_values),
                    index_str,
                    visited,
                )

        return True

    def restore_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        column_values: dict[str, JsonValue] | None = None,
    ) -> bool:
        """Restore a previously deleted table instance.

        Args:
            table_oid: The OID of the table
            index_values: Dict mapping index column names to values
            column_values: Optional dict mapping column names to values

        Returns:
            True if instance was restored

        """
        instance_oid = f"{table_oid}.{self._build_index_str(index_values)}"

        if instance_oid in self.deleted_instances:
            self.add_table_instance(table_oid, index_values, column_values or {})
            return True

        return False
