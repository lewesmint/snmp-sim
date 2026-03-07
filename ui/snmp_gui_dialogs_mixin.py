"""Dialog-related helper mixin for SNMP GUI."""

from __future__ import annotations

from tkinter import messagebox
from typing import Any

import customtkinter as ctk

# ruff: noqa: ANN401


class SNMPGuiDialogsMixin:
    """Mixin containing UI helper methods for add/edit dialogs."""

    root: Any
    oid_metadata: dict[str, dict[str, Any]]
    oid_tree: Any

    def _toggle_entry_state(self, entry: Any, unlocked: bool) -> None:
        raise NotImplementedError

    def _set_oid_value(self, oid: str, new_value: str, item: str) -> None:
        raise NotImplementedError

    def _get_next_add_instance_default(self, schema: dict[str, Any]) -> str:
        instances = [str(inst) for inst in schema.get("instances", [])]
        if not instances:
            return "1"

        numeric_vals: list[int] = []
        for inst in instances:
            parts = str(inst).split(".")
            if parts and parts[-1].isdigit():
                numeric_vals.append(int(parts[-1]))

        if numeric_vals:
            return str(max(numeric_vals) + 1)
        return "1"

    def _render_add_instance_index_fields(
        self,
        input_frame: Any,
        index_field_widgets: list[list[Any]],
        entries: dict[str, ctk.CTkEntry],
        index_columns: list[tuple[str, dict[str, Any]]],
        num_index_parts: int,
        next_default: str,
        add_command: Any,
        remove_command: Any,
    ) -> None:
        for widget_list in index_field_widgets:
            for widget in widget_list:
                widget.destroy()
        index_field_widgets.clear()
        entries.clear()

        for i in range(num_index_parts):
            col_name = index_columns[i][0] if i < len(index_columns) else f"index{i}"
            label = ctk.CTkLabel(input_frame, text=f"{col_name}:")
            label.grid(row=i, column=0, sticky="w", pady=5, padx=10)

            entry = ctk.CTkEntry(input_frame)
            default_val = next_default if i == num_index_parts - 1 else "1"
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, sticky="ew", pady=5, padx=(0, 10))
            entries[col_name] = entry
            index_field_widgets.append([label, entry])

        button_row = num_index_parts
        add_btn = ctk.CTkButton(input_frame, text="+", width=40, command=add_command)
        add_btn.grid(row=button_row, column=0, pady=5, padx=10, sticky="w")
        remove_btn = ctk.CTkButton(input_frame, text="-", width=40, command=remove_command)
        remove_btn.grid(row=button_row, column=1, pady=5, padx=(0, 10), sticky="w")
        if num_index_parts <= 1:
            remove_btn.configure(state="disabled")

        index_field_widgets.append([add_btn, remove_btn])
        input_frame.columnconfigure(1, weight=1)

    def _resolve_edit_dialog_metadata(self, oid: str) -> tuple[dict[str, Any], str, str]:
        base_oid = (
            oid.split(".")[:-1] if "." in oid and oid.rsplit(".", maxsplit=1)[-1].isdigit() else oid
        )
        base_oid_str = ".".join(base_oid) if isinstance(base_oid, list) else base_oid
        metadata = self.oid_metadata.get(base_oid_str, {})
        value_type = str(metadata.get("type", "Unknown"))
        access = str(metadata.get("access", "read-only")).lower()
        return metadata, value_type, access

    def _is_index_item(self, item: str) -> bool:
        type_from_tree = self.oid_tree.set(item, "type")
        return "[INDEX]" in type_from_tree

    def _create_edit_dialog_shell(
        self,
        oid: str,
        value_type: str,
        current_value: str,
    ) -> tuple[Any, Any]:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Edit OID Value")
        dialog.geometry("450x300")
        dialog.resizable(width=False, height=False)
        dialog.transient(self.root)

        x_pos = self.root.winfo_x() + (self.root.winfo_width() // 2) - 225
        y_pos = self.root.winfo_y() + (self.root.winfo_height() // 2) - 150
        dialog.geometry(f"+{x_pos}+{y_pos}")

        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            main_frame,
            text="Edit OID Value",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(0, 15))

        ctk.CTkLabel(
            main_frame,
            text=f"OID: {oid}\nType: {value_type}",
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            main_frame,
            text=f"Current: {current_value}",
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(
            main_frame,
            text="New value:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w")
        return dialog, main_frame

    def _create_edit_value_widget(
        self,
        main_frame: Any,
        current_value: str,
        enums: dict[str, Any],
    ) -> tuple[Any, Any]:
        value_var = ctk.StringVar(value=current_value)
        if enums:
            enum_values = [
                f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])
            ]
            value_widget = ctk.CTkComboBox(
                main_frame,
                variable=value_var,
                values=enum_values,
                width=400,
                state="readonly",
            )
            for enum_val in enum_values:
                if enum_val.startswith(current_value.split(maxsplit=1)[0]):
                    value_var.set(enum_val)
                    break
        else:
            value_widget = ctk.CTkEntry(main_frame, textvariable=value_var, width=400)

        value_widget.pack(pady=(5, 10), fill="x")
        return value_var, value_widget

    def _create_edit_unlock_row(
        self,
        main_frame: Any,
        show_checkbox: bool,
        unlock_var: Any,
        value_var: Any,
        value_widget: Any,
        original_value: str,
    ) -> tuple[Any, Any]:
        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", pady=(15, 0))

        unlock_checkbox = None
        if show_checkbox:

            def on_checkbox_toggle() -> None:
                unlocked = unlock_var.get()
                if not unlocked:
                    value_var.set(original_value)
                self._toggle_entry_state(value_widget, unlocked)

            unlock_checkbox = ctk.CTkCheckBox(
                bottom_frame,
                text="Unlock for editing",
                variable=unlock_var,
                command=on_checkbox_toggle,
            )
            unlock_checkbox.pack(side="left", anchor="w")
            value_widget.configure(state="disabled")

        return bottom_frame, unlock_checkbox

    def _create_edit_dialog_buttons(
        self,
        bottom_frame: Any,
        on_ok: Any,
        on_cancel: Any,
    ) -> Any:
        button_container = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        button_container.pack(side="right")

        cancel_button = ctk.CTkButton(button_container, text="Cancel", command=on_cancel, width=80)
        cancel_button.pack(side="right", padx=(10, 0))
        del cancel_button

        ok_button = ctk.CTkButton(
            button_container,
            text="OK",
            command=on_ok,
            width=80,
            state="disabled",
        )
        ok_button.pack(side="right")
        return ok_button

    def _handle_edit_dialog_ok(
        self,
        oid: str,
        item: str,
        value_var: Any,
        show_checkbox: bool,
        unlock_var: Any,
        value_changed: Any,
    ) -> None:
        new_value = value_var.get()
        if new_value is None:
            return

        if show_checkbox and not unlock_var.get():
            messagebox.showwarning(
                "Read-Only",
                "Please check 'Unlock for editing' to modify this read-only object.",
            )
            return
        if not value_changed.get():
            messagebox.showinfo("No Change", "Value has not been modified.")
            return

        if " (" in new_value and new_value.endswith(")"):
            new_value = new_value.split(" (")[0]
        self._set_oid_value(oid, new_value, item)

    def _focus_edit_dialog_input(
        self,
        value_widget: Any,
        unlock_checkbox: Any,
        has_enums: bool,
        show_checkbox: bool,
    ) -> None:
        if not show_checkbox:
            value_widget.focus()
            if not has_enums and hasattr(value_widget, "select_range"):
                value_widget.select_range(0, "end")
        elif unlock_checkbox:
            unlock_checkbox.focus()
