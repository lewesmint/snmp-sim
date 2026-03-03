"""Trap metadata, index handling, and override workflows for the SNMP GUI."""

# ruff: noqa: ANN401, ARG005, PLR0915, PLR2004

from __future__ import annotations

import contextlib
import tkinter.font as tkfont
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import requests


class SNMPGuiTrapOverridesMixin:
    """Provide trap details, index selectors, and override persistence logic."""

    root: Any
    connected: bool
    api_url: str
    host_var: Any
    port_var: Any
    trap_var: Any
    trap_dropdown: Any
    send_trap_btn: Any
    send_test_trap_btn: Any
    trap_info_text: Any
    trap_index_var: Any
    trap_index_vars: dict[str, Any]
    trap_index_widgets: list[Any]
    trap_index_frame: Any
    trap_table_col_widths: dict[str, int]
    oid_table_frame: Any
    oid_rows: list[dict[str, Any]]
    oid_metadata: dict[str, dict[str, Any]]
    traps_metadata: dict[str, dict[str, Any]]
    current_trap_overrides: dict[str, Any]
    _loading_trap_overrides: bool
    _trap_override_save_job: Any
    _last_trap_name: str | None
    _last_trap_index: Any
    _trap_index_columns: list[str]
    _trap_index_columns_meta: dict[str, Any]
    _trap_index_parent_table_oid: Any
    _log: Any
    _save_config_locally: Any
    _extract_index_values: Any
    _build_instance_from_index_values: Any

    def _is_index_varbind(self, oid_name: str) -> bool:
        """Check if the given OID name is an index varbind."""
        index_object_names = {
            "ifIndex",
        }

        if "::" in oid_name:
            parts = oid_name.split("::")
            if len(parts) == 2:
                obj_name = parts[1].split(".")[0]
                return obj_name in index_object_names

        return False

    def _is_sysuptime_varbind(self, oid_name: str) -> bool:
        """Check if the given OID name is sysUpTime."""
        if "::" in oid_name:
            parts = oid_name.split("::")
            if len(parts) == 2:
                obj_name = parts[1].split(".")[0]
                return obj_name == "sysUpTime"
        return False

    def _create_oid_table_row(self, oid_name: str, current_value: str = "") -> dict[str, Any]:
        """Create a row in the OID overrides table."""
        row_frame = ctk.CTkFrame(self.oid_table_frame)
        row_frame.pack(fill="x", pady=2)

        col_widths = getattr(self, "trap_table_col_widths", {})
        oid_col_width = col_widths.get("oid", 260)
        current_col_width = col_widths.get("current", 140)
        checkbox_col_width = col_widths.get("checkbox", 30)
        override_col_width = col_widths.get("override", 180)

        row_frame.grid_columnconfigure(0, weight=0, minsize=oid_col_width)
        row_frame.grid_columnconfigure(1, weight=0, minsize=current_col_width)
        row_frame.grid_columnconfigure(2, weight=0, minsize=checkbox_col_width)
        row_frame.grid_columnconfigure(3, weight=0, minsize=override_col_width)

        is_table_oid = False
        base_oid_name = oid_name
        index_part = ""
        if "." in oid_name and oid_name[-1].isdigit():
            parts = oid_name.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                is_table_oid = True
                base_oid_name = parts[0]
                index_part = "." + parts[1]

        plain_name = base_oid_name.split("::", 1)[1] if "::" in base_oid_name else base_oid_name
        is_index = self._is_index_varbind(oid_name) or plain_name in self._trap_index_columns
        is_sysuptime = self._is_sysuptime_varbind(oid_name)

        metadata = self._get_oid_metadata_by_name(base_oid_name)
        enums = metadata.get("enums") or {}
        has_enums = bool(enums)

        raw_display = oid_name.split("::", 1)[1] if "::" in oid_name else oid_name
        display_name = raw_display
        oid_label = ctk.CTkLabel(
            row_frame,
            text=display_name,
            anchor="w",
            font=("", 10),
            width=oid_col_width,
        )
        oid_label.grid(row=0, column=0, padx=(5, 5), sticky="ew")

        current_label = ctk.CTkLabel(
            row_frame,
            text=current_value or "Loading...",
            anchor="w",
            font=("", 10),
            width=current_col_width,
        )
        current_label.grid(row=0, column=1, padx=(0, 5), sticky="ew")

        use_override_var = ctk.BooleanVar(value=False)
        override_value_var = ctk.StringVar(value="")
        override_check = ctk.CTkCheckBox(
            row_frame,
            text="",
            variable=use_override_var,
            width=checkbox_col_width,
        )

        override_entry: Any
        if has_enums and not is_index and not is_sysuptime:
            enum_values = [
                f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])
            ]
            override_entry = ctk.CTkComboBox(
                row_frame,
                variable=override_value_var,
                values=enum_values,
                width=override_col_width,
                font=("", 10),
                state="disabled",
            )
        else:
            override_entry = ctk.CTkEntry(
                row_frame,
                textvariable=override_value_var,
                width=override_col_width,
                font=("", 10),
            )

        def schedule_save_event(*_args: Any) -> None:
            self._schedule_trap_override_save()

        if is_sysuptime:
            sysuptime_label = ctk.CTkLabel(
                row_frame,
                text="(Real-time)",
                width=170,
                anchor="w",
                font=("", 10),
                text_color="#4a9eff",
            )
            sysuptime_label.grid(row=0, column=2, columnspan=2, padx=(0, 5), sticky="w")

            def on_sysuptime_single_click(_: Any) -> None:
                """Refresh sysUpTime value on single click."""
                self._refresh_sysuptime_value(oid_name, current_label)

            def on_sysuptime_double_click(_: Any) -> None:
                """Show notification on double click."""
                messagebox.showinfo(
                    "sysUpTime is Real-time",
                    "sysUpTime reflects the actual agent uptime and cannot be overridden.\n\n"
                    "It is automatically calculated based on how long the "
                    "SNMP agent has been running.\n\n"
                    "Single-click on this row to refresh the current value.",
                )

            for widget in [row_frame, oid_label, current_label, sysuptime_label]:
                widget.bind("<Button-1>", on_sysuptime_single_click)
                widget.bind("<Double-Button-1>", on_sysuptime_double_click)
        elif is_index:
            current_label.configure(text="")
            spacer = ctk.CTkLabel(row_frame, text="", width=checkbox_col_width + override_col_width)
            spacer.grid(row=0, column=2, columnspan=2, padx=(0, 5), sticky="ew")
        else:
            override_check.grid(row=0, column=2, padx=(0, 5))
            override_entry.grid(row=0, column=3, padx=(0, 5), sticky="ew")
            override_entry.configure(state="disabled")

            def on_checkbox_toggle() -> None:
                if use_override_var.get():
                    if not override_value_var.get():
                        current_text = current_label.cget("text") if current_label else ""
                        override_value_var.set(current_text)
                    override_entry.configure(state="readonly" if has_enums else "normal")
                else:
                    override_entry.configure(state="disabled")
                schedule_save_event()

            use_override_var.trace_add("write", lambda *args: on_checkbox_toggle())

            override_value_var.trace_add("write", schedule_save_event)
            if has_enums:
                override_entry.bind("<<ComboboxSelected>>", schedule_save_event)
                override_entry.bind("<FocusOut>", schedule_save_event)
            else:
                override_entry.bind("<KeyRelease>", schedule_save_event)
                override_entry.bind("<FocusOut>", schedule_save_event)

        return {
            "frame": row_frame,
            "oid_label": oid_label,
            "current_label": current_label,
            "use_override_var": use_override_var,
            "override_check": override_check,
            "override_entry": override_entry,
            "override_var": override_value_var,
            "oid_name": oid_name,
            "has_enums": has_enums,
            "is_table_oid": is_table_oid,
            "base_oid_name": base_oid_name,
            "index_part": index_part,
            "is_index": is_index,
            "is_sysuptime": is_sysuptime,
            "is_enum": has_enums,
            "enums": enums,
        }

    def _update_override_labels(self) -> None:
        """Update OID labels in the overrides table with index suffixes when trap index changes."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return

        trap_data = self.traps_metadata.get(trap_name)
        if not trap_data:
            return

        current_index = self._get_selected_trap_index()

        for row in self.oid_rows:
            base_oid_name = row.get("base_oid_name", row["oid_name"])
            if row["is_table_oid"]:
                display_base = (
                    base_oid_name.split("::", 1)[1] if "::" in base_oid_name else base_oid_name
                )
                new_display_name = f"{display_base}.{current_index}"
                row["oid_label"].configure(text=new_display_name)
                row["oid_name"] = base_oid_name + f".{current_index}"

    def _on_trap_index_change(self) -> None:
        """Handle trap index changes by updating labels and refreshing values/overrides."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return

        current_index = self._get_selected_trap_index()
        if self._last_trap_index and self._last_trap_index != current_index:
            self._save_all_overrides_silent(trap_name_override=trap_name)

        self._update_override_labels()
        self._load_trap_overrides(trap_name)
        self._refresh_current_values()
        self._last_trap_index = current_index

    def _schedule_trap_override_save(self) -> None:
        """Debounce trap override saves for immediate persistence."""
        if not self.connected:
            return
        if getattr(self, "_loading_trap_overrides", False):
            return

        job = getattr(self, "_trap_override_save_job", None)
        if job is not None:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                self.root.after_cancel(job)

        self._trap_override_save_job = self.root.after(400, self._save_all_overrides_silent)

    def _clear_oid_table(self) -> None:
        """Clear all rows from the OID overrides table."""
        job = getattr(self, "_trap_override_save_job", None)
        if job is not None:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                self.root.after_cancel(job)
            self._trap_override_save_job = None
        for row in self.oid_rows:
            row["frame"].destroy()
        self.oid_rows.clear()

    def _update_available_oids(self, trap_name: str, trap_data: dict[str, Any]) -> None:
        """Update the available OIDs dropdown and create table for the selected trap."""
        objects = trap_data.get("objects", [])
        oid_list = []
        current_index = self._get_selected_trap_index()
        index_column_set = {col.lower() for col in self._trap_index_columns}
        for obj in objects:
            obj_mib = obj.get("mib", "")
            obj_name = obj.get("name", "")
            if obj_mib and obj_name:
                if self._trap_index_columns and (
                    obj_name.lower() in index_column_set
                    or self._is_index_varbind(f"{obj_mib}::{obj_name}")
                ):
                    continue
                if self._trap_index_columns and current_index:
                    oid_list.append(f"{obj_mib}::{obj_name}.{current_index}")
                else:
                    oid_list.append(f"{obj_mib}::{obj_name}")

        try:
            font = tkfont.Font(family="Helvetica", size=10)
            max_width = self.trap_table_col_widths.get("oid", 260)
            for oid_name in oid_list:
                display_name = oid_name.split("::", 1)[1] if "::" in oid_name else oid_name
                measured = font.measure(display_name) + 20
                max_width = max(max_width, measured)
            self.trap_table_col_widths["oid"] = max_width
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

        self._clear_oid_table()

        for oid_name in oid_list:
            row = self._create_oid_table_row(oid_name)
            self.oid_rows.append(row)

        self._load_trap_overrides(trap_name)
        self._refresh_current_values()

    def _load_trap_overrides(self, trap_name: str) -> None:
        """Load stored overrides for the specified trap and update table."""
        self._loading_trap_overrides = True
        try:
            response = requests.get(f"{self.api_url}/trap-overrides/{trap_name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.current_trap_overrides = data.get("overrides", {})

                for row in self.oid_rows:
                    if row.get("is_sysuptime", False) or row.get("is_index", False):
                        continue

                    oid_name = row["oid_name"]
                    if oid_name in self.current_trap_overrides:
                        saved_entry = self.current_trap_overrides[oid_name]
                        if isinstance(saved_entry, dict):
                            enabled = bool(saved_entry.get("enabled"))
                            override_val = str(saved_entry.get("value", ""))
                        else:
                            enabled = True
                            override_val = str(saved_entry)

                        row["use_override_var"].set(enabled)
                        if row.get("is_enum"):
                            display_val = self._format_enum_display(
                                override_val,
                                row.get("enums", {}),
                            )
                            if row.get("override_var") is not None:
                                row["override_var"].set(display_val)
                            else:
                                row["override_entry"].set(display_val)
                        elif row.get("override_var") is not None:
                            row["override_var"].set(override_val)
                        else:
                            row["override_entry"].delete(0, "end")
                            row["override_entry"].insert(0, override_val)
                    else:
                        row["use_override_var"].set(False)
                        if row.get("is_enum"):
                            if row.get("override_var") is not None:
                                row["override_var"].set("")
                            else:
                                row["override_entry"].set("")
                        elif row.get("override_var") is not None:
                            row["override_var"].set("")
                        else:
                            row["override_entry"].delete(0, "end")
            else:
                self.current_trap_overrides = {}
                for row in self.oid_rows:
                    if row.get("is_sysuptime", False) or row.get("is_index", False):
                        continue
                    row["use_override_var"].set(False)
                    if row.get("is_enum"):
                        row["override_entry"].set("")
                    else:
                        row["override_entry"].delete(0, "end")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            self._log(f"Failed to load trap overrides: {error}", "WARNING")
            self.current_trap_overrides = {}
            for row in self.oid_rows:
                if row.get("is_sysuptime", False) or row.get("is_index", False):
                    continue
                row["use_override_var"].set(False)
                if row.get("is_enum"):
                    row["override_entry"].set("")
                else:
                    row["override_entry"].delete(0, "end")
        finally:
            self._loading_trap_overrides = False

    def _refresh_current_values(self) -> None:
        """Refresh the current values displayed in the OID table."""
        if not self.connected:
            return

        for row in self.oid_rows:
            oid_name = row.get("oid_name")
            if not oid_name:
                continue

            try:
                if row.get("is_index", False):
                    if row.get("current_label") is not None:
                        row["current_label"].configure(text="")
                    continue

                actual_oid = self._resolve_table_oid(oid_name, row)
                if actual_oid:
                    response = requests.get(f"{self.api_url}/value?oid={actual_oid}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        current_value = str(data.get("value", "N/A"))
                        if row.get("is_enum"):
                            display_value = self._format_enum_display(
                                current_value,
                                row.get("enums", {}),
                            )
                            row["current_label"].configure(text=display_value)
                        else:
                            row["current_label"].configure(text=current_value)
                    elif row.get("current_label") is not None:
                        row["current_label"].configure(text="")
                elif row.get("current_label") is not None:
                    row["current_label"].configure(text="")
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
                if row.get("current_label") is not None:
                    row["current_label"].configure(text="")
                self._log(f"Failed to get current value for {oid_name}: {error}", "WARNING")

    def _refresh_sysuptime_value(self, _oid_name: str, label_widget: Any) -> None:
        """Refresh the sysUpTime value for a specific label widget."""
        if not self.connected:
            return

        try:
            response = requests.get(f"{self.api_url}/value?oid=1.3.6.1.2.1.1.3.0", timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_value = str(data.get("value", "N/A"))
                label_widget.configure(text=current_value)
                self._log(f"Refreshed sysUpTime: {current_value}")
            else:
                label_widget.configure(text="Error")
                self._log(f"Failed to refresh sysUpTime: {response.text}", "WARNING")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            label_widget.configure(text="Error")
            self._log(f"Failed to refresh sysUpTime: {error}", "WARNING")

    def _save_trap_config(self) -> None:
        """Save trap configuration including host/port and overrides."""
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "selected_trap": self.trap_var.get(),
            "trap_index": self._get_selected_trap_index(),
            "trap_overrides": self.current_trap_overrides,
        }
        try:
            resp = requests.post(f"{self.api_url}/config", json=cfg, timeout=5)
            resp.raise_for_status()
            self._log("Configuration saved to server")
            messagebox.showinfo("Success", "Configuration saved successfully")
        except requests.exceptions.RequestException as error:
            self._log(f"Failed to save config to server: {error}", "ERROR")
            self._save_config_locally(cfg)
            messagebox.showwarning("Warning", "Saved locally - server not available")

        self._save_all_overrides_silent()

    def _save_all_overrides_silent(self, trap_name_override: str | None = None) -> None:
        """Save all overrides from the table to the API without showing messages."""
        trap_name = trap_name_override or self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return

        overrides: dict[str, dict[str, Any]] = {}
        current_oid_names: set[str] = set()
        for row in self.oid_rows:
            oid_name = row["oid_name"]
            current_oid_names.add(oid_name)
            enabled = bool(row["use_override_var"].get())
            raw_value = ""
            if row.get("override_var") is not None:
                raw_value = row["override_var"].get().strip()
            else:
                raw_value = row["override_entry"].get().strip()

            if row.get("is_enum"):
                override_value = self._extract_enum_value(raw_value, row.get("enums", {}))
            else:
                override_value = raw_value

            if override_value or enabled:
                overrides[oid_name] = {
                    "value": override_value,
                    "enabled": enabled,
                }

        existing_overrides: dict[str, Any] = dict(self.current_trap_overrides or {})
        removed_any = False
        for oid_name in list(existing_overrides.keys()):
            if oid_name in current_oid_names:
                existing_overrides.pop(oid_name, None)
                removed_any = True

        merged_overrides = {**existing_overrides, **overrides}
        if not merged_overrides and not removed_any:
            return

        try:
            response = requests.post(
                f"{self.api_url}/trap-overrides/{trap_name}",
                json=merged_overrides,
                timeout=5,
            )
            if response.status_code == 200:
                self.current_trap_overrides = merged_overrides
                self._log(f"Saved {len(merged_overrides)} overrides for trap: {trap_name}")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            self._log(f"Failed to save overrides: {error}", "ERROR")

    def _load_traps(self) -> None:
        """Load available traps from the REST API."""
        if not self.connected:
            messagebox.showinfo("Not Connected", "Please connect to the SNMP agent first.")
            return

        try:
            response = requests.get(f"{self.api_url}/traps", timeout=5)
            response.raise_for_status()
            data = response.json()

            traps = data.get("traps", {})
            if not traps:
                messagebox.showinfo("No Traps", "No traps found in the loaded MIBs.")
                self.trap_dropdown.configure(values=["No traps available"], state="disabled")
                self.send_trap_btn.configure(state="disabled")
                self.send_test_trap_btn.configure(state="disabled")
                return

            self.traps_metadata = traps
            trap_names = sorted(traps.keys())
            self.trap_dropdown.configure(values=trap_names, state="readonly")
            self.send_trap_btn.configure(state="normal")
            self.send_test_trap_btn.configure(state="normal")

            if trap_names:
                self.trap_var.set(trap_names[0])

            self._log(f"Loaded {len(traps)} trap(s)")

        except requests.exceptions.RequestException as error:
            error_msg = f"Failed to load traps: {error}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _update_trap_info(self) -> None:
        """Update the trap info display with details of the selected trap."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            self.trap_info_text.configure(state="normal")
            self.trap_info_text.delete("1.0", "end")
            self.trap_info_text.configure(state="disabled")
            return

        previous_trap = getattr(self, "_last_trap_name", None)
        if previous_trap and previous_trap != trap_name:
            self._save_all_overrides_silent(trap_name_override=previous_trap)

        trap_data = self.traps_metadata.get(trap_name)
        if not trap_data:
            return

        info_lines = []
        info_lines.append(f"Name: {trap_name}")
        info_lines.append(f"MIB: {trap_data.get('mib', 'Unknown')}")

        oid = trap_data.get("oid", [])
        oid_str = ".".join(str(x) for x in oid) if oid else "Unknown"
        info_lines.append(f"OID: {oid_str}")

        info_lines.append(f"Status: {trap_data.get('status', 'Unknown')}")

        objects = trap_data.get("objects", [])
        if objects:
            info_lines.append(f"\nObjects ({len(objects)}):")
            for obj in objects:
                obj_mib = obj.get("mib", "")
                obj_name = obj.get("name", "")
                info_lines.append(f"  - {obj_mib}::{obj_name}")

        description = trap_data.get("description", "")
        if description:
            info_lines.append("\nDescription:")
            info_lines.append(f"  {description}")

        self.trap_info_text.configure(state="normal")
        self.trap_info_text.delete("1.0", "end")
        self.trap_info_text.insert("1.0", "\n".join(info_lines))
        self.trap_info_text.configure(state="disabled")

        self._setup_trap_index_selectors(trap_name)
        self._update_available_oids(trap_name, trap_data)
        self._update_override_labels()

        self._last_trap_name = trap_name
        self._last_trap_index = self._get_selected_trap_index()

    def _trap_has_index_objects(self, trap_data: dict[str, Any]) -> bool:
        """Check if the trap contains any Index-type varbinds that require instance values."""
        objects = trap_data.get("objects", [])

        index_object_names = {
            "ifIndex",
        }

        for obj in objects:
            obj_name = obj.get("name", "")
            if obj_name in index_object_names:
                return True

        return False

    def _get_trap_indices(self, trap_data: dict[str, Any]) -> list[str]:
        """Get available indices for the trap's index objects."""
        objects = trap_data.get("objects", [])

        for obj in objects:
            obj_name = obj.get("name", "")
            if obj_name == "ifIndex":
                return self._get_interface_indices()

        return ["1"]

    def _get_interface_indices(self) -> list[str]:
        """Get available interface indices."""
        try:
            schema_resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": "1.3.6.1.2.1.2.2"},
                timeout=3,
            )
            if schema_resp.status_code == 200:
                schema = schema_resp.json()
                instances = [str(inst) for inst in schema.get("instances", [])]
                if instances:
                    def _sort_key(val: str) -> tuple[int, int | str]:
                        return (0, int(val)) if val.isdigit() else (1, val)

                    return sorted(instances, key=_sort_key)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

        try:
            resp = requests.get(
                f"{self.api_url}/value",
                params={"oid": "1.3.6.1.2.1.2.1.0"},
                timeout=2,
            )
            if resp.status_code == 200:
                data = resp.json()
                if_number = int(data.get("value", 1))
                return [str(i) for i in range(1, if_number + 1)]
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

        indices = []
        for index in range(1, 11):
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": f"1.3.6.1.2.1.2.2.1.1.{index}"},
                    timeout=1,
                )
                if resp.status_code == 200:
                    indices.append(str(index))
                else:
                    break
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                break

        return indices or ["1"]

    def _clear_trap_index_selectors(self) -> None:
        """Remove dynamic index selectors from the trap UI."""
        for widget in self.trap_index_widgets:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                widget.destroy()
        self.trap_index_widgets.clear()
        self.trap_index_vars.clear()
        self._trap_index_columns = []
        self._trap_index_columns_meta = {}
        self._trap_index_parent_table_oid = None
        self.trap_index_frame.pack_forget()

    def _get_selected_trap_index(self) -> str:
        """Build the current index string from dynamic selectors."""
        if not self._trap_index_columns:
            return str(self.trap_index_var.get())

        index_values: dict[str, str] = {}
        for col_name in self._trap_index_columns:
            var = self.trap_index_vars.get(col_name)
            if var is not None:
                index_values[col_name] = var.get()

        return str(
            self._build_instance_from_index_values(
                index_values,
                self._trap_index_columns,
                self._trap_index_columns_meta,
            )
        )

    def _setup_trap_index_selectors(self, trap_name: str) -> None:
        """Create index dropdowns for traps with index varbinds."""
        self._clear_trap_index_selectors()

        try:
            response = requests.get(f"{self.api_url}/trap-varbinds/{trap_name}", timeout=5)
            if response.status_code != 200:
                return
            data = response.json()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        index_columns = data.get("index_columns", [])
        columns_meta = data.get("columns_meta", {})
        parent_table_oid = data.get("parent_table_oid")
        instances = data.get("instances", [])

        if not index_columns:
            return

        if not instances and parent_table_oid:
            try:
                table_oid = ".".join(str(x) for x in parent_table_oid)
                schema_resp = requests.get(
                    f"{self.api_url}/table-schema",
                    params={"oid": table_oid},
                    timeout=3,
                )
                if schema_resp.status_code == 200:
                    schema = schema_resp.json()
                    instances = schema.get("instances", [])
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass

        self._trap_index_columns = list(index_columns)
        self._trap_index_columns_meta = columns_meta
        self._trap_index_parent_table_oid = (
            ".".join(str(x) for x in parent_table_oid) if parent_table_oid else None
        )

        values_by_column: dict[str, list[str]] = {col: [] for col in index_columns}
        for inst in instances:
            inst_str = str(inst)
            index_values = self._extract_index_values(inst_str, index_columns, columns_meta)
            for col in index_columns:
                val = index_values.get(col, "")
                if val and val not in values_by_column[col]:
                    values_by_column[col].append(val)

        for col in index_columns:
            values_by_column[col].sort()

        for col_name in index_columns:
            row_frame = ctk.CTkFrame(self.trap_index_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=(0, 4), anchor="w")
            self.trap_index_widgets.append(row_frame)

            label = ctk.CTkLabel(row_frame, text=f"{col_name}:", font=("", 10))
            label.pack(side="left", padx=(0, 6))
            self.trap_index_widgets.append(label)

            var = ctk.StringVar(value="")
            values = values_by_column.get(col_name, [])
            if values:
                var.set(values[0])

            combo = ctk.CTkComboBox(
                row_frame,
                variable=var,
                values=values or [""],
                width=160,
                font=("", 10),
                state="readonly",
            )
            combo.pack(side="left")
            self.trap_index_widgets.append(combo)
            self.trap_index_vars[col_name] = var
            var.trace_add("write", lambda *args: self._on_trap_index_change())

        self.trap_index_frame.pack(fill="x", pady=(0, 5), anchor="w")

    def _resolve_table_oid(self, oid_str: str, _row: dict[str, Any] | None = None) -> str | None:
        """Resolve a table OID with .index suffix to an actual OID with instance number."""
        if "." in oid_str and oid_str[-1].isdigit():
            parts = oid_str.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_name = parts[0]
                index_str = parts[1]

                for oid, metadata in self.oid_metadata.items():
                    metadata_name = metadata.get("name", "")
                    mib_name = metadata.get("mib", "")
                    full_name = f"{mib_name}::{metadata_name}"

                    if full_name == base_name:
                        return f"{oid}.{index_str}"

        if "::" in oid_str:
            for oid, metadata in self.oid_metadata.items():
                metadata_name = metadata.get("name", "")
                mib_name = metadata.get("mib", "")
                full_name = f"{mib_name}::{metadata_name}"

                if full_name == oid_str:
                    obj_type = metadata.get("type", "")
                    access = metadata.get("access", "").lower()

                    oid_parts = tuple(int(x) for x in oid.split("."))
                    if len(oid_parts) > 1:
                        parent_oid = ".".join(str(x) for x in oid_parts[:-1])
                        parent_metadata = self.oid_metadata.get(parent_oid, {})
                        parent_type = parent_metadata.get("type", "")

                        if parent_type == "MibTableRow":
                            return None

                    if "not-accessible" not in access and obj_type not in [
                        "MibTable",
                        "MibTableRow",
                    ]:
                        return f"{oid}.0"
                    return None

        return None

    def _get_oid_metadata_by_name(self, oid_name: str) -> dict[str, Any]:
        """Get OID metadata by MIB::name string."""
        if "::" not in oid_name:
            return {}

        for metadata in self.oid_metadata.values():
            metadata_name = metadata.get("name", "")
            mib_name = metadata.get("mib", "")
            if mib_name and metadata_name and f"{mib_name}::{metadata_name}" == oid_name:
                return metadata

        return {}

    def _format_enum_display(self, value: str, enums: dict[str, int]) -> str:
        """Format a raw value with its enum name when possible."""
        if value in ("", "N/A", "unset"):
            return value
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            return value

        for enum_name, enum_value in enums.items():
            if enum_value == int_value:
                return f"{value} ({enum_name})"

        return value

    def _extract_enum_value(self, display_value: str, enums: dict[str, int]) -> str:
        """Extract a raw enum value from a display string."""
        if " (" in display_value and display_value.endswith(")"):
            return display_value.split(" (", maxsplit=1)[0]

        if display_value.isdigit():
            return display_value

        for enum_name, enum_value in enums.items():
            if enum_name == display_value:
                return str(enum_value)

        return display_value
