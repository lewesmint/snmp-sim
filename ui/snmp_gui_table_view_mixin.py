"""Table view and table instance management mixin for SNMP GUI."""

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: ANN401,D101,PLR2004,TRY300

from __future__ import annotations

from tkinter import messagebox
from typing import Any, cast

import customtkinter as ctk
import requests


class SNMPGuiTableViewMixin:
    def _populate_table_view(self, table_item: str, selected_instance: str | None = None) -> None:
        """Populate the table view with data from the selected table."""
        oid_str = self.oid_tree.set(table_item, "oid")
        if not oid_str:
            self._log("No OID found for table item", "WARNING")
            return

        selected_instance, preserved_yview = self._capture_table_view_selection_state(
            selected_instance,
        )
        preserved_widths = self._capture_table_column_widths()
        self._clear_table_tree_rows()

        entry_tuple, _entry_name = self._resolve_entry_for_table_oid(oid_str)
        columns = self._discover_table_columns(entry_tuple)

        if not columns:
            self._log(f"No columns found for table {oid_str}", "WARNING")
            return

        self._log(f"Found {len(columns)} columns for table {oid_str}")

        schema, instances, index_columns = self._load_table_schema_with_fallback(
            oid_str,
            columns[0][1],
        )
        instances = sorted(instances, key=self._table_instance_sort_key)

        col_names = [col[0] for col in columns]
        self._configure_table_columns(
            col_names=col_names,
            index_columns=index_columns,
            preserved_widths=preserved_widths,
        )

        self._current_table_columns = columns
        self._current_index_columns = index_columns
        self._current_columns_meta = schema.get("columns", {})
        self._current_table_item = table_item
        self._current_table_oid = oid_str

        row_items = self._populate_table_rows(instances, columns, index_columns, schema)
        self._restore_table_selection_or_scroll(
            row_items=row_items,
            selected_instance=selected_instance,
            preserved_yview=preserved_yview,
            table_oid=oid_str,
        )
        self._update_add_index_button_state(index_columns)

    def _capture_table_view_selection_state(
        self,
        selected_instance: str | None,
    ) -> tuple[str | None, tuple[float, float] | None]:
        preserved_yview = self.table_tree.yview() if self.table_tree.winfo_exists() else None
        if selected_instance is not None:
            return selected_instance, preserved_yview

        selected_rows = self.table_tree.selection()
        if not selected_rows:
            return None, preserved_yview

        selected_values = self.table_tree.item(selected_rows[0], "values")
        if not selected_values:
            return None, preserved_yview
        return str(selected_values[0]), preserved_yview

    def _capture_table_column_widths(self) -> dict[str, int]:
        preserved_widths: dict[str, int] = {}
        for col_id in self.table_tree["columns"]:
            try:
                preserved_widths[col_id] = int(self.table_tree.column(col_id, "width"))
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                continue
        return preserved_widths

    def _clear_table_tree_rows(self) -> None:
        for child in self.table_tree.get_children():
            self.table_tree.delete(child)

    def _resolve_entry_for_table_oid(self, oid_str: str) -> tuple[tuple[int, ...], str]:
        entry_tuple = tuple(int(x) for x in f"{oid_str}.1".split("."))
        entry_name = next(
            (name for name, oid_t in self.oids_data.items() if oid_t == entry_tuple),
            None,
        )
        return entry_tuple, entry_name or "Entry"

    def _discover_table_columns(self, entry_tuple: tuple[int, ...]) -> list[tuple[str, str, int]]:
        columns: list[tuple[str, str, int]] = []
        entry_len = len(entry_tuple)
        for name, oid_t in self.oids_data.items():
            if oid_t[:entry_len] == entry_tuple and len(oid_t) == entry_len + 1:
                columns.append((name, ".".join(str(x) for x in oid_t), oid_t[-1]))
        columns.sort(key=lambda x: x[2])
        return columns

    def _load_table_schema_with_fallback(
        self,
        oid_str: str,
        first_col_oid: str,
    ) -> tuple[dict[str, Any], list[Any], list[str]]:
        schema: dict[str, Any] = {}
        index_columns: list[str] = []
        try:
            resp = requests.get(f"{self.api_url}/table-schema", params={"oid": oid_str}, timeout=5)
            if resp.status_code == 200:
                schema = resp.json()
                instances = list(schema.get("instances", []))
                index_columns = list(schema.get("index_columns", []))
                if not index_columns:
                    index_columns = ["__index__"]
                self._log(
                    f"Loaded {len(instances)} instances from table schema for {oid_str}: "
                    f"instances={instances}, index_columns={index_columns}",
                    "DEBUG",
                )
                return schema, instances, index_columns

            self._log("Failed to get table schema, using fallback discovery", "WARNING")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error loading table schema: {e}, using fallback discovery", "WARNING")

        return schema, self._discover_instances_fallback(first_col_oid), index_columns

    @staticmethod
    def _table_instance_sort_key(inst: Any) -> list[tuple[int, Any]]:
        parts = str(inst).split(".")
        return [(0, int(part)) if part.isdigit() else (1, part) for part in parts]

    def _compute_table_column_widths(
        self,
        col_names: list[str],
        preserved_widths: dict[str, int],
    ) -> tuple[int, int]:
        if preserved_widths:
            return preserved_widths.get("index", 100), 150

        try:
            available_width = self.table_tree.winfo_width()
            if available_width <= 1:
                available_width = 800
            available_width -= 20
            index_width = max(120, int(available_width * 0.15))
            remaining_width = available_width - index_width
            col_width = max(100, int(remaining_width / len(col_names))) if col_names else 150
            return index_width, col_width
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return 120, 150

    def _configure_table_columns(
        self,
        *,
        col_names: list[str],
        index_columns: list[str],
        preserved_widths: dict[str, int],
    ) -> None:
        self.table_tree["columns"] = ("index", *tuple(col_names))
        index_header = "__Index__" if index_columns == ["__index__"] else "Index"
        self.table_tree.heading("index", text=index_header)

        index_width, col_width = self._compute_table_column_widths(col_names, preserved_widths)
        self.table_tree.column("index", width=index_width, minwidth=50, stretch=False, anchor="w")

        index_column_set = {name.lower() for name in index_columns}
        for i, col_name in enumerate(col_names):
            header_text = f"🔑 {col_name}" if col_name.lower() in index_column_set else col_name
            self.table_tree.heading(col_name, text=header_text)
            width = preserved_widths.get(col_name, 150) if preserved_widths else col_width
            self.table_tree.column(
                col_name,
                width=width,
                minwidth=100,
                stretch=i == len(col_names) - 1,
                anchor="w",
            )

    def _fetch_table_cell_value(self, full_oid: str) -> Any:
        try:
            resp = requests.get(
                f"{self.api_url}/value",
                params={"oid": full_oid},
                timeout=1,
            )
            if resp.status_code == 200:
                return resp.json().get("value", "unset")
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return "unset"
        return "unset"

    def _decorate_enum_display(self, col_oid: str, value: Any) -> Any:
        if value in ("unset", "N/A", ""):
            return value
        col_metadata = self.oid_metadata.get(col_oid, {})
        enums = col_metadata.get("enums")
        if not enums:
            return value
        try:
            int_value = int(value)
            for enum_name, enum_value in enums.items():
                if enum_value == int_value:
                    return f"{value} ({enum_name})"
        except (ValueError, TypeError):
            return value
        return value

    def _populate_table_rows(
        self,
        instances: list[Any],
        columns: list[tuple[str, str, int]],
        index_columns: list[str],
        schema: dict[str, Any],
    ) -> list[tuple[Any, str]]:
        row_items: list[tuple[Any, str]] = []
        index_column_set = {name.lower() for name in index_columns}
        columns_meta = schema.get("columns", {})

        for inst in instances:
            inst_str = str(inst)
            values: list[Any] = [inst]
            index_values = self._extract_index_values(inst_str, index_columns, columns_meta)
            for name, col_oid, _col_num in columns:
                if name.lower() in index_column_set:
                    values.append(index_values.get(name, inst_str))
                    continue

                full_oid = f"{col_oid}.{inst_str}"
                raw_value = self._fetch_table_cell_value(full_oid)
                values.append(self._decorate_enum_display(col_oid, raw_value))

            item = self.table_tree.insert("", "end", values=values)
            row_items.append((inst, item))

        return row_items

    def _restore_table_selection_or_scroll(
        self,
        *,
        row_items: list[tuple[Any, str]],
        selected_instance: str | None,
        preserved_yview: tuple[float, float] | None,
        table_oid: str,
    ) -> None:
        if selected_instance:
            for inst, item in row_items:
                if inst == selected_instance:
                    self.table_tree.selection_set(item)
                    self.table_tree.see(item)
                    self.remove_instance_btn.configure(state="normal")
                    self._set_pending_oid_focus(table_oid, str(selected_instance))
                    return

        if preserved_yview is not None:
            self.table_tree.yview_moveto(preserved_yview[0])

    def _update_add_index_button_state(self, index_columns: list[str]) -> None:
        is_no_index_table = (
            all(col.startswith("__index") for col in index_columns) if index_columns else True
        )
        self.add_index_col_btn.configure(state="normal" if is_no_index_table else "disabled")

    def _discover_instances_fallback(self, first_col_oid: str) -> list[str]:
        """Fallback method to discover table instances by trying sequential indexes.

        This is used when the table-schema API doesn't return instances.
        Only works for simple single-index tables.
        """
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
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self._log(f"Error loading instance {index}: {e}", "DEBUG")
                break

        if len(instances) == max_attempts:
            self._log("Reached maximum attempts while discovering instances", "WARNING")

        return instances

    def _resolve_table_item_for_add_instance(self) -> str | None:
        try:
            selected_items = self.oid_tree.selection()
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Error getting selected item: {e}")
            return None

        if not selected_items:
            selected_items = ()

        for item in selected_items:
            if "table" in self.oid_tree.item(item, "tags"):
                return str(item)
            if "table-entry" in self.oid_tree.item(item, "tags"):
                parent = self.oid_tree.parent(item)
                if parent and "table" in self.oid_tree.item(parent, "tags"):
                    return str(parent)
            if "table-column" in self.oid_tree.item(item, "tags"):
                parent = self.oid_tree.parent(item)
                if parent and "table-entry" in self.oid_tree.item(parent, "tags"):
                    table_parent = self.oid_tree.parent(parent)
                    if table_parent and "table" in self.oid_tree.item(table_parent, "tags"):
                        return str(table_parent)

        return cast("str | None", getattr(self, "_current_table_item", None))

    def _fetch_table_schema_for_oid(self, table_oid: str) -> dict[str, Any] | None:
        try:
            resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": table_oid},
                timeout=5,
            )
            if resp.status_code != 200:
                messagebox.showerror("Error", "Failed to get table schema")
                return None
            return cast("dict[str, Any]", resp.json())
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to get schema: {e}")
            return None

    def _collect_non_index_defaults(
        self,
        schema: dict[str, Any],
        index_column_names: list[str],
    ) -> dict[str, str]:
        instances = schema.get("instances", [])
        columns_meta = cast("dict[str, dict[str, Any]]", schema.get("columns", {}))
        column_defaults: dict[str, str] = {}

        if instances:
            last_instance = instances[-1]
            for col_name, col_info in columns_meta.items():
                if col_name in index_column_names:
                    continue

                col_oid = ".".join(str(x) for x in col_info["oid"])
                full_oid = f"{col_oid}.{last_instance}"
                try:
                    resp = requests.get(
                        f"{self.api_url}/value",
                        params={"oid": full_oid},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        value_data = resp.json()
                        column_defaults[col_name] = str(value_data.get("value", "unset"))
                    else:
                        column_defaults[col_name] = "unset"
                except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                    self._log(f"Could not fetch value for {col_name}: {e}", "WARNING")
                    column_defaults[col_name] = "unset"
            return column_defaults

        for col_name in columns_meta:
            if col_name not in index_column_names:
                column_defaults[col_name] = "unset"
        return column_defaults

    def _submit_add_instance(
        self,
        table_item: str,
        table_oid: str,
        index_columns: list[tuple[str, dict[str, Any]]],
        num_index_parts: int,
        entries: dict[str, ctk.CTkEntry],
        column_defaults: dict[str, str],
        dialog: ctk.CTkToplevel,
    ) -> None:
        index_values: dict[str, str] = {}
        index_parts_ordered: list[str] = []
        for col_name, _col_info in index_columns[:num_index_parts]:
            if col_name not in entries:
                continue
            val = entries[col_name].get().strip()
            if not val:
                messagebox.showerror("Error", f"{col_name} cannot be empty")
                return
            index_values[col_name] = val
            index_parts_ordered.append(val)

        try:
            payload = {
                "table_oid": table_oid,
                "index_values": index_values,
                "column_values": column_defaults,
            }
            resp = requests.post(f"{self.api_url}/table-row", json=payload, timeout=5)
            if resp.status_code == 200:
                result = resp.json()
                messagebox.showinfo(
                    "Success",
                    f"Instance added successfully: {result.get('instance_oid')}",
                )
                self._populate_table_view(table_item)
                instance_str = ".".join(index_parts_ordered)
                self._add_instance_to_oid_tree(table_item, instance_str)
                dialog.destroy()
            else:
                messagebox.showerror("Error", f"Failed to add instance: {resp.text}")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to add instance: {e}")

    def _show_add_instance_dialog(
        self,
        table_item: str,
        table_oid: str,
        schema: dict[str, Any],
        index_columns: list[tuple[str, dict[str, Any]]],
        column_defaults: dict[str, str],
    ) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Add Table Instance")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        title_label = ctk.CTkLabel(
            dialog,
            text=f"Add instance to {schema.get('name', table_oid)}",
            font=("", 14, "bold"),
        )
        title_label.pack(pady=10)

        input_frame = ctk.CTkFrame(dialog)
        input_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        entries: dict[str, ctk.CTkEntry] = {}
        index_field_widgets: list[list[Any]] = []
        dialog_state: dict[str, Any] = {
            "num_index_parts": len(index_columns) if index_columns else 1
        }

        def render_index_fields() -> None:
            self._render_add_instance_index_fields(
                input_frame=input_frame,
                index_field_widgets=index_field_widgets,
                entries=entries,
                index_columns=index_columns,
                num_index_parts=int(dialog_state["num_index_parts"]),
                next_default=self._get_next_add_instance_default(schema),
                add_command=add_index_part,
                remove_command=remove_index_part,
            )

        def add_index_part() -> None:
            dialog_state["num_index_parts"] = int(dialog_state["num_index_parts"]) + 1
            render_index_fields()

        def remove_index_part() -> None:
            dialog_state["num_index_parts"] = max(1, int(dialog_state["num_index_parts"]) - 1)
            render_index_fields()

        render_index_fields()

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_cancel() -> None:
            dialog.destroy()

        def on_add() -> None:
            self._submit_add_instance(
                table_item=table_item,
                table_oid=table_oid,
                index_columns=index_columns,
                num_index_parts=int(dialog_state["num_index_parts"]),
                entries=entries,
                column_defaults=column_defaults,
                dialog=dialog,
            )

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = ctk.CTkButton(button_frame, text="Add", command=on_add)
        add_btn.pack(side="right")

    def _add_instance(self) -> None:
        """Add a new instance to the current table."""
        table_item = self._resolve_table_item_for_add_instance()
        if not table_item:
            messagebox.showwarning("No Table Selected", "Select a table or table entry first.")
            return

        table_oid = self.oid_tree.set(table_item, "oid")
        if not table_oid:
            return

        schema = self._fetch_table_schema_for_oid(table_oid)
        if not schema:
            return

        index_columns: list[tuple[str, dict[str, Any]]] = []
        for col_name in schema.get("index_columns", []):
            if col_name in schema.get("columns", {}):
                col_info = schema["columns"][col_name]
                index_columns.append((col_name, col_info))

        index_from = schema.get("index_from", [])
        if index_from:
            parent_info = index_from[0] if index_from else {}
            parent_mib = parent_info.get("mib", "Unknown MIB")
            parent_col = parent_info.get("column", "Unknown")
            messagebox.showerror(
                "Cannot Add to Augmented Table",
                f"This table (indexed by {parent_col}) is an augmented table "
                f"that inherits instances from {parent_mib}.\n\n"
                "You cannot add instances directly to this table. Instead, "
                f"add instances to the parent table in {parent_mib}, and the "
                "new instances will automatically appear here.",
            )
            return

        if not index_columns:
            messagebox.showerror("Error", "Table has no index columns in schema")
            return

        index_column_names = [name for name, _ in index_columns]
        column_defaults = self._collect_non_index_defaults(schema, index_column_names)
        self._show_add_instance_dialog(
            table_item=table_item,
            table_oid=table_oid,
            schema=schema,
            index_columns=index_columns,
            column_defaults=column_defaults,
        )

    def _add_index_column(self) -> None:
        """Add an extra index column to a no-index table by recreating all instances."""
        table_item = getattr(self, "_current_table_item", None)
        if not table_item:
            messagebox.showwarning("No Table Selected", "Select a table first.")
            return

        table_oid = self.oid_tree.set(table_item, "oid")
        if not table_oid:
            return

        schema = self._load_table_schema_for_index_column(str(table_oid))
        if schema is None:
            return

        instances = schema.get("instances", [])
        if not instances:
            messagebox.showinfo(
                "No Instances",
                "Table has no instances. Add instances first, then add more index columns.",
            )
            return

        index_columns = schema.get("index_columns", [])
        columns_meta = schema.get("columns", {})
        current_parts = len(index_columns) if index_columns else 1

        self._open_add_index_column_dialog(
            table_item=table_item,
            table_oid=str(table_oid),
            instances=instances,
            columns_meta=columns_meta,
            current_parts=current_parts,
        )

    def _load_table_schema_for_index_column(self, table_oid: str) -> dict[str, Any] | None:
        try:
            resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": table_oid},
                timeout=5,
            )
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to get schema: {e}")
            return None

        if resp.status_code != 200:
            messagebox.showerror("Error", "Failed to get table schema")
            return None
        return cast("dict[str, Any]", resp.json())

    def _open_add_index_column_dialog(
        self,
        table_item: str,
        table_oid: str,
        instances: list[Any],
        columns_meta: dict[str, Any],
        current_parts: int,
    ) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Add Index Column")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Add index part #{current_parts + 1}",
            font=("", 14, "bold"),
        ).pack(pady=10)
        ctk.CTkLabel(
            dialog,
            text=f"This will recreate all {len(instances)} instances\nwith an extra index part.",
            font=("", 11),
        ).pack(pady=5)

        input_frame = ctk.CTkFrame(dialog)
        input_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(input_frame, text="Default value for new index part:").pack(
            side="left",
            padx=(0, 10),
        )
        default_entry = ctk.CTkEntry(input_frame, width=100)
        default_entry.insert(0, "1")
        default_entry.pack(side="left")

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_cancel() -> None:
            dialog.destroy()

        def on_add_column() -> None:
            default_val = default_entry.get().strip()
            if not default_val:
                messagebox.showerror("Error", "Default value cannot be empty")
                return

            dialog.destroy()
            success_count, fail_count = self._rebuild_instances_with_extra_index(
                table_oid=table_oid,
                instances=instances,
                columns_meta=columns_meta,
                current_parts=current_parts,
                default_val=default_val,
            )
            self._show_add_index_column_result(
                table_item=table_item,
                success_count=success_count,
                fail_count=fail_count,
            )

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = ctk.CTkButton(
            button_frame,
            text="Add Column",
            command=on_add_column,
            fg_color="green",
            hover_color="darkgreen",
        )
        add_btn.pack(side="right")

    def _build_current_index_values(self, instance: Any) -> dict[str, str]:
        current_index_parts = str(instance).split(".")
        index_values: dict[str, str] = {}
        for i, part in enumerate(current_index_parts):
            col_name = "__index__" if i == 0 else f"__index_{i + 1}__"
            index_values[col_name] = part
        return index_values

    def _load_column_values_for_instance(
        self,
        instance: Any,
        columns_meta: dict[str, Any],
    ) -> dict[str, str]:
        column_values: dict[str, str] = {}
        for col_name, col_info in columns_meta.items():
            if col_name.startswith("__index"):
                continue
            col_oid = ".".join(str(x) for x in col_info["oid"])
            full_oid = f"{col_oid}.{instance}"
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": full_oid},
                    timeout=5,
                )
                if resp.status_code == 200:
                    value_data = resp.json()
                    column_values[col_name] = str(value_data.get("value", ""))
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
        return column_values

    def _delete_table_row(
        self,
        table_oid: str,
        index_values: dict[str, str],
        instance: Any,
    ) -> bool:
        del_payload = {
            "table_oid": table_oid,
            "index_values": index_values,
        }
        resp = requests.delete(f"{self.api_url}/table-row", json=del_payload, timeout=5)
        if resp.status_code == 200:
            return True
        self._log(f"Failed to delete instance {instance}: {resp.text}", "WARNING")
        return False

    def _create_table_row_with_new_index(
        self,
        table_oid: str,
        current_index_values: dict[str, str],
        column_values: dict[str, str],
        current_parts: int,
        default_val: str,
        instance: Any,
    ) -> bool:
        new_index_values = current_index_values.copy()
        new_col_name = f"__index_{current_parts + 1}__" if current_parts > 0 else "__index_2__"
        new_index_values[new_col_name] = default_val

        create_payload = {
            "table_oid": table_oid,
            "index_values": new_index_values,
            "column_values": column_values,
        }
        resp = requests.post(
            f"{self.api_url}/table-row",
            json=create_payload,
            timeout=5,
        )
        if resp.status_code == 200:
            return True
        self._log(f"Failed to recreate instance {instance}: {resp.text}", "WARNING")
        return False

    def _rebuild_single_instance_with_new_index(
        self,
        table_oid: str,
        instance: Any,
        columns_meta: dict[str, Any],
        current_parts: int,
        default_val: str,
    ) -> bool:
        current_index_values = self._build_current_index_values(instance)
        column_values = self._load_column_values_for_instance(instance, columns_meta)

        if not self._delete_table_row(table_oid, current_index_values, instance):
            return False
        return self._create_table_row_with_new_index(
            table_oid=table_oid,
            current_index_values=current_index_values,
            column_values=column_values,
            current_parts=current_parts,
            default_val=default_val,
            instance=instance,
        )

    def _rebuild_instances_with_extra_index(
        self,
        table_oid: str,
        instances: list[Any],
        columns_meta: dict[str, Any],
        current_parts: int,
        default_val: str,
    ) -> tuple[int, int]:
        success_count = 0
        fail_count = 0
        for instance in instances:
            try:
                if self._rebuild_single_instance_with_new_index(
                    table_oid=table_oid,
                    instance=instance,
                    columns_meta=columns_meta,
                    current_parts=current_parts,
                    default_val=default_val,
                ):
                    success_count += 1
                else:
                    fail_count += 1
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self._log(f"Error processing instance {instance}: {e}", "ERROR")
                fail_count += 1
        return success_count, fail_count

    def _show_add_index_column_result(
        self,
        table_item: str,
        success_count: int,
        fail_count: int,
    ) -> None:
        if fail_count == 0:
            messagebox.showinfo("Success", f"Added index column to {success_count} instances")
        else:
            messagebox.showwarning(
                "Partial Success",
                f"Updated {success_count} instances, {fail_count} failed",
            )

        self._populate_table_view(table_item)
        self._populate_oid_tree()

    def _get_selected_rows_for_removal(self) -> tuple[str, ...]:
        selected_rows = self.table_tree.selection()
        if not selected_rows:
            messagebox.showwarning("No Selection", "Please select an instance to remove.")
        return cast("tuple[str, ...]", selected_rows)

    def _get_current_table_oid_for_removal(self) -> str | None:
        if not hasattr(self, "_current_table_item") or self._current_table_item is None:
            messagebox.showerror("Error", "No table selected")
            return None

        try:
            raw_table_oid = self.oid_tree.set(self._current_table_item, "oid")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Could not get table OID: {e}")
            return None

        table_oid = str(raw_table_oid) if raw_table_oid else ""

        if not table_oid:
            messagebox.showerror("Error", "Table OID not found")
            return None
        return table_oid

    def _warn_if_augmented_table_for_removal(self, table_oid: str) -> bool:
        try:
            resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": table_oid},
                timeout=5,
            )
            if resp.status_code != 200:
                return False

            schema = resp.json()
            index_from = schema.get("index_from", [])
            if not index_from:
                return False

            parent_info = index_from[0] if index_from else {}
            parent_mib = parent_info.get("mib", "Unknown MIB")
            parent_col = parent_info.get("column", "Unknown")
            messagebox.showerror(
                "Cannot Remove from Augmented Table",
                f"This table (indexed by {parent_col}) is an augmented "
                f"table that inherits instances from {parent_mib}.\n\n"
                "You cannot remove instances from this table. Instead, "
                f"remove instances from the parent table in {parent_mib}, "
                "and the instances will automatically be removed from here.",
            )
            return True
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error checking if table is augmented: {e}", "WARNING")
            return False

    def _confirm_instance_deletion(self, count: int) -> bool:
        if count == 1:
            msg = "Are you sure you want to delete this instance?"
        else:
            msg = f"Are you sure you want to delete {count} instances?"
        return bool(messagebox.askyesno("Confirm Deletion", msg))

    def _delete_selected_row_instance(self, selected_item: str, table_oid: str) -> bool:
        values = self.table_tree.item(selected_item, "values")
        if not values:
            return False

        instance_str = values[0]
        index_columns = getattr(self, "_current_index_columns", [])
        columns_meta = getattr(self, "_current_columns_meta", {})
        index_values = self._extract_index_values(instance_str, index_columns, columns_meta)

        payload = {"table_oid": table_oid, "index_values": index_values}
        resp = requests.delete(f"{self.api_url}/table-row", json=payload, timeout=5)
        if resp.status_code != 200:
            self._log(f"Failed to delete instance {instance_str}: {resp.text}", "ERROR")
            return False

        self._log(f"Deleted instance: {instance_str}", "INFO")
        if self._current_table_item:
            self._remove_instance_from_oid_tree(self._current_table_item, instance_str)
        return True

    def _delete_selected_instances(
        self,
        selected_rows: tuple[str, ...],
        table_oid: str,
    ) -> tuple[int, int]:
        deleted_count = 0
        failed_count = 0
        for selected_item in selected_rows:
            try:
                if self._delete_selected_row_instance(selected_item, table_oid):
                    deleted_count += 1
                else:
                    failed_count += 1
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                failed_count += 1
                self._log(f"Error deleting instance: {e}", "ERROR")
        return deleted_count, failed_count

    def _show_remove_instance_result(self, deleted_count: int, failed_count: int) -> None:
        if deleted_count > 0:
            messagebox.showinfo("Success", f"Deleted {deleted_count} instance(s)")
            if self._current_table_item is not None:
                self._populate_table_view(self._current_table_item)

        if failed_count > 0:
            messagebox.showwarning(
                "Partial Failure",
                f"Failed to delete {failed_count} instance(s)",
            )

    def _remove_instance(self) -> None:
        """Remove the selected instance from the table."""
        try:
            selected_rows = self._get_selected_rows_for_removal()
            if not selected_rows:
                return

            table_oid = self._get_current_table_oid_for_removal()
            if not table_oid:
                return

            if self._warn_if_augmented_table_for_removal(table_oid):
                return

            if not self._confirm_instance_deletion(len(selected_rows)):
                return

            deleted_count, failed_count = self._delete_selected_instances(selected_rows, table_oid)
            self._show_remove_instance_result(deleted_count, failed_count)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Error removing instance: {e}")
            self._log(f"Error in _remove_instance: {e}", "ERROR")
