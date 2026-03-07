"""OID tree rendering and interaction mixin for SNMP GUI."""

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: ANN401,D101,PLR2004,SLF001

from __future__ import annotations

import contextlib
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import messagebox, ttk
from typing import Any, cast

import customtkinter as ctk
import requests


class SNMPGuiOidTreeMixin:
    def _populate_oid_tree(self) -> None:
        """Populate the OID tree with data."""
        for item in self.oid_tree.get_children():
            self.oid_tree.delete(item)
        self.oid_to_item.clear()

        if self.oids_data:
            root = self.oid_tree.insert("", "end", text="MIB Tree", values=("", "", "", "", "", ""))
            self.oid_tree.item(root, open=True)
            self._build_tree_from_oids(root, self.oids_data)
            self.executor.submit(self._fetch_values_for_node, root)
            system_oid = "1.3.6.1.2.1.1"
            if system_oid in self.oid_to_item:
                self._expand_path_to_item(self.oid_to_item[system_oid])
                self.executor.submit(self._fetch_values_for_node, self.oid_to_item[system_oid])
            self._ensure_tree_column_width()

    def _build_tree_from_oids(self, parent: str, oids: dict[str, tuple[int, ...]]) -> None:
        """Recursively build the tree from OID dict."""
        filtered_oids: dict[str, tuple[int, ...]] = {}
        scalar_instances: dict[tuple[int, ...], str] = {}

        for name, oid_tuple in oids.items():
            if len(oid_tuple) > 0 and oid_tuple[-1] == 0 and ("Inst" in name):
                base_oid = oid_tuple[:-1]
                scalar_instances[base_oid] = name
            else:
                filtered_oids[name] = oid_tuple

        for base_oid, instance_name in scalar_instances.items():
            base_name = instance_name.removesuffix("Inst")
            filtered_oids[base_name] = base_oid

        tree: dict[Any, Any] = {}
        for name, oid_tuple in filtered_oids.items():
            current = tree
            for num in oid_tuple:
                if num not in current:
                    current[num] = {}
                current = current[num]
            current["__name__"] = name
            if oid_tuple in scalar_instances:
                current["__has_instance__"] = True

        self._mark_tables(tree)
        self._insert_tree_nodes(parent, tree, ())

    def _mark_tables(self, tree: dict[Any, Any]) -> None:
        """Mark nodes that are table entries."""
        for key, value in list(tree.items()):
            if key in ("__name__", "__has_instance__", "__is_table__"):
                continue
            if isinstance(value, dict):
                if "__name__" in value and "Table" in value["__name__"]:
                    value["__is_table__"] = True
                self._mark_tables(value)

    def _sorted_tree_children(self, tree: dict[Any, Any]) -> list[tuple[int, dict[Any, Any]]]:
        children: list[tuple[int, dict[Any, Any]]] = []
        for key, value in sorted(tree.items(), key=lambda kv: (isinstance(kv[0], str), str(kv[0]))):
            if key in {"__name__", "__has_instance__"} or not isinstance(key, int):
                continue
            if not isinstance(value, dict):
                continue
            children.append((key, value))
        return children

    def _row_tag_and_next_count(self, row_count: int) -> tuple[str, int]:
        row_tag = "evenrow" if row_count % 2 == 0 else "oddrow"
        return row_tag, row_count + 1

    def _is_leaf_tree_node(self, value: dict[Any, Any]) -> bool:
        child_keys = [k for k in value if k not in ("__name__", "__has_instance__")]
        return len(child_keys) == 0

    def _icon_ref(self, icon_key: str) -> Any:
        if not getattr(self, "oid_icon_images", None):
            return ""
        icon = self.oid_icon_images.get(icon_key)
        return cast("Any", icon) if icon is not None else ""

    def _leaf_base_fields(
        self,
        oid_str: str,
        has_instance: bool,
    ) -> tuple[str, str, Any, str, Any, Any]:
        metadata = self.oid_metadata.get(oid_str, {})
        access = str(metadata.get("access", "")).lower()
        if "write" in access:
            icon_key = "edit"
        elif "read" in access or "not-accessible" in access or "none" in access:
            icon_key = "lock"
        else:
            icon_key = "chart" if has_instance else "doc"

        if has_instance:
            instance_oid_str = oid_str + ".0"
            instance_str = "0"
            val = self.oid_values.get(instance_oid_str, "")
        else:
            instance_str = ""
            val = self.oid_values.get(oid_str, "")

        type_val = metadata.get("type") or "Unknown"
        access_val = metadata.get("access") or "N/A"
        mib_val = metadata.get("mib") or "N/A"
        return icon_key, instance_str, val, type_val, access_val, mib_val

    def _format_leaf_display_value(self, oid_str: str, type_val: str, val: Any) -> tuple[str, Any]:
        if type_val == "Unknown" and not val:
            return "Empty Node", ""

        display_val = val
        metadata = self.oid_metadata.get(oid_str, {})
        enums = metadata.get("enums")
        if enums and val and val not in ("N/A", "unset", ""):
            try:
                int_value = int(val)
                for enum_name, enum_value in enums.items():
                    if enum_value == int_value:
                        display_val = f"{val} ({enum_name})"
                        break
            except (ValueError, TypeError):
                pass
        return type_val, display_val

    def _insert_leaf_tree_node(
        self,
        parent: str,
        key: int,
        value: dict[Any, Any],
        oid_str: str,
        row_tag: str,
    ) -> str:
        stored_name = value.get("__name__")
        has_instance = bool(value.get("__has_instance__", False))
        icon_key, instance_str, val, type_val, access_val, mib_val = self._leaf_base_fields(
            oid_str,
            has_instance,
        )

        display_text = stored_name or str(key)
        if stored_name in [
            "ifIndex",
            "ifStackHigherLayer",
            "ifStackLowerLayer",
            "ifRcvAddressAddress",
        ]:
            type_val += " [INDEX]"

        type_val, display_val = self._format_leaf_display_value(oid_str, type_val, val)

        node = self.oid_tree.insert(
            parent,
            "end",
            text=display_text,
            image=self._icon_ref(icon_key),
            values=(
                oid_str,
                instance_str,
                display_val,
                type_val,
                access_val,
                mib_val,
            ),
            tags=(row_tag,),
        )
        return str(node)

    def _insert_table_tree_node(
        self,
        parent: str,
        key: int,
        value: dict[Any, Any],
        oid_str: str,
        row_tag: str,
    ) -> str:
        display_text = value.get("__name__") or str(key)
        metadata = self.oid_metadata.get(oid_str, {})
        type_val = metadata.get("type") or "branch"
        access_val = metadata.get("access") or ""
        mib_val = metadata.get("mib") or "N/A"

        node = self.oid_tree.insert(
            parent,
            "end",
            text=display_text,
            image=self._icon_ref("table"),
            values=(oid_str, "", "", type_val, access_val, mib_val),
            tags=(row_tag, "table"),
        )

        if hasattr(self, "table_instances_data") and oid_str in self.table_instances_data:
            self._log(
                f"Pre-populating table {oid_str} from table_instances_data",
                "DEBUG",
            )
            self._populate_table_instances_immediate(node, oid_str)
        elif hasattr(self, "table_instances_data"):
            self._log(
                f"Table {oid_str} NOT in table_instances_data "
                f"(have {len(self.table_instances_data)} tables)",
                "DEBUG",
            )
        else:
            self._log(
                f"table_instances_data not loaded yet for table {oid_str}",
                "DEBUG",
            )
        return str(node)

    def _insert_folder_tree_node(
        self,
        parent: str,
        key: int,
        value: dict[Any, Any],
        oid_str: str,
        row_tag: str,
    ) -> str:
        display_text = value.get("__name__") or str(key)
        metadata = self.oid_metadata.get(oid_str, {})
        type_val = metadata.get("type") or "branch"
        access_val = metadata.get("access") or "N/A"
        mib_val = metadata.get("mib") or "N/A"

        node = self.oid_tree.insert(
            parent,
            "end",
            text=display_text,
            image=self._icon_ref("folder"),
            values=(oid_str, "", "", type_val, access_val, mib_val),
            tags=(row_tag,),
        )
        return str(node)

    def _is_table_container_node(self, value: dict[Any, Any], oid_str: str) -> bool:
        return bool(
            value.get("__is_table__")
            and str(self.oid_metadata.get(oid_str, {}).get("type", "")) == "MibTable"
        )

    def _insert_tree_node_by_kind(
        self,
        parent: str,
        key: int,
        value: dict[Any, Any],
        oid_str: str,
        row_tag: str,
        is_leaf: bool,
    ) -> str:
        if is_leaf:
            return self._insert_leaf_tree_node(parent, key, value, oid_str, row_tag)
        if self._is_table_container_node(value, oid_str):
            return self._insert_table_tree_node(parent, key, value, oid_str, row_tag)
        return self._insert_folder_tree_node(parent, key, value, oid_str, row_tag)

    def _insert_tree_nodes(
        self,
        parent: str,
        tree: dict[Any, Any],
        current_oid: tuple[int, ...],
        row_count: int = 0,
    ) -> int:
        """Insert nodes into Treeview recursively.

        Returns the updated row count for alternating row colors.
        """
        for key, value in self._sorted_tree_children(tree):
            new_oid = (*current_oid, key)
            oid_str = ".".join(str(x) for x in new_oid)

            row_tag, row_count = self._row_tag_and_next_count(row_count)
            is_leaf = self._is_leaf_tree_node(value)
            node = self._insert_tree_node_by_kind(
                parent,
                key,
                value,
                oid_str,
                row_tag,
                is_leaf,
            )
            self.oid_to_item[oid_str] = node

            if not is_leaf and not self._is_table_container_node(value, oid_str):
                row_count = self._insert_tree_nodes(node, value, new_oid, row_count)

        return row_count

    def _on_node_open(self, event: Any) -> None:
        """Fetch values when a tree node is expanded."""
        try:
            item = event.widget.focus()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            item = None

        if not item:
            return

        self._ensure_oid_name_width(item)
        self.executor.submit(self._fetch_values_for_node, item)

        tags = self.oid_tree.item(item, "tags")
        if "table" in tags:
            oid_str = self.oid_tree.set(item, "oid")
            if oid_str:
                children = self.oid_tree.get_children(item)
                if not children:
                    self._log(
                        f"Table {oid_str} has no children, discovering instances...",
                        "DEBUG",
                    )
                else:
                    self._log(
                        f"Table {oid_str} has {len(children)} children, "
                        "refreshing to show latest...",
                        "INFO",
                    )
                self.executor.submit(self._discover_table_instances, item, oid_str)

    def _on_double_click(self, event: Any) -> None:
        """Handle tree double-click and allow editing writable values."""
        try:
            item = self.oid_tree.identify_row(event.y)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        if not item:
            return

        children = self.oid_tree.get_children(item)
        if children:
            if self.oid_tree.item(item, "open"):
                self.oid_tree.item(item, open=False)
            else:
                self.oid_tree.item(item, open=True)
            return

        oid_str = self.oid_tree.set(item, "oid")
        instance_str = self.oid_tree.set(item, "instance")

        if not oid_str:
            return

        full_oid = f"{oid_str}.{instance_str}" if instance_str else oid_str
        is_writable = self._is_oid_writable(full_oid)
        current_value = self.oid_tree.set(item, "value")
        self._show_edit_dialog(full_oid, current_value, item, is_writable)

    def _reset_search_state_for_tree_select(self) -> None:
        if self._search_setting_selection:
            return
        self._search_matches.clear()
        self._search_current_index = 0
        self._search_term = ""

    def _hide_table_tab_unless_active(self) -> None:
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            current_tab = self.tabview.get()
            if current_tab == "Table View":
                return
        if "Table View" in self.tabview._tab_dict:
            self.tabview.delete("Table View")

    def _extract_table_context_from_selection(
        self,
        selected_items: tuple[str, ...],
    ) -> tuple[str | None, str | None, str | None]:
        table_item: str | None = None
        table_entry_item: str | None = None
        selected_instance: str | None = None

        for item in selected_items:
            tags = self.oid_tree.item(item, "tags")
            if "table" in tags:
                table_item = item
                break
            if "table-entry" in tags:
                table_entry_item = item
                instance_str = self.oid_tree.set(item, "instance")
                if instance_str:
                    selected_instance = instance_str
                break
            if "table-column" in tags:
                instance_str = self.oid_tree.set(item, "instance")
                if instance_str:
                    selected_instance = instance_str
                parent = self.oid_tree.parent(item)
                if parent and "table-entry" in self.oid_tree.item(parent, "tags"):
                    table_entry_item = parent
                break
        return table_item, table_entry_item, selected_instance

    def _resolve_table_item_from_entry(self, table_entry_item: str | None) -> str | None:
        if not table_entry_item:
            return None
        parent = self.oid_tree.parent(table_entry_item)
        if parent and "table" in self.oid_tree.item(parent, "tags"):
            return str(parent)
        return None

    def _show_table_selection(self, table_item: str, selected_instance: str | None) -> None:
        if "Table View" not in self.tabview._tab_dict:
            self.enable_table_tab()
        table_oid = self.oid_tree.set(table_item, "oid")
        self._log(
            f"Table selection: table_oid={table_oid}, selected_instance={selected_instance}",
            "DEBUG",
        )
        self._populate_table_view(table_item, selected_instance)
        self.add_instance_btn.configure(state="normal")

    def _on_tree_select(self, event: Any) -> None:
        """Handle tree selection changes and populate Table View."""
        del event
        self._reset_search_state_for_tree_select()

        selected_items = self.oid_tree.selection()
        if not selected_items:
            self._hide_table_tab_unless_active()
            self._update_selected_info(None)
            return

        (
            table_item,
            table_entry_item,
            selected_instance,
        ) = self._extract_table_context_from_selection(selected_items)

        self._ensure_oid_name_width(selected_items[0])
        self._update_selected_info(selected_items[0])

        if not table_item and table_entry_item:
            table_item = self._resolve_table_item_from_entry(table_entry_item)

        if table_item:
            self._show_table_selection(table_item, selected_instance)
        else:
            self._hide_table_tab_unless_active()

    def _update_selected_info(self, item: str | None) -> None:
        """Update the toolbar display with OID, value, and type for the selected item."""
        if not item:
            self._set_selected_info_text("")
            return

        oid_str = self.oid_tree.set(item, "oid")
        instance_str = self.oid_tree.set(item, "instance")
        type_str = self.oid_tree.set(item, "type")

        if not oid_str:
            self._set_selected_info_text("")
            return

        full_oid = oid_str
        if instance_str:
            full_oid = f"{oid_str}.{instance_str}"

        value_str = self.oid_tree.set(item, "value")
        if not value_str:
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": full_oid},
                    timeout=2,
                )
                value_str = str(resp.json().get("value", "")) if resp.status_code == 200 else "N/A"
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                value_str = "N/A"

        display = self._format_selected_info(full_oid, type_str, value_str)
        self._set_selected_info_text(display)

    def _ensure_tree_column_width(self) -> None:
        """Scan visible tree items and ensure column #0 is wide enough for all of them."""
        try:
            if getattr(self, "_oid_tree_user_resized", False):
                return

            max_width = int(self.oid_tree.column("#0", "width"))

            def check_item(item: str, depth: int = 0) -> int:
                """Recursively check item and its open children, return max width needed."""
                nonlocal max_width

                text = self.oid_tree.item(item, "text")
                if text:
                    try:
                        font_obj = tkfont.Font(
                            family="Helvetica",
                            size=int(getattr(self, "tree_font_size", 22)),
                        )
                        text_width = font_obj.measure(str(text))
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        text_width = len(text) * 10

                    indent_per_level = 20
                    icon_width = 20
                    padding = 40
                    indentation = depth * indent_per_level + icon_width
                    desired_width = indentation + text_width + padding

                    max_width = max(max_width, desired_width)

                if self.oid_tree.item(item, "open"):
                    for child in self.oid_tree.get_children(item):
                        check_item(child, depth + 1)

                return max_width

            for root_item in self.oid_tree.get_children():
                check_item(root_item, 0)

            current_width = int(self.oid_tree.column("#0", "width"))
            if max_width > current_width:
                self.oid_tree.column("#0", width=max_width)

        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

    def _ensure_oid_name_width(self, item: str) -> None:
        """Ensure the name column is wide enough to display the selected item's text."""
        try:
            if getattr(self, "_oid_tree_user_resized", False):
                return
            text = self.oid_tree.item(item, "text") or ""
            if not text:
                return

            size = getattr(self, "tree_font_size", 22)
            font = tkfont.Font(family="Helvetica", size=size)

            text_width = font.measure(text)

            depth = 0
            parent = self.oid_tree.parent(item)
            while parent:
                depth += 1
                parent = self.oid_tree.parent(parent)

            indent_per_level = 20
            icon_width = 20
            indentation = depth * indent_per_level + icon_width

            padding = 40
            desired_width = indentation + text_width + padding
            current_width = int(self.oid_tree.column("#0", "width"))

            if desired_width > current_width:
                self.oid_tree.column("#0", width=desired_width)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            traceback.print_exc()

    def _on_oid_tree_resize(self, event: tk.Event[tk.Widget]) -> None:
        """Track manual column resizing to avoid auto-expanding the tree column."""
        try:
            region = self.oid_tree.identify_region(event.x, event.y)
            if region == "separator":
                self._oid_tree_user_resized = True
                return
            item = self.oid_tree.identify_row(event.y)
            if item:
                self._ensure_oid_name_width(item)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

    def _adjust_tree_font_size(self, delta: int) -> None:
        """Increase or decrease the tree font size and row height."""
        try:
            size = int(getattr(self, "tree_font_size", 22)) + delta
            size = max(12, min(34, size))
            self.tree_font_size = size
            self.tree_row_height = max(24, size + 8)
            style = ttk.Style()
            style.configure("Treeview", font=("Helvetica", size), rowheight=self.tree_row_height)
            style.configure("Treeview.Heading", font=("Helvetica", size + 1, "bold"))
            self.edit_overlay_combo.configure(font=("Helvetica", max(8, size - 1)))
            self.edit_overlay_entry.configure(font=("Helvetica", max(8, size - 1)))
            self._ensure_oid_name_width(self.oid_tree.focus())
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

    def _format_selected_info(self, full_oid: str, type_str: str, value_str: str) -> str:
        """Format selected item display to match snmpget-like output with enum names."""
        if not full_oid.startswith("."):
            full_oid = "." + full_oid

        enum_display = ""
        base_oid = (
            full_oid.split(".0")[0] if full_oid.endswith(".0") else full_oid.rsplit(".", 1)[0]
        )
        metadata = self.oid_metadata.get(base_oid, {})
        enums = metadata.get("enums")

        if enums and value_str and value_str not in ("N/A", "unset"):
            try:
                int_value = int(value_str)
                for enum_name, enum_value in enums.items():
                    if enum_value == int_value:
                        enum_display = f" ({enum_name})"
                        break
            except (ValueError, TypeError):
                pass

        if type_str:
            return f"{full_oid} = {type_str}: {value_str}{enum_display}"
        return f"{full_oid} = {value_str}{enum_display}"

    def _extract_index_values(
        self,
        instance: str,
        index_columns: list[str],
        columns_meta: dict[str, Any],
    ) -> dict[str, str]:
        """Decode index values from a dotted instance string."""
        if not index_columns:
            return {"__index__": instance or "1"}
        parts = instance.split(".") if instance else []
        values: dict[str, str] = {}
        pos = 0
        for col_name in index_columns:
            if col_name == "__index__":
                values[col_name] = instance or "1"
                continue
            col_info = columns_meta.get(col_name, {}) if columns_meta else {}
            col_type = str(col_info.get("type", "")).lower()
            if col_type == "ipaddress":
                if pos + 4 <= len(parts):
                    values[col_name] = ".".join(parts[pos : pos + 4])
                    pos += 4
                else:
                    values[col_name] = instance
            elif pos < len(parts):
                values[col_name] = parts[pos]
                pos += 1
            else:
                values[col_name] = instance
        return values

    def _build_instance_from_index_values(
        self,
        index_values: dict[str, str],
        index_columns: list[str],
        columns_meta: dict[str, Any],
    ) -> str:
        """Encode index values into a dotted instance string."""
        if not index_columns:
            return str(index_values.get("__index__", "1"))
        parts: list[str] = []
        for col_name in index_columns:
            if col_name == "__index__":
                return str(index_values.get(col_name, "1"))
            col_info = columns_meta.get(col_name, {}) if columns_meta else {}
            col_type = str(col_info.get("type", "")).lower()
            raw_val = str(index_values.get(col_name, ""))
            if col_type == "ipaddress":
                ip_parts = [p for p in raw_val.split(".") if p]
                if len(ip_parts) == 4:
                    parts.extend(ip_parts)
                else:
                    parts.append(raw_val)
            else:
                parts.append(raw_val)
        return ".".join(parts)

    def _set_selected_info_text(self, text: str) -> None:
        """Set the selected info textbox content in a copyable way."""
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            self.selected_info_entry.configure(state="normal")
            self.selected_info_var.set(text)
            self.selected_info_entry.configure(state="readonly")

    def _show_edit_dialog(self, oid: str, current_value: str, item: str, is_writable: bool) -> None:
        """Show a dialog to edit the value of an OID."""
        del is_writable
        metadata, value_type, access = self._resolve_edit_dialog_metadata(oid)

        if self._is_index_item(item):
            messagebox.showinfo("Cannot Edit", "Index/key columns cannot be edited.")
            return

        dialog, main_frame = self._create_edit_dialog_shell(oid, value_type, current_value)
        enums = metadata.get("enums", {})
        value_var, value_widget = self._create_edit_value_widget(main_frame, current_value, enums)

        original_value = current_value
        value_changed = ctk.BooleanVar(value=False)
        show_checkbox = access == "read-only"
        unlock_var = ctk.BooleanVar(value=False)

        bottom_frame, unlock_checkbox = self._create_edit_unlock_row(
            main_frame,
            show_checkbox,
            unlock_var,
            value_var,
            value_widget,
            original_value,
        )

        def on_ok() -> None:
            self._handle_edit_dialog_ok(
                oid=oid,
                item=item,
                value_var=value_var,
                show_checkbox=show_checkbox,
                unlock_var=unlock_var,
                value_changed=value_changed,
            )
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        ok_button = self._create_edit_dialog_buttons(bottom_frame, on_ok, on_cancel)

        def on_value_change(*args: Any) -> None:
            del args
            changed = value_var.get() != original_value
            value_changed.set(changed)
            ok_button.configure(state="normal" if changed else "disabled")

        value_var.trace_add("write", on_value_change)

        self._focus_edit_dialog_input(value_widget, unlock_checkbox, bool(enums), show_checkbox)
        dialog.bind("<Return>", lambda _event: on_ok())
        dialog.bind("<Escape>", lambda _event: on_cancel())

    def _toggle_entry_state(self, entry: Any, unlocked: bool) -> None:
        """Toggle the entry field state based on unlock checkbox."""
        entry.configure(state="normal" if unlocked else "disabled")

    def _decompose_table_oid(self, oid_str: str) -> tuple[str, str, str] | None:
        """Decompose a table OID (1.3.6.1.2.1.2.2.1.7.3) into (table_oid, column_oid, instance).

        For ifTable column OIDs:
        - Instance OID: 1.3.6.1.2.1.2.2.1.7.3 (full column instance)
        - Column OID: 1.3.6.1.2.1.2.2.1.7 (column without instance)
        - Table OID: 1.3.6.1.2.1.2.2 (table without entry and column)
        - Instance: 3

        Returns (table_oid, column_name, instance) or None if not a table column.
        """
        try:
            parts = oid_str.split(".")
            for table_data in self.table_schemas.values():
                table_oid = ".".join(str(x) for x in table_data.get("oid", []))
                entry_oid = ".".join(str(x) for x in table_data.get("entry_oid", []))

                if oid_str.startswith(entry_oid + "."):
                    entry_parts = entry_oid.split(".")
                    num_indices = len(table_data.get("index_columns", []))

                    if len(parts) > len(entry_parts) + num_indices:
                        column_index = int(parts[len(entry_parts)])
                        for col_name, col_data in table_data.get("columns", {}).items():
                            col_oid = ".".join(str(x) for x in col_data.get("oid", []))
                            col_oid_parts = col_oid.split(".")
                            if len(col_oid_parts) > len(entry_parts) and int(
                                col_oid_parts[len(entry_parts)]
                            ) == column_index:
                                instance = ".".join(parts[len(entry_parts) + 1 :])
                                return (table_oid, col_name, instance)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error decomposing table OID {oid_str}: {e}", "DEBUG")

        return None

    def _set_oid_value(self, oid: str, new_value: str, item: str) -> None:
        """Set the value for an OID via the API.

        Handles both scalar OIDs and table column OIDs by routing to appropriate endpoint.
        """
        try:
            self._log(f"Setting value for OID {oid} to: {new_value}")

            resp = requests.post(
                f"{self.api_url}/value",
                json={"oid": oid, "value": new_value},
                timeout=5,
            )
            if resp.status_code == 404:
                decomposed = self._decompose_table_oid(oid)
                if decomposed:
                    table_oid, column_name, instance = decomposed
                    index_cols = []
                    for schema_data in self.table_schemas.values():
                        if (
                            schema_data.get("oid")
                            and ".".join(str(x) for x in schema_data["oid"]) == table_oid
                        ):
                            index_cols = schema_data.get("index_columns", [])
                            break

                    index_values = {}
                    instance_parts = instance.split(".")
                    for i, col_name in enumerate(index_cols):
                        if i < len(instance_parts):
                            index_values[col_name] = instance_parts[i]

                    self._log(
                        f"Trying table-row endpoint: table_oid={table_oid}, "
                        f"index_values={index_values}, column={column_name}",
                    )
                    resp = requests.post(
                        f"{self.api_url}/table-row",
                        json={
                            "table_oid": table_oid,
                            "index_values": index_values,
                            "column_values": {column_name: new_value},
                        },
                        timeout=5,
                    )

            resp.raise_for_status()
            result = resp.json()
            self._log(f"API response: {result}")

            self.oid_values[oid] = new_value

            display_value = new_value
            base_oid = oid.rsplit(".", 1)[0] if "." in oid else oid
            metadata = self.oid_metadata.get(base_oid, {})
            enums = metadata.get("enums")
            if enums and new_value:
                try:
                    int_value = int(new_value)
                    for enum_name, enum_value in enums.items():
                        if enum_value == int_value:
                            display_value = f"{new_value} ({enum_name})"
                            break
                except (ValueError, TypeError):
                    pass

            self.oid_tree.set(item, "value", display_value)

            self._log(f"Successfully set value for OID {oid}")

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to set value for OID {oid}: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Set Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error setting value for OID {oid}: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Set Error", error_msg)

    def _is_oid_writable(self, oid: str) -> bool:
        """Check if an OID is writable based on metadata."""
        base_oid = (
            oid.split(".")[:-1] if "." in oid and oid.rsplit(".", maxsplit=1)[-1].isdigit() else oid
        )
        base_oid_str = ".".join(base_oid) if isinstance(base_oid, list) else base_oid

        metadata = self.oid_metadata.get(base_oid_str, {})
        access = metadata.get("access", "").lower()
        return access in ["read-write", "readwrite", "write-only", "writeonly"]
