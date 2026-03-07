"""Table editing mixin for SNMP controller GUI."""

# ruff: noqa: ANN401,ARG005,D401,PLR0915,PLR2004

from __future__ import annotations

import traceback
from tkinter import messagebox
from typing import Any

import requests


class SNMPGuiTableEditMixin:
    """Mixin containing table-row selection and in-place edit logic."""

    table_tree: Any
    remove_instance_btn: Any
    root: Any
    edit_overlay_frame: Any
    edit_overlay_entry: Any
    edit_overlay_combo: Any
    editing_item: str | None
    editing_column: str | None
    editing_oid: str | None
    _saving_cell: bool
    _combo_just_selected: bool
    oid_metadata: dict[str, dict[str, Any]]
    oid_values: dict[str, str]
    api_url: str
    _current_table_columns: list[tuple[str, str, int]]
    _current_table_item: str

    def _log(self, message: str, level: str = "INFO") -> None:
        raise NotImplementedError

    def _set_pending_oid_focus(
        self,
        table_oid: str,
        instance: str | None,
        column_oid: str | None = None,
    ) -> None:
        raise NotImplementedError

    def _extract_index_values(
        self,
        instance: Any,
        index_columns: list[str],
        columns_meta: dict[str, Any],
    ) -> dict[str, str]:
        raise NotImplementedError

    def _remove_instance_from_oid_tree(self, table_item: str, instance: str) -> None:
        raise NotImplementedError

    def _populate_table_view(self, table_item: str, selected_instance: str | None = None) -> None:
        raise NotImplementedError

    def _add_instance_to_oid_tree(self, table_item: str, instance: str) -> None:
        raise NotImplementedError

    def _decorate_enum_display(self, col_oid: str, value: Any) -> Any:
        raise NotImplementedError

    def _refresh_oid_tree_value(self, full_oid: str, display_value: str) -> None:
        raise NotImplementedError

    def _refresh_oid_tree_table(self, table_item: str) -> None:
        raise NotImplementedError

    def _on_table_row_select(self, event: Any) -> None:
        """Handler called when table row selection changes."""
        _ = event
        selected_rows = self.table_tree.selection()
        if selected_rows:
            self.remove_instance_btn.configure(state="normal")
            try:
                selected_values = self.table_tree.item(selected_rows[0], "values")
                if selected_values:
                    instance = str(selected_values[0])
                    table_oid = getattr(self, "_current_table_oid", None)
                    if table_oid:
                        self._set_pending_oid_focus(table_oid, instance)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
        else:
            self.remove_instance_btn.configure(state="disabled")

    def _on_table_double_click(self, event: Any) -> None:
        """Handle double-click on table cell to enable in-place editing."""
        region = self.table_tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item = self.table_tree.identify_row(event.y)
        column = self.table_tree.identify_column(event.x)

        if not item or not column:
            return

        col_num = int(column[1:]) - 1
        if col_num == 0:
            return

        values = self.table_tree.item(item, "values")
        if col_num >= len(values):
            return

        current_value = str(values[col_num])
        self._show_edit_overlay(event, item, column, current_value)

    def _show_edit_overlay(self, event: Any, item: str, column: str, current_value: str) -> None:
        """Show edit overlay at the clicked cell location."""
        _ = event
        self._hide_edit_overlay()

        bbox = self.table_tree.bbox(item, column)
        if not bbox:
            return

        cell_x, cell_y, cell_width, cell_height = bbox

        tree_rootx = self.table_tree.winfo_rootx()
        tree_rooty = self.table_tree.winfo_rooty()

        root_rootx = self.root.winfo_rootx()
        root_rooty = self.root.winfo_rooty()

        overlay_x = tree_rootx + cell_x - root_rootx
        overlay_y = tree_rooty + cell_y - root_rooty

        self.editing_item = item
        self.editing_column = column

        self.edit_overlay_frame.place(
            x=overlay_x,
            y=overlay_y,
            width=cell_width,
            height=cell_height,
        )
        self.edit_overlay_frame.lift()

        enum_values: list[str] = []
        if hasattr(self, "_current_table_columns"):
            col_num = int(column[1:]) - 1
            data_col_index = col_num - 1
            columns = self._current_table_columns
            if 0 <= data_col_index < len(columns):
                _col_name, col_oid, _ = columns[data_col_index]
                metadata = self.oid_metadata.get(col_oid, {})
                enums = metadata.get("enums", {})
                if enums:
                    enum_values = [
                        f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])
                    ]

        if enum_values:
            self.edit_overlay_entry.pack_forget()
            self.edit_overlay_combo.pack(padx=2, pady=2, fill="both", expand=True)

            self.edit_overlay_combo.config(values=enum_values, state="readonly")
            for enum_val in enum_values:
                if enum_val.startswith(current_value.split(maxsplit=1)[0]):
                    self.edit_overlay_combo.set(enum_val)
                    break

            self.edit_overlay_combo.unbind("<Return>")
            self.edit_overlay_combo.unbind("<Escape>")
            self.edit_overlay_combo.unbind("<<ComboboxSelected>>")
            self.edit_overlay_combo.unbind("<FocusOut>")

            self.edit_overlay_combo.bind("<Return>", lambda e: self._save_cell_edit())
            self.edit_overlay_combo.bind("<Escape>", lambda e: self._hide_edit_overlay())
            self.edit_overlay_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self._on_combo_selected(),
            )
            self.edit_overlay_combo.bind("<FocusOut>", lambda e: self._on_edit_focus_out())

            self.edit_overlay_combo.focus()
        else:
            self.edit_overlay_combo.pack_forget()
            self.edit_overlay_entry.pack(padx=2, pady=2, fill="both", expand=True)

            self.edit_overlay_entry.delete(0, "end")
            self.edit_overlay_entry.insert(0, current_value)
            self.edit_overlay_entry.selection_range(0, "end")

            self.edit_overlay_entry.unbind("<Return>")
            self.edit_overlay_entry.unbind("<Escape>")
            self.edit_overlay_entry.unbind("<FocusOut>")

            self.edit_overlay_entry.bind("<Return>", lambda e: self._save_cell_edit())
            self.edit_overlay_entry.bind("<Escape>", lambda e: self._hide_edit_overlay())
            self.edit_overlay_entry.bind("<FocusOut>", lambda e: self._on_edit_focus_out())

            self.edit_overlay_entry.focus()

    def _on_table_click(self, event: Any) -> None:
        """Handle click on table - save edit if clicking outside edit area."""
        if not self.editing_item:
            return
        try:
            widget = event.widget.winfo_containing(event.x_root, event.y_root)
            if widget not in (self.edit_overlay_combo, self.edit_overlay_entry):
                self._save_cell_edit()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

    def _on_table_configure(self, event: Any) -> None:
        """Handle table configuration changes (resize, scroll) - hide edit overlay."""
        _ = event
        if self.editing_item:
            self._save_cell_edit()

    def _on_combo_selected(self) -> None:
        """Handle combobox selection and save immediately."""
        if not self.editing_item:
            return

        self._log("DEBUG: Combo selected - saving immediately", "DEBUG")
        self._save_cell_edit()

    def _on_edit_focus_out(self) -> None:
        """Handle focus leaving edit entry."""
        self._log(
            "DEBUG: Edit focus out event (happens before ComboboxSelected on macOS)",
            "DEBUG",
        )

        if self.editing_item and not hasattr(self, "_combo_just_selected"):
            self._log("DEBUG: FocusOut triggering save for text entry", "DEBUG")
            self.root.after(50, self._save_cell_edit)

    def _hide_edit_overlay(self) -> None:
        """Hide the edit overlay and cancel editing."""
        self._log("DEBUG: _hide_edit_overlay called", "DEBUG")

        self.edit_overlay_frame.place_forget()
        self._log("DEBUG: Overlay frame hidden", "DEBUG")

        self.editing_item = None
        self.editing_column = None
        self.editing_oid = None
        self._log("DEBUG: Editing state cleared", "DEBUG")
        self._log("DEBUG: _hide_edit_overlay complete", "DEBUG")

    def _save_cell_edit(self) -> None:
        """Save the edited cell value."""
        if not self.editing_item or not self.editing_column or self._saving_cell:
            self._log(
                "DEBUG: _save_cell_edit blocked - already saving or no edit active",
                "DEBUG",
            )
            return

        self._saving_cell = True
        self._log("DEBUG: _save_cell_edit STARTED", "DEBUG")

        try:
            editing_item = self.editing_item
            editing_column = self.editing_column

            new_value = self._get_pending_edit_value()

            item_values = self.table_tree.item(editing_item, "values")
            col_num = int(editing_column[1:]) - 1

            self._log(
                f"DEBUG: Saving cell edit - col_num={col_num}, new_value={new_value}",
                "DEBUG",
            )

            if not hasattr(self, "_current_table_columns"):
                self._log("ERROR: _current_table_columns not found", "ERROR")
                return

            columns = self._current_table_columns
            data_col_index = col_num - 1

            if data_col_index < 0 or data_col_index >= len(columns):
                self._log(
                    f"ERROR: data_col_index {data_col_index} out of bounds "
                    f"(columns len={len(columns)})",
                    "ERROR",
                )
                messagebox.showerror("Error", "Column index out of bounds")
                return

            col_name, col_oid, _ = columns[data_col_index]
            instance_index = item_values[0]

            index_columns = getattr(self, "_current_index_columns", [])
            columns_meta = getattr(self, "_current_columns_meta", {})
            table_oid = getattr(self, "_current_table_oid", None)

            if col_name in index_columns:
                self._save_index_cell_edit(
                    col_name=col_name,
                    col_oid=col_oid,
                    col_num=col_num,
                    new_value=new_value,
                    item_values=item_values,
                    instance_index=instance_index,
                    index_columns=index_columns,
                    columns_meta=columns_meta,
                    table_oid=table_oid,
                    columns=columns,
                )
            else:
                self._save_non_index_cell_edit(
                    editing_item=editing_item,
                    col_name=col_name,
                    col_oid=col_oid,
                    col_num=col_num,
                    new_value=new_value,
                    item_values=item_values,
                    instance_index=instance_index,
                    index_columns=index_columns,
                    columns_meta=columns_meta,
                    table_oid=table_oid,
                    columns=columns,
                )
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Failed to save cell: {e}"
            self._log(error_msg, "ERROR")
            traceback.print_exc()
            messagebox.showerror("Error", error_msg)
        finally:
            self._log("DEBUG: Entering finally block - clearing flag", "DEBUG")
            self._saving_cell = False
            self._combo_just_selected = False
            self.root.after(150, self._hide_edit_overlay)
            self._log("DEBUG: finally block complete, hide deferred 150ms", "DEBUG")

    @staticmethod
    def _strip_enum_suffix(value: str) -> str:
        if " (" in value and value.endswith(")"):
            return value.split(" (", maxsplit=1)[0]
        return value

    def _get_pending_edit_value(self) -> str:
        if self.edit_overlay_combo.winfo_ismapped():
            value = self.edit_overlay_combo.get()
            self._log(f"DEBUG: Got value from combo: {value}", "DEBUG")
        else:
            value = self.edit_overlay_entry.get()
            self._log(f"DEBUG: Got value from entry: {value}", "DEBUG")

        stripped = self._strip_enum_suffix(value)
        if stripped != value:
            self._log(f"DEBUG: Parsed enum value: {stripped}", "DEBUG")
        return stripped

    def _build_new_index_values(
        self,
        *,
        columns: list[tuple[str, str, int]],
        index_columns: list[str],
        updated_values: list[Any],
    ) -> dict[str, str]:
        new_index_values: dict[str, str] = {}
        column_names = [c[0] for c in columns]
        for idx_name in index_columns:
            try:
                idx_pos = column_names.index(idx_name)
                new_index_values[idx_name] = str(updated_values[1 + idx_pos])
            except ValueError:
                new_index_values[idx_name] = "unset"
        return new_index_values

    def _collect_non_index_column_values(
        self,
        *,
        columns: list[tuple[str, str, int]],
        index_columns: list[str],
        row_values: list[Any],
    ) -> dict[str, str]:
        column_values: dict[str, str] = {}
        for i, (c_name, _, _) in enumerate(columns):
            if c_name in index_columns:
                continue
            val = str(row_values[1 + i]) if 1 + i < len(row_values) else "unset"
            column_values[c_name] = self._strip_enum_suffix(val)
        return column_values

    def _save_index_cell_edit(
        self,
        *,
        col_name: str,
        col_oid: str,
        col_num: int,
        new_value: str,
        item_values: Any,
        instance_index: Any,
        index_columns: list[str],
        columns_meta: dict[str, Any],
        table_oid: str | None,
        columns: list[tuple[str, str, int]],
    ) -> None:
        if not table_oid:
            messagebox.showerror("Error", "Table OID not available")
            return

        old_index_values: dict[str, str] = self._extract_index_values(
            instance_index,
            index_columns,
            columns_meta,
        )

        updated_values = list(item_values)
        updated_values[col_num] = new_value
        new_index_values = self._build_new_index_values(
            columns=columns,
            index_columns=index_columns,
            updated_values=updated_values,
        )
        column_values = self._collect_non_index_column_values(
            columns=columns,
            index_columns=index_columns,
            row_values=updated_values,
        )

        try:
            self._log("DEBUG: Calling DELETE /table-row for index update", "DEBUG")
            del_resp = requests.delete(
                f"{self.api_url}/table-row",
                json={
                    "table_oid": table_oid,
                    "index_values": old_index_values,
                    "column_values": {},
                },
                timeout=5,
            )
            self._log(f"DEBUG: DELETE response: {del_resp.status_code}", "DEBUG")
            if del_resp.status_code != 200:
                messagebox.showerror("Error", f"Failed to delete old instance: {del_resp.text}")
                return

            old_instance_str = ".".join(str(old_index_values[k]) for k in index_columns)
            if hasattr(self, "_current_table_item") and self._current_table_item:
                self._remove_instance_from_oid_tree(self._current_table_item, old_instance_str)

            self._log("DEBUG: Calling POST /table-row for index update", "DEBUG")
            create_resp = requests.post(
                f"{self.api_url}/table-row",
                json={
                    "table_oid": table_oid,
                    "index_values": new_index_values,
                    "column_values": column_values,
                },
                timeout=5,
            )
            if create_resp.status_code != 200:
                messagebox.showerror("Error", f"Failed to create new instance: {create_resp.text}")
                return

            self._log(
                f"Updated index {col_name} from {old_index_values[col_name]} to {new_value}",
            )
            if hasattr(self, "_current_table_item") and self._current_table_item:
                new_instance = ".".join(
                    str(new_index_values.get(idx_name, "")) for idx_name in index_columns
                )
                self._populate_table_view(self._current_table_item, new_instance)
                self._add_instance_to_oid_tree(self._current_table_item, new_instance)
                self._set_pending_oid_focus(table_oid, new_instance, col_oid)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to update index: {e}")
            self._log(f"Error updating index: {e}", "ERROR")

    def _save_non_index_cell_edit(
        self,
        *,
        editing_item: str,
        col_name: str,
        col_oid: str,
        col_num: int,
        new_value: str,
        item_values: Any,
        instance_index: Any,
        index_columns: list[str],
        columns_meta: dict[str, Any],
        table_oid: str | None,
        columns: list[tuple[str, str, int]],
    ) -> None:
        index_values = self._extract_index_values(instance_index, index_columns, columns_meta)
        updated_row_values = list(item_values)
        updated_row_values[col_num] = new_value
        column_values = self._collect_non_index_column_values(
            columns=columns,
            index_columns=index_columns,
            row_values=updated_row_values,
        )

        full_oid = f"{col_oid}.{instance_index}"
        is_new_instance = full_oid not in self.oid_values

        try:
            self._log(
                "DEBUG: Calling POST /table-row for cell update "
                f"(col={col_name}, val={new_value}, new_instance={is_new_instance})",
                "DEBUG",
            )
            resp = requests.post(
                f"{self.api_url}/table-row",
                json={
                    "table_oid": table_oid,
                    "index_values": index_values,
                    "column_values": column_values,
                },
                timeout=5,
            )
            self._log(f"DEBUG: POST response: {resp.status_code}", "DEBUG")
            if resp.status_code != 200:
                error_msg = f"Failed to update value: {resp.status_code} - {resp.text}"
                self._log(error_msg, "ERROR")
                messagebox.showerror("Error", error_msg)
                return

            self._log("DEBUG: Starting UI update for cell", "DEBUG")
            display_value = self._decorate_enum_display(col_oid, new_value)
            ui_values = list(item_values)
            ui_values[col_num] = display_value
            self.table_tree.item(editing_item, values=ui_values)
            self._log("DEBUG: Cell display updated in treeview", "DEBUG")
            self._log(f"Updated {col_name} (OID {full_oid}) to: {new_value}")
            self.oid_values[full_oid] = new_value
            self._log("DEBUG: Cache updated, cell save complete", "DEBUG")

            self._refresh_oid_tree_value(full_oid, display_value)
            if table_oid:
                self._set_pending_oid_focus(table_oid, str(instance_index), col_oid)

            if (
                is_new_instance
                and hasattr(self, "_current_table_item")
                and self._current_table_item
            ):
                self._log("DEBUG: New instance detected, refreshing OID tree table", "DEBUG")
                self._refresh_oid_tree_table(self._current_table_item)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Failed to update cell via table-row API: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
