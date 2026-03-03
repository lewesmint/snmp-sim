"""Links-tab behaviors for the SNMP GUI controller."""

# ruff: noqa: ANN401, PLR0915, PLR2004

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import customtkinter as ctk
import requests


class SNMPGuiLinksMixin:
    """Provide links UI setup and CRUD handlers."""

    root: Any
    tabview: Any
    connected: bool
    api_url: str
    oid_metadata: dict[str, Any]
    links_tree: Any
    links_data: list[dict[str, Any]]

    _log: Any

    def _setup_links_tab(self) -> None:
        """Set up the links management tab."""
        links_frame = self.tabview.tab("Links")

        toolbar = ctk.CTkFrame(links_frame)
        toolbar.pack(fill="x", padx=10, pady=(10, 6))

        refresh_btn = ctk.CTkButton(toolbar, text="Refresh", command=self._refresh_links, width=100)
        add_btn = ctk.CTkButton(
            toolbar,
            text="Add",
            command=lambda: self._open_link_dialog(None),
            width=80,
        )
        edit_btn = ctk.CTkButton(toolbar, text="Edit", command=self._edit_selected_link, width=80)
        delete_btn = ctk.CTkButton(
            toolbar,
            text="Delete",
            command=self._delete_selected_link,
            width=80,
        )

        refresh_btn.pack(side="left", padx=(0, 8))
        add_btn.pack(side="left", padx=(0, 8))
        edit_btn.pack(side="left", padx=(0, 8))
        delete_btn.pack(side="left", padx=(0, 8))

        self.links_tree = ttk.Treeview(
            links_frame,
            columns=("id", "scope", "match", "endpoints", "source"),
            show="headings",
            style="OID.Treeview",
        )
        self.links_tree.heading("id", text="ID")
        self.links_tree.heading("scope", text="Scope")
        self.links_tree.heading("match", text="Match")
        self.links_tree.heading("endpoints", text="Endpoints")
        self.links_tree.heading("source", text="Source")

        self.links_tree.column("id", width=180, minwidth=140, stretch=False, anchor="w")
        self.links_tree.column("scope", width=120, minwidth=100, stretch=False, anchor="w")
        self.links_tree.column("match", width=140, minwidth=120, stretch=False, anchor="w")
        self.links_tree.column("endpoints", width=520, minwidth=200, stretch=True, anchor="w")
        self.links_tree.column("source", width=100, minwidth=80, stretch=False, anchor="w")

        v_scroll = ttk.Scrollbar(links_frame, orient="vertical", command=self.links_tree.yview)
        self.links_tree.configure(yscrollcommand=v_scroll.set)

        self.links_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        v_scroll.pack(side="right", fill="y", pady=(0, 10))

        self.links_data: list[dict[str, Any]] = []
        self._refresh_links()

    def _format_link_endpoints(self, endpoints: list[dict[str, Any]]) -> str:
        parts = []
        for endpoint in endpoints:
            table_oid = endpoint.get("table_oid")
            column = endpoint.get("column")
            if table_oid:
                parts.append(f"{table_oid}:{column}")
            else:
                parts.append(str(column))
        return " | ".join(parts)

    def _parse_endpoints_text(self, text: str) -> list[dict[str, Any]]:
        """Parse endpoint text into endpoint dictionaries.

        Supported input forms per non-empty line (or comma-separated token):
        - "table_oid column"
        - "table_oid:column"
        - "column"
        """
        endpoints: list[dict[str, Any]] = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            parts = [p.strip() for p in line.split(",") if p.strip()] if "," in line else [line]
            for part in parts:
                if ":" in part:
                    table_oid, column = part.split(":", 1)
                    endpoints.append(
                        {"table_oid": table_oid.strip() or None, "column": column.strip()})
                    continue

                split_part = part.split()
                if len(split_part) >= 2:
                    table_oid = split_part[0].strip()
                    column = " ".join(split_part[1:]).strip()
                    endpoints.append({"table_oid": table_oid or None, "column": column})
                    continue

                endpoints.append({"table_oid": None, "column": part.strip()})

        return endpoints

    def _refresh_links(self) -> None:
        if not self.connected:
            return
        try:
            resp = requests.get(f"{self.api_url}/links", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            self.links_data = data.get("links", [])

            for item in self.links_tree.get_children():
                self.links_tree.delete(item)

            for link in self.links_data:
                endpoints_display = self._format_link_endpoints(link.get("endpoints", []))
                self.links_tree.insert(
                    "",
                    "end",
                    values=(
                        link.get("id", ""),
                        link.get("scope", ""),
                        link.get("match", ""),
                        endpoints_display,
                        link.get("source", ""),
                    ),
                )
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
            self._log(f"Failed to refresh links: {exc}", "WARNING")

    def _get_selected_link(self) -> dict[str, Any] | None:
        selection = self.links_tree.selection()
        if not selection:
            return None
        item = selection[0]
        link_id = self.links_tree.set(item, "id")
        for link in self.links_data:
            if link.get("id") == link_id:
                return link
        return None

    def _edit_selected_link(self) -> None:
        link = self._get_selected_link()
        if not link:
            messagebox.showinfo("Links", "Select a link first.")
            return
        self._open_link_dialog(link)

    def _delete_selected_link(self) -> None:
        link = self._get_selected_link()
        if not link:
            messagebox.showinfo("Links", "Select a link first.")
            return
        if link.get("source") != "state":
            messagebox.showinfo("Links", "Only state links can be deleted.")
            return
        if not messagebox.askyesno("Delete Link", f"Delete link '{link.get('id')}'?"):
            return
        try:
            resp = requests.delete(f"{self.api_url}/links/{link.get('id')}", timeout=5)
            resp.raise_for_status()
            self._refresh_links()
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
            self._log(f"Failed to delete link: {exc}", "WARNING")


    def _open_link_dialog(self, link: dict[str, Any] | None) -> None:
        """Link dialog with BASE + LINKED verification."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Link Columns" if link is None else f"Edit Link: {link.get('id')}")
        dialog.geometry("750x700")
        dialog.transient(self.root)
        dialog.grab_set()

        is_state = link is None or link.get("source") == "state"

        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Link Multiple OIDs/Columns with Base Selection",
            font=("TkDefaultFont", 14, "bold"),
        )
        title_label.pack(fill="x", pady=(0, 12))

        # Help text
        help_text = ctk.CTkLabel(
            main_frame,
            text="1. Enter column names or OIDs below\n"
            "2. Select one as the BASE (others will sync to it)\n"
            "3. Verify all are compatible\n"
            "• For columns: same table, shared index\n"
            "• For scalars: exact value matching",
            justify="left",
            text_color=("gray50", "gray70"),
            font=("TkDefaultFont", 9),
        )
        help_text.pack(fill="x", pady=(0, 12), padx=0)

        # Endpoints input
        endpoints_label = ctk.CTkLabel(main_frame, text="OIDs/Columns to Link:")
        endpoints_label.pack(anchor="w", pady=(6, 2))

        endpoints_text = tk.Text(
            main_frame,
            height=6,
            font=("Courier", 10),
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="white",
        )
        endpoints_text.pack(fill="both", expand=False, pady=(0, 12), ipady=6)

        if link:
            # Load existing endpoints
            endpoints_str = "\n".join([ep.get("column", "") for ep in link.get("endpoints", [])])
            endpoints_text.insert("1.0", endpoints_str)

        # BASE SELECTION FRAME
        base_frame = ctk.CTkFrame(main_frame, fg_color=("gray90", "gray20"), corner_radius=6)
        base_frame.pack(fill="x", pady=(0, 12), padx=0, ipady=8, ipadx=8)

        base_label = ctk.CTkLabel(
            base_frame,
            text="Select BASE OID (master - all others sync to this):",
            font=("TkDefaultFont", 10, "bold"),
        )
        base_label.pack(anchor="w", pady=(0, 8))

        base_var = tk.StringVar(value="")
        base_radio_frame = ctk.CTkFrame(base_frame, fg_color="transparent")
        base_radio_frame.pack(fill="x")

        # File/radio frame will be populated by validation
        base_radios: list[ctk.CTkRadioButton] = []

        # VERIFICATION FRAME
        verify_frame = ctk.CTkFrame(main_frame, fg_color=("gray95", "gray15"), corner_radius=6)
        verify_frame.pack(fill="x", pady=(0, 12), padx=8, ipady=10, ipadx=10)

        verify_label = ctk.CTkLabel(
            verify_frame,
            text="Verification: Not configured yet",
            text_color=("gray70", "gray50"),
            font=("TkDefaultFont", 9),
            wraplength=650,
            justify="left",
        )
        verify_label.pack(anchor="w")

        # Description
        desc_label = ctk.CTkLabel(main_frame, text="Description (optional):")
        desc_label.pack(anchor="w", pady=(6, 2))

        desc_var = ctk.StringVar(value="" if link is None else link.get("description", ""))
        ctk.CTkEntry(main_frame, textvariable=desc_var).pack(fill="x", pady=(0, 12))

        # Button frame
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(6, 0))

        def _rebuild_base_selection(resolved_endpoints: list[dict[str, Any]]) -> None:
            """Rebuild the BASE radio buttons based on resolved endpoints."""
            # Clear existing radios
            for widget in base_radio_frame.winfo_children():
                widget.destroy()
            base_radios.clear()
            base_var.set("")

            if not resolved_endpoints:
                empty_label = ctk.CTkLabel(
                    base_radio_frame,
                    text="(No valid OIDs entered)",
                    text_color=("gray70", "gray50"),
                )
                empty_label.pack(anchor="w")
                return

            for i, ep in enumerate(resolved_endpoints):
                ep_name = ep.get("name", "")
                ep_type = "Column" if ep.get("is_column") else "Scalar"
                radio_text = f"{ep_name}  ({ep_type})"

                radio = ctk.CTkRadioButton(
                    base_radio_frame,
                    text=radio_text,
                    variable=base_var,
                    value=str(i),
                    font=("TkDefaultFont", 9),
                )
                radio.pack(anchor="w", pady=2)
                base_radios.append(radio)

        def _parse_parts(text: str) -> list[str]:
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            parts: list[str] = []
            for line in lines:
                if "," in line:
                    parts.extend([p.strip() for p in line.split(",") if p.strip()])
                else:
                    parts.append(line)
            return parts

        def _resolve_parts(parts: list[str]) -> list[dict[str, Any]]:
            resolved_endpoints: list[dict[str, Any]] = []
            metadata = self.oid_metadata or {}
            for part in parts:
                matched = next(
                    (
                        (oid, meta)
                        for oid, meta in metadata.items()
                        if meta.get("name", "") == part
                    ),
                    None,
                )
                if matched is None:
                    resolved_endpoints.append(
                        {
                            "name": part,
                            "oid": part,
                            "type": "Unknown",
                            "mib": "Unknown",
                            "is_column": False,
                        }
                    )
                    continue

                oid_str, meta = matched
                parent_type = meta.get("parent_type")
                resolved_endpoints.append(
                    {
                        "name": part,
                        "oid": oid_str,
                        "type": meta.get("type", "Unknown"),
                        "parent_oid": meta.get("parent_oid"),
                        "parent_type": parent_type,
                        "mib": meta.get("mib", "Unknown"),
                        "is_column": parent_type == "MibTable" if parent_type else False,
                    }
                )
            return resolved_endpoints

        def _set_verify_message(resolved_endpoints: list[dict[str, Any]]) -> None:
            if len(resolved_endpoints) < 2:
                verify_label.configure(
                    text="⚠ Need at least 2 OIDs to create a link",
                    text_color=("orange", "orange"),
                )
                return

            columns = [ep for ep in resolved_endpoints if ep.get("is_column")]
            scalars = [ep for ep in resolved_endpoints if not ep.get("is_column")]

            if columns and scalars:
                verify_label.configure(
                    text="⚠ ERROR: Cannot mix table columns and scalars",
                    text_color=("red", "red"),
                )
                return

            if not columns:
                scalar_names = ", ".join(str(ep.get("name", "")) for ep in scalars)
                verify_text = (
                    f"✓ Valid Scalar Link\n"
                    f"  • Type: SCALAR VALUES (exact value matching)\n"
                    f"  • Scalars: {scalar_names}\n"
                    f"  • Behavior: All values stay synchronized globally"
                )
                verify_label.configure(text=verify_text, text_color=("green", "green"))
                return

            parent_oids = {ep.get("parent_oid") for ep in columns}
            if len(parent_oids) > 1:
                err_msg = ", ".join(str(p) for p in parent_oids)
                verify_label.configure(
                    text=f"⚠ ERROR: Columns from different tables: {err_msg}",
                    text_color=("red", "red"),
                )
                return

            parent_oid = next(iter(parent_oids))
            parent_name = next(
                (
                    m.get("name", "")
                    for m in (self.oid_metadata or {}).values()
                    if m.get("parent_oid") == parent_oid
                ),
                "Unknown",
            )
            column_names = ", ".join(str(ep.get("name", "")) for ep in columns)
            verify_text = (
                f"✓ Valid Column Link\n"
                f"  • Type: TABLE COLUMNS (shared-index matching)\n"
                f"  • Table: {parent_name} ({parent_oid})\n"
                f"  • Columns: {column_names}\n"
                f"  • Behavior: All column values sync with BASE per row"
            )
            verify_label.configure(text=verify_text, text_color=("green", "green"))

        def _on_endpoints_change(*_args: Any) -> None:
            """Validate and update BASE selection + verification."""
            text = endpoints_text.get("1.0", "end").strip()
            if not text:
                verify_label.configure(
                    text="Ready. Enter OIDs above.",
                    text_color=("gray70", "gray50"),
                )
                _rebuild_base_selection([])
                return

            parts = _parse_parts(text)
            resolved_endpoints = _resolve_parts(parts)
            _rebuild_base_selection(resolved_endpoints)
            _set_verify_message(resolved_endpoints)

        # Bind text changes
        endpoints_text.bind("<KeyRelease>", _on_endpoints_change)

        def _save() -> None:
            """Save the link with BASE selection."""
            text = endpoints_text.get("1.0", "end").strip()
            if not text:
                messagebox.showerror("Link", "Enter at least one OID")
                return

            # Validate BASE selected
            if not base_var.get():
                messagebox.showerror("Link", "Select a BASE OID (which endpoints sync to)")
                return

            parts = _parse_parts(text)

            if len(parts) < 2:
                messagebox.showerror("Link", "Enter at least two OIDs or column names")
                return

            # Resolve names to OIDs and table OIDs
            endpoints: list[dict[str, Any]] = []
            base_index = int(base_var.get())

            for i, part in enumerate(parts):
                # Try exact match on column name first
                matched = False
                for meta in (self.oid_metadata or {}).values():
                    if meta.get("name", "") == part:
                        table_oid = meta.get("parent_oid")
                        endpoint = {
                            "table_oid": table_oid,
                            "column": part,
                        }
                        # Mark which is the BASE
                        if i == base_index:
                            endpoint["is_base"] = True
                        endpoints.append(endpoint)
                        matched = True
                        break

                if not matched:
                    # Treat as OID string directly
                    endpoint = {
                        "table_oid": None,
                        "column": part,
                    }
                    if i == base_index:
                        endpoint["is_base"] = True
                    endpoints.append(endpoint)

            # Determine scope based on whether we have table OIDs
            has_table_oids = any(ep.get("table_oid") for ep in endpoints)
            scope = "per-instance" if has_table_oids else "global"

            payload = {
                "id": link.get("id") if link else None,
                "scope": scope,
                "type": "bidirectional",
                "match": "shared-index" if has_table_oids else "same",
                "endpoints": endpoints,
                "description": desc_var.get().strip() or None,
                "create_missing": False,
            }

            try:
                url = f"{self.api_url}/links"
                resp = requests.post(url, json=payload, timeout=5)
                resp.raise_for_status()
                dialog.destroy()
                self._refresh_links()
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
                msg = f"Failed to save link: {exc}"
                messagebox.showerror("Link", msg)

        def _close() -> None:
            dialog.destroy()

        save_btn = ctk.CTkButton(button_frame, text="Create Link", command=_save)
        close_btn = ctk.CTkButton(button_frame, text="Close", command=_close)

        if is_state:
            save_btn.pack(side="right", padx=(6, 0))
        close_btn.pack(side="right")

        # Initial validation
        _on_endpoints_change()
