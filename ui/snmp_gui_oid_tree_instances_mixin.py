"""OID-tree table-instance population and refresh mixin for SNMP GUI."""

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: ANN401,D101,PLR2004

from __future__ import annotations

import traceback
from tkinter import messagebox
from typing import Any, cast

import requests


class SNMPGuiOidTreeInstancesMixin:
    def _populate_table_instances_immediate(self, table_item: str, table_oid: str) -> None:
        """Pre-populate table instances from bulk-loaded data."""
        try:
            table_data = self._get_table_instances_data_for_immediate_population(table_oid)
            if table_data is None:
                return

            instances = table_data.get("instances", [])
            entry_name = table_data.get("entry_name", "Entry")
            index_columns = table_data.get("index_columns", [])

            self._log(f"Pre-populating table {table_oid}: {len(instances)} instances", "DEBUG")

            if not instances:
                self._log(f"No instances to pre-populate for {table_oid}", "DEBUG")
                return

            entry_oid = table_oid + ".1"
            entry_tuple = tuple(int(x) for x in entry_oid.split("."))

            columns = self._collect_table_columns_for_entry(entry_tuple)
            columns_meta = self._build_columns_meta_for_immediate_population(columns)

            index_column_set = {name.lower() for name in index_columns}

            for inst in sorted(instances, key=self._instance_sort_key):
                self._add_prepopulated_instance_to_tree(
                    table_item=table_item,
                    table_oid=table_oid,
                    entry_name=entry_name,
                    instance=inst,
                    index_columns=index_columns,
                    columns_meta=columns_meta,
                    columns=columns,
                    index_column_set=index_column_set,
                )

            self._log(
                f"Pre-populated {len(instances)} instances for table {table_oid}",
                "DEBUG",
            )
            self._ensure_tree_column_width()

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error pre-populating table {table_oid}: {e}", "WARNING")
            traceback.print_exc()

    def _get_table_instances_data_for_immediate_population(
        self,
        table_oid: str,
    ) -> dict[str, Any] | None:
        if table_oid in self.table_instances_data:
            return cast("dict[str, Any]", self.table_instances_data[table_oid])
        self._log(
            f"Cannot pre-populate {table_oid}: not in table_instances_data",
            "DEBUG",
        )
        return None

    def _build_columns_meta_for_immediate_population(
        self,
        columns: list[tuple[str, str, int]],
    ) -> dict[str, Any]:
        columns_meta: dict[str, Any] = {}
        for col_name, col_oid, _ in columns:
            columns_meta[col_name] = self.oid_metadata.get(col_oid, {})
        return columns_meta

    def _insert_prepopulated_entry_node(
        self,
        table_item: str,
        table_oid: str,
        entry_name: str,
        instance: Any,
    ) -> str:
        entry_display = f"{entry_name}.{instance}"
        entry_img = None
        if getattr(self, "oid_icon_images", None):
            entry_img = self.oid_icon_images.get("entry")
        entry_img_ref = cast("Any", entry_img) if entry_img is not None else ""
        entry_item = self.oid_tree.insert(
            table_item,
            "end",
            text=entry_display,
            image=entry_img_ref,
            values=(
                table_oid,
                instance,
                "",
                "Entry",
                "N/A",
                self.oid_metadata.get(table_oid, {}).get("mib") or "N/A",
            ),
            tags=("table-entry",),
        )
        entry_full_oid = f"{table_oid}.{instance}"
        self.oid_to_item[entry_full_oid] = entry_item
        return str(entry_item)

    def _insert_prepopulated_column_node(
        self,
        entry_item: str,
        col_name: str,
        col_oid: str,
        instance: Any,
        value_here: Any,
        is_index: bool,
        full_col_oid: str,
    ) -> None:
        access = str(self.oid_metadata.get(col_oid, {}).get("access", "")).lower()
        type_str = self.oid_metadata.get(col_oid, {}).get("type") or "Unknown"
        access_str = self.oid_metadata.get(col_oid, {}).get("access") or "N/A"

        if is_index:
            icon_key = "key"
        elif "write" in access:
            icon_key = "edit"
        elif "read" in access or "not-accessible" in access or "none" in access:
            icon_key = "lock"
        else:
            icon_key = "chart"

        img = None
        if getattr(self, "oid_icon_images", None):
            img = self.oid_icon_images.get(icon_key)
        mib_val = self.oid_metadata.get(col_oid, {}).get("mib") or "N/A"
        img_ref = cast("Any", img) if img is not None else ""
        tags = (
            ("evenrow", "table-column", "table-index")
            if is_index
            else ("evenrow", "table-column")
        )

        col_item = self.oid_tree.insert(
            entry_item,
            "end",
            text=col_name,
            image=img_ref,
            values=(
                col_oid,
                instance,
                value_here,
                type_str,
                access_str,
                mib_val,
            ),
            tags=tags,
        )
        self.oid_to_item[full_col_oid] = col_item
        if col_oid not in self.oid_to_item:
            self.oid_to_item[col_oid] = col_item

    def _add_prepopulated_instance_to_tree(
        self,
        table_item: str,
        table_oid: str,
        entry_name: str,
        instance: Any,
        index_columns: list[str],
        columns_meta: dict[str, Any],
        columns: list[tuple[str, str, int]],
        index_column_set: set[str],
    ) -> None:
        entry_item = self._insert_prepopulated_entry_node(
            table_item,
            table_oid,
            entry_name,
            instance,
        )
        index_values = self._extract_index_values(instance, index_columns, columns_meta)

        for col_name, col_oid, _col_num in columns:
            full_col_oid = f"{col_oid}.{instance}"
            is_index = col_name.lower() in index_column_set
            value_here = index_values.get(col_name, "N/A") if is_index else self.oid_values.get(
                full_col_oid,
                "unset",
            )
            self._insert_prepopulated_column_node(
                entry_item=entry_item,
                col_name=col_name,
                col_oid=col_oid,
                instance=instance,
                value_here=value_here,
                is_index=is_index,
                full_col_oid=full_col_oid,
            )

    def _resolve_entry_metadata(self, entry_oid: str) -> tuple[str, tuple[int, ...], str | None]:
        entry_name: str | None = None
        entry_tuple = tuple(int(x) for x in (entry_oid + ".1").split("."))

        for name, oid_t in self.oids_data.items():
            if oid_t == entry_tuple:
                entry_name = name
                break

        if not entry_name:
            self._log(f"Could not find name for entry OID {entry_oid}.1", "WARNING")
            entry_name = "Entry"

        first_col_oid: str | None = None
        for oid_t in self.oids_data.values():
            if oid_t[: len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                first_col_oid = ".".join(str(x) for x in oid_t)
                break

        return entry_name, entry_tuple, first_col_oid

    def _load_table_schema_instances(self, entry_oid: str) -> tuple[list[str], list[str]]:
        instances: list[str] = []
        index_columns: list[str] = []
        try:
            resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": entry_oid},
                timeout=5,
            )
            if resp.status_code == 200:
                schema = resp.json()
                instances = [str(inst) for inst in schema.get("instances", [])]
                index_columns = list(schema.get("index_columns", []))
                self._log(
                    f"Table schema loaded for {entry_oid}: found {len(instances)} "
                    f"instances: {instances}, index_columns={index_columns}",
                    "INFO",
                )
            else:
                self._log(
                    f"Table schema request failed for {entry_oid}: {resp.status_code} {resp.text}",
                    "WARNING",
                )
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error loading table schema for {entry_oid}: {e}", "WARNING")

        return instances, index_columns

    def _fallback_discover_instances(self, first_col_oid: str, entry_oid: str) -> list[str]:
        instances: list[str] = []
        index = 1
        max_attempts = 20
        while len(instances) < max_attempts:
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": first_col_oid + "." + str(index)},
                    timeout=1,
                )
                if resp.status_code == 200:
                    instances.append(str(index))
                    index += 1
                else:
                    break
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                break

        if len(instances) == max_attempts:
            messagebox.showwarning("Warning", "Reached maximum attempts while loading instances.")

        self._log(
            f"Fallback instance discovery used for {entry_oid}: instances={instances}",
            "DEBUG",
        )
        return instances

    def _collect_table_columns_for_entry(
        self,
        entry_tuple: tuple[int, ...],
    ) -> list[tuple[str, str, int]]:
        columns: list[tuple[str, str, int]] = []
        for name, oid_t in self.oids_data.items():
            if oid_t[: len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                col_num = oid_t[-1]
                col_oid = ".".join(str(x) for x in oid_t)
                columns.append((name, col_oid, col_num))
        columns.sort(key=lambda x: x[2])
        return columns

    @staticmethod
    def _instance_sort_key(inst: Any) -> list[tuple[int, Any]]:
        parts = str(inst).split(".")
        key: list[tuple[int, Any]] = []
        for part in parts:
            if part.isdigit():
                key.append((0, int(part)))
            else:
                key.append((1, part))
        return key

    def _build_grouped_instance_cells(
        self,
        instances: list[str],
        columns: list[tuple[str, str, int]],
        index_columns: list[str],
    ) -> dict[str, list[tuple[str, str, str, str, bool]]]:
        columns_meta: dict[str, Any] = {}
        for name, col_oid, _ in columns:
            if name in index_columns:
                columns_meta[name] = self.oid_metadata.get(col_oid, {})

        grouped: dict[str, list[tuple[str, str, str, str, bool]]] = {}
        index_name_set = {idx.lower() for idx in index_columns}

        instances_index_values: dict[str, dict[str, str]] = {}
        for inst in instances:
            instances_index_values[inst] = self._extract_index_values(
                inst,
                index_columns,
                columns_meta,
            )

        for inst in instances:
            grouped[inst] = []
            for name, col_oid, _ in columns:
                full_col_oid = f"{col_oid}.{inst}"
                is_index = name.lower() in index_name_set

                if full_col_oid in self.oid_values:
                    value_here = self.oid_values[full_col_oid]
                    if is_index:
                        value_here = instances_index_values[inst].get(name, "N/A")
                elif is_index:
                    value_here = instances_index_values[inst].get(name, "N/A")
                    self.oid_values[full_col_oid] = value_here
                else:
                    try:
                        resp = requests.get(
                            f"{self.api_url}/value",
                            params={"oid": full_col_oid},
                            timeout=2,
                        )
                        if resp.status_code == 200:
                            value_here = str(resp.json().get("value", "unset"))
                            self.oid_values[full_col_oid] = value_here
                        else:
                            value_here = "unset"
                            self.oid_values[full_col_oid] = value_here
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        value_here = "unset"
                        self.oid_values[full_col_oid] = value_here
                grouped[inst].append((name, col_oid, full_col_oid, value_here, is_index))

        return grouped

    def _apply_discovered_instances_to_tree(  # noqa: PLR0915
        self,
        item: str,
        entry_oid: str,
        entry_name: str,
        grouped: dict[str, list[tuple[str, str, str, str, bool]]],
        index_columns: list[str],
    ) -> None:
        existing_children = self.oid_tree.get_children(item)
        self._log(f"Removing {len(existing_children)} existing children from table", "DEBUG")
        for child in existing_children:
            self.oid_tree.delete(child)

        self._log(
            f"Adding {len(grouped)} new instances to OID tree: {list(grouped.keys())}",
            "INFO",
        )
        index_column_set = {name.lower() for name in index_columns}
        added_count = 0
        for inst, cols in grouped.items():
            entry_display = f"{entry_name}.{inst}"
            mib_val = self.oid_metadata.get(entry_oid, {}).get("mib") or "N/A"
            entry_img = None
            if getattr(self, "oid_icon_images", None):
                entry_img = self.oid_icon_images.get("entry")
            entry_img_ref = cast("Any", entry_img) if entry_img is not None else ""
            entry_item = self.oid_tree.insert(
                item,
                "end",
                text=entry_display,
                image=entry_img_ref,
                values=(entry_oid, inst, "", "Entry", "N/A", mib_val),
                tags=("table-entry",),
            )
            entry_full_oid = f"{entry_oid}.{inst}"
            self.oid_to_item[entry_full_oid] = entry_item
            added_count += 1

            for name, col_oid, full_col_oid, value_here, is_index in cols:
                access = str(self.oid_metadata.get(col_oid, {}).get("access", "")).lower()
                type_str = self.oid_metadata.get(col_oid, {}).get("type") or "Unknown"
                access_str = self.oid_metadata.get(col_oid, {}).get("access") or "N/A"
                if name.lower() in index_column_set:
                    icon_key = "key"
                elif "write" in access:
                    icon_key = "edit"
                elif "read" in access or "not-accessible" in access or "none" in access:
                    icon_key = "lock"
                else:
                    icon_key = "chart"

                display_value = value_here
                if value_here not in ("unset", "N/A", ""):
                    col_metadata = self.oid_metadata.get(col_oid, {})
                    enums = col_metadata.get("enums")
                    if enums:
                        try:
                            int_value = int(value_here)
                            for enum_name, enum_value in enums.items():
                                if enum_value == int_value:
                                    display_value = f"{value_here} ({enum_name})"
                                    break
                        except (ValueError, TypeError):
                            pass

                img = None
                if getattr(self, "oid_icon_images", None):
                    img = self.oid_icon_images.get(icon_key)
                mib_val = self.oid_metadata.get(col_oid, {}).get("mib") or "N/A"
                img_ref = cast("Any", img) if img is not None else ""
                col_item = self.oid_tree.insert(
                    entry_item,
                    "end",
                    text=name,
                    image=img_ref,
                    values=(
                        col_oid,
                        inst,
                        display_value,
                        type_str,
                        access_str,
                        mib_val,
                    ),
                    tags=(
                        ("evenrow", "table-column", "table-index")
                        if is_index
                        else ("evenrow", "table-column")
                    ),
                )
                self.oid_to_item[full_col_oid] = col_item
                if col_oid not in self.oid_to_item:
                    self.oid_to_item[col_oid] = col_item

        self._log(f"Successfully added {added_count} instances to OID tree", "INFO")
        self.oid_tree.item(item, open=True)
        self._ensure_tree_column_width()

    def _discover_table_instances(self, item: str, entry_oid: str) -> None:
        """Discover table instances and populate the tree."""
        self._log(f"Discovering table instances for table OID {entry_oid}", "DEBUG")

        entry_name, entry_tuple, first_col_oid = self._resolve_entry_metadata(entry_oid)
        if not first_col_oid:
            self._log(f"No columns found for table {entry_oid}", "WARNING")
            return

        instances, index_columns = self._load_table_schema_instances(entry_oid)
        if not instances:
            instances = self._fallback_discover_instances(first_col_oid, entry_oid)

        columns = self._collect_table_columns_for_entry(entry_tuple)
        instances = sorted(instances, key=self._instance_sort_key)
        grouped = self._build_grouped_instance_cells(instances, columns, index_columns)

        self.root.after(
            0,
            lambda: self._apply_discovered_instances_to_tree(
                item,
                entry_oid,
                entry_name,
                grouped,
                index_columns,
            ),
        )

    def _resolve_fetch_oid_for_child(
        self,
        child: str,
    ) -> tuple[str, str, str] | None:
        oid_str = self.oid_tree.set(child, "oid")
        instance_str = self.oid_tree.set(child, "instance")
        tags = self.oid_tree.item(child, "tags")
        if not oid_str or "table-index" in tags:
            return None

        if instance_str == "0":
            fetch_oid = oid_str + ".0"
        elif instance_str:
            parts = instance_str.split(".")
            if not all(part.isdigit() for part in parts if part):
                return None
            fetch_oid = oid_str + "." + instance_str
        else:
            return None

        return fetch_oid, oid_str, instance_str

    def _format_display_value_with_enums(self, oid_str: str, val_str: str) -> str:
        if val_str in ("unset", "N/A", ""):
            return val_str

        metadata = self.oid_metadata.get(oid_str, {})
        enums = metadata.get("enums")
        if not enums:
            return val_str

        try:
            int_value = int(val_str)
            for enum_name, enum_value in enums.items():
                if enum_value == int_value:
                    return f"{val_str} ({enum_name})"
        except (ValueError, TypeError):
            pass
        return val_str

    def _queue_child_value_update(self, child: str, display_val: str) -> None:
        def update_ui(c: str = child, v: str = display_val) -> None:
            self.oid_tree.set(c, "value", v)

        self.root.after(0, update_ui)

    def _fetch_and_cache_oid_value(
        self,
        fetch_oid: str,
        oid_str: str,
        instance_str: str,
        child: str,
    ) -> None:
        self._log(f"Fetching value for OID {fetch_oid} (instance={instance_str})")
        resp = requests.get(
            f"{self.api_url}/value",
            params={"oid": fetch_oid},
            timeout=3,
        )
        resp.raise_for_status()

        val = resp.json().get("value", "unset")
        val_str = "unset" if val is None else str(val)
        self.oid_values[fetch_oid] = val_str
        display_val = self._format_display_value_with_enums(oid_str, val_str)
        self._queue_child_value_update(child, display_val)
        self._log(f"Fetched value for OID {fetch_oid}: {val_str}")

    def _process_child_value_fetch(self, child: str) -> None:
        if self.oid_tree.get_children(child):
            return

        resolved = self._resolve_fetch_oid_for_child(child)
        if resolved is None:
            return

        fetch_oid, oid_str, instance_str = resolved
        if fetch_oid in self.oid_values:
            return

        try:
            self._fetch_and_cache_oid_value(fetch_oid, oid_str, instance_str, child)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.oid_values[fetch_oid] = ""
            self._log(f"Failed to fetch value for OID {fetch_oid}: {e}", "WARNING")

    def _fetch_values_for_node(self, item: str) -> None:
        """Background worker: fetch values for immediate children of `item`.

        This runs in a worker thread and updates the UI via `root.after`.
        """
        try:
            children = list(self.oid_tree.get_children(item))
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        for child in children:
            self._process_child_value_fetch(child)

    def _refresh_oid_tree_value(self, full_oid: str, display_value: str) -> None:
        """Refresh a specific OID value in the tree after it's been updated.

        Args:
            full_oid: The full OID including instance (e.g., "1.3.6.1.2.1.2.2.1.8.1")
            display_value: The formatted display value to show

        """
        parts = full_oid.rsplit(".", 1)
        if len(parts) == 2:
            base_oid, instance = parts
        else:
            base_oid = full_oid
            instance = ""

        def find_and_update(item: str) -> bool:
            """Recursively search for the matching tree item."""
            try:
                item_oid = self.oid_tree.set(item, "oid")
                item_instance = self.oid_tree.set(item, "instance")

                if item_oid == base_oid and item_instance == instance:
                    self.oid_tree.set(item, "value", display_value)
                    self._log(
                        f"Refreshed OID tree value for {full_oid}: {display_value}",
                        "DEBUG",
                    )
                    return True

                for child in self.oid_tree.get_children(item):
                    if find_and_update(child):
                        return True

            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self._log(f"Error searching tree item: {e}", "DEBUG")

            return False

        for root_item in self.oid_tree.get_children():
            if find_and_update(root_item):
                break

    def _add_instance_to_oid_tree(self, table_item: str, instance: str) -> None:
        """Add a single new instance to the OID tree immediately.

        Args:
            table_item: The tree item ID for the table node
            instance: The instance string (e.g., "5" or "192.168.1.1")

        """
        try:
            table_oid = self.oid_tree.set(table_item, "oid")
            if not table_oid:
                self._log("Cannot add instance: no table OID found", "WARNING")
                return

            self._log(f"Adding instance {instance} to OID tree table {table_oid}", "INFO")

            self.executor.submit(self._discover_table_instances, table_item, table_oid)

            def refresh_augmented_tables() -> None:
                """Find and refresh all augmented tables that depend on this parent."""
                try:
                    self._refresh_augmented_tables_for_parent(table_oid)
                except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                    self._log(f"Error refreshing augmented tables: {e}", "WARNING")

            self.root.after(500, lambda: self.executor.submit(refresh_augmented_tables))

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error adding instance to OID tree: {e}", "ERROR")

    def _remove_instance_from_oid_tree(self, table_item: str, instance: str) -> None:
        """Remove a single instance from the OID tree immediately.

        Args:
            table_item: The tree item ID for the table node
            instance: The instance string to remove (e.g., "5" or "192.168.1.1")

        """
        try:
            table_oid = self.oid_tree.set(table_item, "oid")
            if not table_oid:
                self._log("Cannot remove instance: no table OID found", "WARNING")
                return

            self._log(f"Removing instance {instance} from OID tree table {table_oid}", "INFO")

            def delete_entry() -> None:
                children = self.oid_tree.get_children(table_item)
                for child in children:
                    child_instance = self.oid_tree.set(child, "instance")
                    if child_instance == instance:
                        self.oid_tree.delete(child)
                        self._log(f"Deleted instance {instance} from OID tree", "DEBUG")
                        return
                self._log(f"Instance {instance} not found in OID tree", "DEBUG")

            self.root.after(0, delete_entry)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error removing instance from OID tree: {e}", "ERROR")

    def _refresh_oid_tree_table(self, table_item: str) -> None:
        """Refresh a table in the OID tree to show new/updated instances.

        This re-discovers table instances and rebuilds the tree nodes.

        Args:
            table_item: The tree item ID for the table node

        """
        try:
            oid_str = self.oid_tree.set(table_item, "oid")
            if not oid_str:
                self._log("Cannot refresh table: no OID found", "WARNING")
                return

            self._log(
                f"Refreshing OID tree table {oid_str} - will re-query /table-schema",
                "INFO",
            )

            self.executor.submit(self._discover_table_instances, table_item, oid_str)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error refreshing OID tree table: {e}", "ERROR")
            traceback.print_exc()

    def _refresh_augmented_tables_for_parent(self, parent_table_oid: str) -> None:
        """Find and refresh all augmented tables that depend on a parent table.

        When a parent table (e.g., ifTable) gets a new instance, any augmented
        tables that inherit from it (e.g., ifXTable, ifTestTable) should also
        be refreshed to show the new instance.

        Args:
            parent_table_oid: The OID of the parent table (e.g., "1.3.6.1.2.1.2.2")

        """
        try:
            self._log(
                f"Looking for augmented tables that depend on parent {parent_table_oid}",
                "INFO",
            )

            def search_for_augmented_tables(item: str) -> None:
                """Recursively search the tree for augmented table nodes."""
                try:
                    item_oid = self.oid_tree.set(item, "oid")
                    item_tags = self.oid_tree.item(item, "tags")

                    if "table" in item_tags and item_oid and item_oid != parent_table_oid:
                        try:
                            resp = requests.get(
                                f"{self.api_url}/table-schema",
                                params={"oid": item_oid},
                                timeout=5,
                            )
                            if resp.status_code == 200:
                                schema = resp.json()
                                index_from = schema.get("index_from", [])

                                if index_from:
                                    self._log(
                                        f"Found augmented table {item_oid} "
                                        f"(index_from={index_from})",
                                        "DEBUG",
                                    )
                                    self.executor.submit(
                                        self._discover_table_instances,
                                        item,
                                        item_oid,
                                    )
                        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                            self._log(
                                f"Error checking table schema for {item_oid}: {e}",
                                "DEBUG",
                            )

                    for child in self.oid_tree.get_children(item):
                        search_for_augmented_tables(child)

                except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                    self._log(f"Error searching for augmented tables: {e}", "DEBUG")

            for root_item in self.oid_tree.get_children():
                search_for_augmented_tables(root_item)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error in _refresh_augmented_tables_for_parent: {e}", "ERROR")
