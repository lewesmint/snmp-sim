"""UI setup and cached-MIB actions mixin for MIB Browser."""

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: D101

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk


class MIBBrowserUIMixin:
    def _setup_ui(self) -> None:
        """Set up the UI components."""
        # Main container
        if isinstance(self.window, ctk.CTk):
            container = self.window
        else:
            container = ctk.CTkFrame(self.window)
            container.pack(fill="both", expand=True)

        # Create tabbed interface
        self.tabview = ctk.CTkTabview(container)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Create tabs
        self.tabview.add("Browser")
        self.tabview.add("MIB Manager")

        # Setup each tab
        self._setup_browser_tab()
        self._setup_mib_manager_tab()

        # Status bar
        status_frame = ctk.CTkFrame(container)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.status_var = ctk.StringVar(value="Ready")
        status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var, anchor="w")
        status_label.pack(fill="x", padx=10, pady=(0, 5))

    def _setup_browser_tab(self) -> None:  # noqa: PLR0915
        """Set up the SNMP browser tab."""
        browser_tab = self.tabview.tab("Browser")

        # Connection settings panel
        conn_frame = ctk.CTkFrame(browser_tab)
        conn_frame.pack(fill="x", padx=10, pady=10)

        # Host
        host_label = ctk.CTkLabel(conn_frame, text="Host:", font=("", 12, "bold"))
        host_label.grid(row=0, column=0, padx=(5, 10), pady=5, sticky="w")

        self.host_var = ctk.StringVar(value=self.default_host)
        self.host_entry = ctk.CTkEntry(conn_frame, textvariable=self.host_var, width=150)
        self.host_entry.grid(row=0, column=1, padx=5, pady=5)

        # Port
        port_label = ctk.CTkLabel(conn_frame, text="Port:", font=("", 12, "bold"))
        port_label.grid(row=0, column=2, padx=(15, 10), pady=5, sticky="w")

        self.port_var = ctk.StringVar(value=str(self.default_port))
        self.port_entry = ctk.CTkEntry(conn_frame, textvariable=self.port_var, width=80)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5)

        # Community
        comm_label = ctk.CTkLabel(conn_frame, text="Community:", font=("", 12, "bold"))
        comm_label.grid(row=0, column=4, padx=(15, 10), pady=5, sticky="w")

        self.community_var = ctk.StringVar(value=self.default_community)
        self.community_entry = ctk.CTkEntry(conn_frame, textvariable=self.community_var, width=100)
        self.community_entry.grid(row=0, column=5, padx=5, pady=5)

        # OID and Value input panel
        control_panel = ctk.CTkFrame(browser_tab)
        control_panel.pack(fill="x", padx=10, pady=(0, 10))

        # OID input
        oid_label = ctk.CTkLabel(control_panel, text="OID:", font=("", 12, "bold"))
        oid_label.grid(row=0, column=0, padx=(5, 10), pady=5, sticky="w")

        self.oid_var = ctk.StringVar(value="1.3.6.1.2.1.1")
        self.oid_entry = ctk.CTkEntry(control_panel, textvariable=self.oid_var, width=400)
        self.oid_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Value input (for SET operations)
        value_label = ctk.CTkLabel(control_panel, text="Value:", font=("", 12, "bold"))
        value_label.grid(row=1, column=0, padx=(5, 10), pady=5, sticky="w")

        self.value_var = ctk.StringVar()
        self.value_entry = ctk.CTkEntry(control_panel, textvariable=self.value_var, width=400)
        self.value_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        control_panel.columnconfigure(1, weight=1)

        # Command buttons
        buttons_frame = ctk.CTkFrame(browser_tab)
        buttons_frame.pack(fill="x", padx=10, pady=(0, 10))

        get_btn = ctk.CTkButton(buttons_frame, text="GET", command=self._snmp_get, width=100)
        get_btn.pack(side="left", padx=5)

        getnext_btn = ctk.CTkButton(
            buttons_frame,
            text="GET NEXT",
            command=self._snmp_getnext,
            width=100,
        )
        getnext_btn.pack(side="left", padx=5)

        walk_btn = ctk.CTkButton(buttons_frame, text="WALK", command=self._snmp_walk, width=100)
        walk_btn.pack(side="left", padx=5)

        set_btn = ctk.CTkButton(buttons_frame, text="SET", command=self._snmp_set, width=100)
        set_btn.pack(side="left", padx=5)

        clear_btn = ctk.CTkButton(
            buttons_frame,
            text="Clear Results",
            command=self._clear_results,
            width=120,
        )
        clear_btn.pack(side="right", padx=5)

        # Toolbar with expand/collapse controls
        toolbar_frame = ctk.CTkFrame(browser_tab)
        toolbar_frame.pack(fill="x", padx=10, pady=(0, 10))

        expand_btn = ctk.CTkButton(
            toolbar_frame,
            text="Expand All",
            command=self._expand_all,
            width=100,
        )
        expand_btn.pack(side="left", padx=(0, 6))

        collapse_btn = ctk.CTkButton(
            toolbar_frame,
            text="Collapse All",
            command=self._collapse_all,
            width=100,
        )
        collapse_btn.pack(side="left", padx=(0, 10))

        # Results tree
        results_frame = ctk.CTkFrame(browser_tab)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Configure style for tree - match OID tree style
        style = ttk.Style()
        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff"
        fg_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        selected_bg = "#1f538d" if ctk.get_appearance_mode() == "Dark" else "#0078d7"

        style.configure(
            "Browser.Treeview",
            font=("Helvetica", 11),
            rowheight=30,
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            borderwidth=2,
            relief="solid",
        )
        style.configure(
            "Browser.Treeview.Heading",
            font=("Helvetica", 12, "bold"),
            background="#1f1f1f" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0",
            foreground=fg_color,
            borderwidth=2,
            relief="groove",
            padding=5,
        )
        style.map("Browser.Treeview", background=[("selected", selected_bg)])

        # Scrollbars
        v_scroll = ttk.Scrollbar(results_frame, orient="vertical")
        h_scroll = ttk.Scrollbar(results_frame, orient="horizontal")

        # Tree with columns: OID, Type, Value
        self.results_tree = ttk.Treeview(
            results_frame,
            columns=("oid", "type", "value"),
            show="tree headings",
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
            style="Browser.Treeview",
        )

        v_scroll.config(command=self.results_tree.yview)
        h_scroll.config(command=self.results_tree.xview)

        # Configure columns
        self.results_tree.heading("#0", text="📋 Agent / Operation / OID")
        self.results_tree.heading("oid", text="🔢 OID")
        self.results_tree.heading("type", text="Type")
        self.results_tree.heading("value", text="💾 Value")

        self.results_tree.column("#0", width=300, minwidth=200)
        self.results_tree.column("oid", width=250, minwidth=150)
        self.results_tree.column("type", width=120, minwidth=80)
        self.results_tree.column("value", width=250, minwidth=150, stretch=True)

        # Pack tree and scrollbars
        self.results_tree.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)
        v_scroll.grid(row=0, column=1, sticky="ns", pady=5)
        h_scroll.grid(row=1, column=0, sticky="ew", padx=(5, 0))

        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)

        # Bind expand event for lazy loading if needed
        self.results_tree.bind("<<TreeviewOpen>>", self._on_node_open)

    def _setup_mib_manager_tab(self) -> None:
        """Set up the MIB Manager tab for browsing and caching MIBs."""
        mib_tab = self.tabview.tab("MIB Manager")

        # Instructions
        instructions = ctk.CTkLabel(
            mib_tab,
            text=(
                "Browse for original MIB source files (.mib, .txt, .my, .asn, "
                ".asn1) to cache and load them for name resolution."
            ),
            font=("", 12),
        )
        instructions.pack(padx=10, pady=10)

        # Buttons frame
        button_frame = ctk.CTkFrame(mib_tab)
        button_frame.pack(fill="x", padx=10, pady=10)

        browse_btn = ctk.CTkButton(
            button_frame,
            text="📁 Browse MIB Files",
            command=self._browse_mib_files,
            width=150,
        )
        browse_btn.pack(side="left", padx=5)

        load_mib_btn = ctk.CTkButton(
            button_frame,
            text="✓ Load Selected",
            command=self._load_selected_mib,
            width=130,
        )
        load_mib_btn.pack(side="left", padx=5)

        check_deps_btn = ctk.CTkButton(
            button_frame,
            text="🔍 Check Dependencies",
            command=self._show_mib_dependencies,
            width=150,
        )
        check_deps_btn.pack(side="left", padx=5)

        remove_btn = ctk.CTkButton(
            button_frame,
            text="✗ Remove Selected",
            command=self._remove_cached_mib,
            width=130,
        )
        remove_btn.pack(side="left", padx=5)

        refresh_btn = ctk.CTkButton(
            button_frame,
            text="🔄 Refresh List",
            command=self._refresh_cached_mibs,
            width=120,
        )
        refresh_btn.pack(side="left", padx=5)

        # Cached MIBs list
        list_frame = ctk.CTkFrame(mib_tab)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        list_label = ctk.CTkLabel(list_frame, text="Cached MIB Files:", font=("", 12, "bold"))
        list_label.pack(anchor="w", padx=5, pady=5)

        # Scrollable listbox for cached MIBs
        self.mib_listbox_frame = ctk.CTkScrollableFrame(list_frame)
        self.mib_listbox_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Refresh the list
        self._refresh_cached_mibs()

    def _load_selected_mib(self) -> None:
        """Load selected MIBs from cache with dependency resolution."""
        selected_files = [
            Path(file_path) for file_path, var in self.cached_mib_checkbuttons.items() if var.get()
        ]

        if not selected_files:
            messagebox.showwarning(
                "No Selection",
                "Please select at least one MIB to load",
                parent=self.window,
            )
            return

        loaded_count = 0
        failed_mibs = {}

        for mib_file in selected_files:
            mib_name = mib_file.stem

            # Check dependencies before loading
            _resolved_deps, missing_deps = self._resolve_mib_dependencies(mib_name)

            if missing_deps:
                # Show detailed error about which dependencies are missing
                missing_list = "\n  • ".join(sorted(missing_deps))
                failed_mibs[mib_name] = (
                    f"Missing {len(missing_deps)} required dependency(ies):\n  • {missing_list}"
                )
                self.logger.log(
                    f"Cannot load {mib_name}: missing dependencies {missing_deps}",
                    "ERROR",
                )
            else:
                loaded, _failed = self.load_mib([mib_name])
                if loaded:
                    loaded_count += 1
                else:
                    failed_mibs[mib_name] = "Failed to load (check log for details)"

        # Refresh to update loaded status
        self._refresh_cached_mibs()

        # Show results with clear feedback
        if loaded_count == len(selected_files):
            # All loaded successfully
            loaded_mibs_str = ", ".join([f.stem for f in selected_files])
            msg = f"✓ Successfully loaded {loaded_count} MIB(s):\n  {loaded_mibs_str}"
            messagebox.showinfo("Load Complete", msg, parent=self.window)
        elif loaded_count > 0:
            # Some loaded, some failed
            msg = f"✓ Successfully loaded {loaded_count} MIB(s)\n\n✗ Failed to load:\n"
            for mib, reason in failed_mibs.items():
                msg += f"\n• {mib}:\n  {reason}\n"
            messagebox.showwarning("Partial Load", msg, parent=self.window)
        else:
            # All failed
            msg = "✗ Failed to load all selected MIBs:\n"
            for mib, reason in failed_mibs.items():
                msg += f"\n• {mib}:\n  {reason}\n"
            messagebox.showerror("Load Failed", msg, parent=self.window)

    def _show_mib_dependencies(self) -> None:
        """Show dependency information for selected MIBs."""
        selected_files = [
            Path(file_path) for file_path, var in self.cached_mib_checkbuttons.items() if var.get()
        ]

        if not selected_files:
            messagebox.showwarning(
                "No Selection",
                "Please select at least one MIB to check dependencies",
                parent=self.window,
            )
            return

        # Create detailed dependency report
        report = "MIB Dependency Report\n" + "=" * 50 + "\n\n"

        all_satisfied = True
        for mib_file in selected_files:
            mib_name = mib_file.stem
            resolved_deps, missing_deps = self._resolve_mib_dependencies(mib_name)

            is_loaded = mib_name in self.loaded_mibs
            status_icon = "✓" if is_loaded else "✗" if missing_deps else "◦"

            report += f"{status_icon} {mib_name}\n"

            if is_loaded:
                report += "   Status: LOADED\n"
                if resolved_deps:
                    report += f"   Dependencies ({len(resolved_deps)} satisfied):\n"
                    for dep in sorted(resolved_deps):
                        dep_status = "✓" if self._is_mib_loaded_in_pysnmp(dep) else "?"
                        report += f"     {dep_status} {dep}\n"
            elif missing_deps:
                report += "   Status: UNSATISFIED DEPENDENCIES\n"
                report += f"   Missing ({len(missing_deps)}):\n"
                for missing in sorted(missing_deps):
                    report += f"     ✗ {missing}\n"
                if resolved_deps:
                    report += f"   Resolved ({len(resolved_deps)}):\n"
                    for dep in sorted(resolved_deps):
                        dep_status = "✓" if self._is_mib_loaded_in_pysnmp(dep) else "?"
                        report += f"     {dep_status} {dep}\n"
                all_satisfied = False
            else:
                report += "   Status: READY TO LOAD\n"
                if resolved_deps:
                    report += f"   Dependencies ({len(resolved_deps)}):\n"
                    for dep in sorted(resolved_deps):
                        dep_status = "✓" if self._is_mib_loaded_in_pysnmp(dep) else "?"
                        report += f"     {dep_status} {dep}\n"

            report += "\n"

        # Show report
        if all_satisfied:
            messagebox.showinfo("Dependency Check - All Satisfied", report, parent=self.window)
        else:
            messagebox.showerror(
                "Dependency Check - Unsatisfied Dependencies",
                report,
                parent=self.window,
            )

    def _remove_cached_mib(self) -> None:
        """Remove selected MIBs from cache."""
        selected_files = [
            file_path for file_path, var in self.cached_mib_checkbuttons.items() if var.get()
        ]

        if not selected_files:
            messagebox.showwarning(
                "No Selection",
                "Please select at least one MIB to remove",
                parent=self.window,
            )
            return

        # Confirm deletion
        file_list = "\n".join(f"• {Path(f).name}" for f in selected_files)
        confirm = messagebox.askyesno(
            "Confirm Removal",
            f"Remove the following MIB(s) from cache?\n\n{file_list}",
            parent=self.window,
        )

        if not confirm:
            return

        removed_count = 0
        for file_path in selected_files:
            mib_file = None
            try:
                mib_file = Path(file_path)
                mib_name = mib_file.stem

                # Unload if loaded
                if mib_name in self.loaded_mibs:
                    self.unload_mib(mib_name)

                # Delete file
                mib_file.unlink()
                removed_count += 1
                self.logger.log(f"Removed cached MIB: {mib_name}", "INFO")
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                mib_name = mib_file.name if mib_file else file_path
                self.logger.log(f"Failed to remove {mib_name}: {e}", "ERROR")
                messagebox.showerror(
                    "Remove Error",
                    f"Failed to remove {mib_name}:\n{e}",
                    parent=self.window,
                )

        if removed_count > 0:
            messagebox.showinfo(
                "Success",
                f"Removed {removed_count} file(s) from cache",
                parent=self.window,
            )
            self._refresh_cached_mibs()
