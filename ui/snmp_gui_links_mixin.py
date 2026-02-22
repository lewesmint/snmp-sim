"""Links-tab behaviors for the SNMP GUI controller."""

# ruff: noqa: ANN401, C901, PLC0206, PLR0913, PLR0915, PLR2004

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
            messagebox.showerror("Links", f"Failed to delete link: {exc}")

    def _parse_endpoints_text(self, text_value: str) -> list[dict[str, Any]]:
        endpoints: list[dict[str, Any]] = []
        for line in text_value.splitlines():
            raw = line.strip()
            if not raw:
                continue
            if ":" in raw:
                table_oid, column = raw.split(":", 1)
                endpoints.append({"table_oid": table_oid.strip(), "column": column.strip()})
                continue
            parts = raw.split()
            if len(parts) == 1:
                endpoints.append({"table_oid": None, "column": parts[0]})
            else:
                endpoints.append({"table_oid": parts[0], "column": parts[1]})
        return endpoints

    @staticmethod
    def _compute_dialog_endpoint(name: str, parent_oid: str) -> tuple[str | None, str]:
        column = name.rsplit(".", maxsplit=1)[-1] if "." in name else name
        table_oid = parent_oid or None
        return table_oid, column

    def _build_link_available_tree(
        self,
        available_tree: ttk.Treeview,
        scope: str,
        selected_map: dict[str, tuple[str, str | None, str]],
    ) -> None:
        available_tree.delete(*available_tree.get_children())

        if not hasattr(self, "oid_metadata") or not self.oid_metadata:
            return

        for oid_str, metadata in self.oid_metadata.items():
            if oid_str in selected_map:
                continue

            parent_type = metadata.get("parent_type", "")
            name = metadata.get("name", "")

            if scope == "per-instance" and parent_type == "MibTableRow":
                parent_oid = metadata.get("parent_oid", "")
                available_tree.insert("", "end", values=(name, oid_str), tags=(oid_str, parent_oid))
            elif scope == "global" and parent_type == "MibTable":
                available_tree.insert("", "end", values=(name, oid_str), tags=(oid_str, ""))

    @staticmethod
    def _build_link_selected_tree(
        selected_tree: ttk.Treeview,
        selected_map: dict[str, tuple[str, str | None, str]],
    ) -> None:
        selected_tree.delete(*selected_tree.get_children())
        for oid_str in list(selected_map.keys()):
            name, _, _ = selected_map[oid_str]
            selected_tree.insert("", "end", values=(name, oid_str))

    def _load_existing_link_selected(
        self,
        link: dict[str, Any],
        selected_map: dict[str, tuple[str, str | None, str]],
    ) -> None:
        for endpoint in link.get("endpoints", []):
            table_oid = endpoint.get("table_oid")
            column = endpoint.get("column", "")

            for oid_str, metadata in (self.oid_metadata or {}).items():
                if metadata.get("name", "").split(".")[-1] == column:
                    parent_oid = metadata.get("parent_oid", "")
                    if (table_oid and parent_oid == table_oid) or (
                        not table_oid and not parent_oid
                    ):
                        name = metadata.get("name", "")
                        selected_map[oid_str] = (name, table_oid, column)
                        break

    def _save_link_dialog(
        self,
        dialog: tk.Toplevel,
        selected_map: dict[str, tuple[str, str | None, str]],
        id_var: ctk.StringVar,
        scope_var: ctk.StringVar,
        match_var: ctk.StringVar,
        desc_var: ctk.StringVar,
    ) -> None:
        endpoints: list[dict[str, Any]] = []
        for oid_str in selected_map:
            _, table_oid, column = selected_map[oid_str]
            endpoints.append({"table_oid": table_oid, "column": column})

        if len(endpoints) < 2:
            messagebox.showerror("Links", "Provide at least two endpoints.")
            return

        payload = {
            "id": id_var.get().strip() or None,
            "scope": scope_var.get(),
            "type": "bidirectional",
            "match": match_var.get(),
            "endpoints": endpoints,
            "description": desc_var.get().strip() or None,
            "create_missing": False,
        }
        try:
            resp = requests.post(f"{self.api_url}/links", json=payload, timeout=5)
            resp.raise_for_status()
            dialog.destroy()
            self._refresh_links()
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Links", f"Failed to save link: {exc}")

    def _build_link_dialog_shell(
        self,
        link: dict[str, Any] | None,
    ) -> tuple[
        tk.Toplevel,
        ctk.CTkFrame,
        ctk.StringVar,
        ctk.StringVar,
        ctk.StringVar,
        ctk.StringVar,
        ttk.Treeview,
        ttk.Treeview,
        bool,
    ]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Link" if link else "New Link")
        dialog.geometry("640x420")
        dialog.transient(self.root)
        dialog.grab_set()

        is_state = link is None or link.get("source") == "state"

        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(frame, text="ID:").grid(row=0, column=0, sticky="w", pady=6)
        id_var = ctk.StringVar(value="" if link is None else link.get("id", ""))
        ctk.CTkEntry(frame, textvariable=id_var, width=260).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=6,
        )

        ctk.CTkLabel(frame, text="Scope:").grid(row=1, column=0, sticky="w", pady=6)
        scope_var = ctk.StringVar(
            value="per-instance" if link is None else link.get("scope", "per-instance"),
        )
        ctk.CTkOptionMenu(frame, values=["per-instance", "global"], variable=scope_var).grid(
            row=1,
            column=1,
            sticky="w",
            pady=6,
        )

        ctk.CTkLabel(frame, text="Match:").grid(row=2, column=0, sticky="w", pady=6)
        match_var = ctk.StringVar(
            value="shared-index" if link is None else link.get("match", "shared-index"),
        )
        ctk.CTkOptionMenu(frame, values=["shared-index"], variable=match_var).grid(
            row=2,
            column=1,
            sticky="w",
            pady=6,
        )

        ctk.CTkLabel(frame, text="Description:").grid(row=3, column=0, sticky="w", pady=6)
        desc_var = ctk.StringVar(value="" if link is None else link.get("description", ""))
        ctk.CTkEntry(frame, textvariable=desc_var).grid(row=3, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(frame, text="Selected:").grid(row=4, column=0, sticky="nw", pady=6)
        selected_frame = ctk.CTkFrame(frame)
        selected_frame.grid(row=4, column=1, sticky="nsew", pady=6)

        selected_tree = ttk.Treeview(
            selected_frame,
            columns=("name", "oid"),
            show="headings",
            height=4,
            style="OID.Treeview",
        )
        selected_tree.heading("name", text="Name")
        selected_tree.heading("oid", text="OID")
        selected_tree.column("name", width=220, minwidth=150, stretch=True, anchor="w")
        selected_tree.column("oid", width=220, minwidth=150, stretch=True, anchor="w")
        selected_scroll = ttk.Scrollbar(
            selected_frame,
            orient="vertical",
            command=selected_tree.yview,
        )
        selected_tree.configure(yscrollcommand=selected_scroll.set)
        selected_tree.pack(side="left", fill="both", expand=True)
        selected_scroll.pack(side="right", fill="y")

        ctk.CTkLabel(frame, text="Available:").grid(row=5, column=0, sticky="nw", pady=6)
        available_frame = ctk.CTkFrame(frame)
        available_frame.grid(row=5, column=1, sticky="nsew", pady=6)

        available_tree = ttk.Treeview(
            available_frame,
            columns=("name", "oid"),
            show="headings",
            height=8,
            style="OID.Treeview",
        )
        available_tree.heading("name", text="Name")
        available_tree.heading("oid", text="OID")
        available_tree.column("name", width=220, minwidth=150, stretch=True, anchor="w")
        available_tree.column("oid", width=220, minwidth=150, stretch=True, anchor="w")
        available_scroll = ttk.Scrollbar(
            available_frame,
            orient="vertical",
            command=available_tree.yview,
        )
        available_tree.configure(yscrollcommand=available_scroll.set)
        available_tree.pack(side="left", fill="both", expand=True)
        available_scroll.pack(side="right", fill="y")

        return (
            dialog,
            frame,
            id_var,
            scope_var,
            match_var,
            desc_var,
            selected_tree,
            available_tree,
            is_state,
        )

    def _open_link_dialog(self, link: dict[str, Any] | None) -> None:
        (
            dialog,
            frame,
            id_var,
            scope_var,
            match_var,
            desc_var,
            selected_tree,
            available_tree,
            is_state,
        ) = self._build_link_dialog_shell(link)

        # Track selected endpoints: {oid_str: (name, table_oid, column)}
        selected_map: dict[str, tuple[str, str | None, str]] = {}

        def _build_available_endpoints() -> None:
            self._build_link_available_tree(
                available_tree=available_tree,
                scope=scope_var.get(),
                selected_map=selected_map,
            )

        def _refresh_selected_tree() -> None:
            self._build_link_selected_tree(selected_tree=selected_tree, selected_map=selected_map)

        def _toggle_selection(event: Any) -> None:
            """Toggle selection when clicking available endpoint."""
            if not is_state:
                return

            tree_widget = event.widget
            region = tree_widget.identify("region", event.x, event.y)
            if region != "cell":
                return

            item = tree_widget.identify_row(event.y)
            if not item:
                return

            tags = tree_widget.item(item, "tags")
            if not tags or len(tags) < 2:
                return

            oid_str = tags[0]
            parent_oid = tags[1] if len(tags) > 1 else ""
            name = tree_widget.item(item, "values")[0]

            table_oid, column = self._compute_dialog_endpoint(str(name), parent_oid)

            # Add to selected
            selected_map[oid_str] = (name, table_oid, column)
            _refresh_selected_tree()
            _build_available_endpoints()

        def _deselect_endpoint(event: Any) -> None:
            """Remove endpoint when clicking selected endpoint."""
            if not is_state:
                return

            tree_widget = event.widget
            region = tree_widget.identify("region", event.x, event.y)
            if region != "cell":
                return

            item = tree_widget.identify_row(event.y)
            if not item:
                return

            values = tree_widget.item(item, "values")
            if values and len(values) >= 2:
                oid_str = values[1]
                if oid_str in selected_map:
                    del selected_map[oid_str]
                    _refresh_selected_tree()
                    _build_available_endpoints()

        def _on_scope_change(*_args: Any) -> None:
            """Handle scope change: filter available list and clear incompatible selections."""
            scope = scope_var.get()
            # Clear selected items that don't match new scope
            to_remove = []
            for oid_str, (_, table_oid, _) in selected_map.items():
                if (scope == "per-instance" and table_oid is None) or (
                    scope == "global" and table_oid is not None
                ):
                    to_remove.append(oid_str)
            for oid_str in to_remove:
                del selected_map[oid_str]
            _refresh_selected_tree()
            _build_available_endpoints()

        scope_var.trace_add("write", _on_scope_change)
        available_tree.bind("<ButtonRelease-1>", _toggle_selection)
        selected_tree.bind("<ButtonRelease-1>", _deselect_endpoint)

        # Initialize available endpoints list
        _build_available_endpoints()

        if link:
            self._load_existing_link_selected(link=link, selected_map=selected_map)
            _refresh_selected_tree()
            _build_available_endpoints()

        if not is_state:
            # Disable editing for schema links
            pass

        button_frame = ctk.CTkFrame(frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky="e")

        def _save() -> None:
            self._save_link_dialog(
                dialog=dialog,
                selected_map=selected_map,
                id_var=id_var,
                scope_var=scope_var,
                match_var=match_var,
                desc_var=desc_var,
            )

        def _close() -> None:
            dialog.destroy()

        save_btn = ctk.CTkButton(button_frame, text="Save", command=_save)
        close_btn = ctk.CTkButton(button_frame, text="Close", command=_close)

        if is_state:
            save_btn.pack(side="right", padx=(6, 0))
        close_btn.pack(side="right")

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=2)  # Selected endpoints
        frame.rowconfigure(5, weight=3)  # Available endpoints
