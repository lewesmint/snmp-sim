# pylint: disable=broad-exception-caught,protected-access,unused-argument
# pylint: disable=unused-variable,attribute-defined-outside-init,line-too-long
# pylint: disable=too-many-lines,missing-module-docstring,missing-class-docstring
# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-statements
# pylint: disable=too-many-branches,too-many-nested-blocks,ungrouped-imports
# pylint: disable=consider-using-dict-items,consider-iterating-dictionary
# pylint: disable=no-else-return,no-else-break,consider-using-max-builtin
# pylint: disable=consider-using-in,import-outside-toplevel,use-maxsplit-arg
# pylint: disable=consider-using-f-string,too-many-return-statements
# pylint: disable=too-many-arguments,too-many-positional-arguments,superfluous-parens
# ruff: noqa: ANN401, ARG001, D100, D101, D401, ERA001, PLR0915, PLR2004, SLF001
# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import contextlib
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, cast

import customtkinter as ctk

from ui.icon_utils import load_icons_with_fallback
from ui.mib_browser import MIBBrowserWindow


class SNMPGuiLayoutMixin:
    mib_browser: MIBBrowserWindow | None

    def _setup_ui(self) -> None:
        """Setup the user interface components."""
        # Create a PanedWindow to split main content and log
        self.main_paned: tk.PanedWindow = tk.PanedWindow(
            self.root,
            orient=tk.VERTICAL,
            sashwidth=10,
            showhandle=True,
            handlesize=10,
            handlepad=2,
            sashrelief=tk.RAISED,
            bg="#2b2b2b",
        )
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=10)

        # Top pane: Main tabview for tabs
        top_frame = ctk.CTkFrame(self.main_paned)
        self.main_paned.add(top_frame, minsize=300, stretch="always")

        self.tabview = ctk.CTkTabview(top_frame)
        self.tabview.pack(fill="both", expand=True)
        try:
            self.tabview.configure(command=self._on_tab_change)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                # Fall back to the segmented button command hook if available.
                self.tabview._segmented_button.configure(command=self._on_tab_change)

        # Tab 1: Configuration (always visible)
        self.tabview.add("Configuration")
        self._setup_config_tab()

        # Tab 2: Scripts
        self.tabview.add("Scripts")
        self._setup_scripts_tab()

        # Tab 3: MIB Browser will be added later (after dynamic tabs) to keep it on the right
        # OID Tree and Table View will be added dynamically when connected
        # Traps tab will also be added dynamically when connected

        # Bottom pane: Log window
        log_frame = ctk.CTkFrame(self.main_paned)
        self.main_paned.add(log_frame, minsize=60, stretch="never")

        log_label = ctk.CTkLabel(log_frame, text="Log Output:", anchor="w")
        log_label.pack(fill="x", padx=5, pady=(5, 0))

        # Create frame for log text with scrollbars
        log_text_frame = tk.Frame(log_frame, bg="#2b2b2b")
        log_text_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Add vertical scrollbar only
        log_scrollbar_y = tk.Scrollbar(log_text_frame)
        log_scrollbar_y.pack(side="right", fill="y")

        # Create text widget with reduced height and vertical scrollbar only
        # Use wrap="word" so text wraps to fit window width
        self.log_text = tk.Text(
            log_text_frame,
            height=3,
            font=("Courier", 14),
            bg="#2b2b2b",
            fg="#ffffff",
            yscrollcommand=log_scrollbar_y.set,
            wrap="word",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(state="disabled")

        # Configure scrollbar
        log_scrollbar_y.config(command=self.log_text.yview)

        # Set log widget for logger
        self.logger.set_log_widget(self.log_text)

        # Status bar
        self.status_var = ctk.StringVar(value="Disconnected")
        status_bar = ctk.CTkLabel(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            fg_color=("gray85", "gray25"),
            corner_radius=0,
            height=25,
        )
        status_bar.pack(fill="x", side="bottom")

    def _set_initial_sash_position(self) -> None:
        """Set the initial position of the log window splitter."""
        try:
            window_height = self.root.winfo_height()
            # Put splitter to give log pane ~120 pixels (enough for 3 lines,
            # label, scrollbars, and padding).
            sash_pos = window_height - 120 - 20  # 20 for padding
            if sash_pos > 300:  # Ensure main content area gets at least 300 pixels
                # Use sash_place for tkinter.PanedWindow (not ttk.PanedWindow)
                cast("Any", self.main_paned.sash_place)(0, 0, sash_pos)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            # If setting sash position fails, just log and continue
            pass

    def _setup_oid_tab(self) -> None:
        """Setup the OID tree view tab."""
        oid_frame = self.tabview.tab("OID Tree")

        # State Management buttons (no captions)
        state_frame = ctk.CTkFrame(oid_frame)
        state_frame.pack(fill="x", padx=6, pady=(4, 0))

        self.fresh_state_btn = ctk.CTkButton(
            state_frame,
            text="Fresh State",
            command=self._fresh_state,
            width=120,
            height=28,
        )
        self.fresh_state_btn.pack(side="left", padx=(10, 6), pady=8)

        self.bake_btn = ctk.CTkButton(
            state_frame,
            text="Bake State",
            command=self._bake_state,
            width=120,
            height=28,
        )
        self.bake_btn.pack(side="left", padx=(0, 6), pady=8)

        self.reset_state_btn = ctk.CTkButton(
            state_frame,
            text="Reset State",
            command=self._reset_state,
            width=120,
            height=28,
        )
        self.reset_state_btn.pack(side="left", padx=(0, 6), pady=8)

        self.load_preset_btn = ctk.CTkButton(
            state_frame,
            text="Load Preset",
            command=self._load_preset_dialog,
            width=120,
            height=28,
        )
        self.load_preset_btn.pack(side="left", padx=(0, 6), pady=8)

        self.save_preset_btn = ctk.CTkButton(
            state_frame,
            text="Save Preset",
            command=self._save_preset_dialog,
            width=120,
            height=28,
        )
        self.save_preset_btn.pack(side="left", padx=(0, 10), pady=8)

        # Toolbar with expand/collapse
        toolbar = ctk.CTkFrame(oid_frame)
        toolbar.pack(fill="x", padx=6, pady=(4, 6))

        expand_btn = ctk.CTkButton(toolbar, text="Expand All", command=self._expand_all, width=100)
        collapse_btn = ctk.CTkButton(
            toolbar,
            text="Collapse All",
            command=self._collapse_all,
            width=100,
        )
        expand_btn.pack(side="left", padx=(0, 6))
        collapse_btn.pack(side="left")

        # Search bar
        search_label = ctk.CTkLabel(toolbar, text="Search:")
        search_label.pack(side="left", padx=(20, 5))
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(toolbar, textvariable=self.search_var, width=250)
        search_entry.pack(side="left", padx=(0, 6))
        search_entry.bind("<Return>", self._on_search_first)

        # Search button (Go cycles through matches)
        self.search_btn = ctk.CTkButton(toolbar, text="Go", command=self._on_search_first, width=50)
        self.search_btn.pack(side="left", padx=(0, 6))

        # Initialize search state
        self._search_matches: list[tuple[str, str]] = []  # List of (oid_str, display_name) tuples
        self._search_current_index = 0  # Current match index
        self._search_term = ""
        self._search_setting_selection = False  # Flag to distinguish search vs manual selection

        # Selected item details (OID, value, type) - copyable, non-editable
        self.selected_info_var = ctk.StringVar(value="")
        self.selected_info_entry = ctk.CTkEntry(
            toolbar,
            textvariable=self.selected_info_var,
            font=("Courier", 13),
            state="readonly",
        )
        self.selected_info_entry.pack(side="left", padx=(12, 12), fill="x", expand=True)

        # Font size controls
        font_inc_btn = ctk.CTkButton(
            toolbar,
            text="+",
            width=32,
            command=lambda: self._adjust_tree_font_size(1),
        )
        font_dec_btn = ctk.CTkButton(
            toolbar,
            text="-",
            width=32,
            command=lambda: self._adjust_tree_font_size(-1),
        )
        font_inc_btn.pack(side="right", padx=(6, 0))
        font_dec_btn.pack(side="right")

        # Frame for treeview (ttk.Treeview is used as customtkinter doesn't have a tree widget)
        tree_frame = ctk.CTkFrame(oid_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Configure Treeview style for better column distinction
        style = ttk.Style()
        # style.theme_use("default")
        style.theme_use("clam")  # optional: helps rowheight be respected on some platforms
        self.tree_font_size = 22
        self.tree_row_height = 40
        style.configure(
            "Treeview",
            font=("Helvetica", self.tree_font_size),
            rowheight=self.tree_row_height,
        )
        style.configure("Treeview.Heading", font=("Helvetica", self.tree_font_size + 1, "bold"))

        # Configure colors based on appearance mode

        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff"
        fg_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        selected_bg = "#1f538d" if ctk.get_appearance_mode() == "Dark" else "#0078d7"

        # Alternating row colors for better readability
        alt_bg = "#333333" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0"

        style.configure(
            "OID.Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            borderwidth=2,
            relief="solid",
            rowheight=40,
        )
        style.configure(
            "OID.Treeview.Heading",
            background="#1f1f1f" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0",
            foreground=fg_color,
            borderwidth=2,
            relief="groove",  # groove gives a 3D inset effect
            padding=5,
        )
        style.map("OID.Treeview", background=[("selected", selected_bg)])

        # Treeview for OIDs (add columns for instance, value, type, access, mib)
        self.oid_tree = ttk.Treeview(
            tree_frame,
            columns=("oid", "instance", "value", "type", "access", "mib"),
            show="tree headings",
            style="OID.Treeview",
            selectmode="browse",
        )
        self.oid_tree.heading("#0", text="📋 MIB/Object")
        self.oid_tree.heading("oid", text="🔢 OID")
        self.oid_tree.heading("instance", text="Instance")
        self.oid_tree.heading("value", text="💾 Value")
        self.oid_tree.heading("type", text="Type")
        self.oid_tree.heading("access", text="Access")
        self.oid_tree.heading("mib", text="📚 MIB")

        # Configure columns with borders for better separation
        self.oid_tree.column("#0", width=250, minwidth=150, stretch=False)
        self.oid_tree.column("oid", width=200, minwidth=150, stretch=False, anchor="w")
        self.oid_tree.column("instance", width=160, minwidth=120, stretch=False, anchor="w")
        self.oid_tree.column("value", width=200, minwidth=100, stretch=False, anchor="w")
        self.oid_tree.column("type", width=120, minwidth=80, stretch=False, anchor="w")
        self.oid_tree.column("access", width=100, minwidth=80, stretch=False, anchor="w")
        self.oid_tree.column("mib", width=120, minwidth=80, stretch=False, anchor="w")

        # Track manual column resizes to avoid auto-expanding the tree column
        self._oid_tree_user_resized = False

        # Configure tags for alternating row colors and column borders
        self.oid_tree.tag_configure("oddrow", background=alt_bg)
        self.oid_tree.tag_configure("evenrow", background=bg_color)

        # Scrollbars
        v_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.oid_tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.oid_tree.xview)
        self.oid_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.oid_tree.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)
        v_scroll.grid(row=0, column=1, sticky="ns", pady=5)
        h_scroll.grid(row=1, column=0, sticky="ew", padx=(5, 0))

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Bind expand event for lazy loading
        self.oid_tree.bind("<<TreeviewOpen>>", self._on_node_open)
        # Bind double-click for editing values
        self.oid_tree.bind("<Double-1>", self._on_double_click)
        # Detect manual column resizing
        self.oid_tree.bind("<ButtonRelease-1>", self._on_oid_tree_resize)
        # Bind selection change
        self._create_icon_images()
        self.oid_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _create_icon_images(self) -> None:
        """Create PhotoImage objects used in the tree view.

        If the `ui/icons` directory contains PNG files named after keys (e.g. folder.png), those are
        loaded and used. Otherwise the method generates simple colored square icons as a fallback.
        """
        icons_dir = Path(__file__).parent / "icons"

        icon_specs = {
            "folder": ("#f4c542", None),
            "table": ("#3b82f6", None),
            "entry": ("#06b6d4", None),
            "lock": ("#9ca3af", None),
            "edit": ("#10b981", None),
            "doc": ("#ffffff", "#e5e7eb"),
            "chart": ("#a78bfa", None),
            "key": ("#f97316", None),
        }

        icons = load_icons_with_fallback(
            icons_dir=icons_dir,
            icon_specs=icon_specs,
            size=16,
            inner_padding=2,
        )

        # Store images and keep refs so Tcl doesn't GC them
        self.oid_icon_images = icons
        self._image_refs = list(icons.values())

    def _setup_table_tab(self) -> None:
        """Setup the table view tab."""
        table_frame = self.tabview.tab("Table View")

        # Buttons frame
        buttons_frame = ctk.CTkFrame(table_frame)
        buttons_frame.pack(fill="x", padx=10, pady=(10, 0))

        # Add instance button
        self.add_instance_btn = ctk.CTkButton(
            buttons_frame,
            text="Add Instance",
            command=self._add_instance,
        )
        self.add_instance_btn.pack(side="left", padx=(0, 10))

        # Remove instance button
        self.remove_instance_btn = ctk.CTkButton(
            buttons_frame,
            text="Remove Instance",
            command=self._remove_instance,
            fg_color="red",
            hover_color="darkred",
        )
        self.remove_instance_btn.pack(side="left", padx=(0, 10))

        # Add index column button (only for no-index tables)
        self.add_index_col_btn = ctk.CTkButton(
            buttons_frame,
            text="Add Index Column",
            command=self._add_index_column,
            fg_color="green",
            hover_color="darkgreen",
        )
        self.add_index_col_btn.pack(side="left")

        # Initially disable buttons
        self.add_instance_btn.configure(state="disabled")
        self.remove_instance_btn.configure(state="disabled")
        self.add_index_col_btn.configure(state="disabled")

        # Table view treeview
        self.table_tree = ttk.Treeview(
            table_frame,
            columns=("index",),
            show="headings",
            style="OID.Treeview",
        )
        self.table_tree.heading("index", text="Index")
        self.table_tree.column("index", width=100, minwidth=50, stretch=False, anchor="w")

        # Bind selection change
        self.table_tree.bind("<<TreeviewSelect>>", self._on_table_row_select)
        # Bind double-click for cell editing
        self.table_tree.bind("<Double-1>", self._on_table_double_click)
        # Bind single click to save edit if clicking away from edit area
        self.table_tree.bind("<Button-1>", self._on_table_click)
        # Bind scroll and column resize to hide edit overlay
        self.table_tree.bind("<Configure>", self._on_table_configure)

        # Scrollbars
        v_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table_tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table_tree.xview)
        self.table_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.table_tree.pack(fill="both", expand=True, padx=10, pady=10)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")

        # Edit overlay for in-place cell editing - using tk.Frame for proper overlay
        # Create as child of root so place() uses absolute coordinates
        self.edit_overlay_frame = tk.Frame(self.root, bg="white", relief="solid", borderwidth=1)
        # Font size is tree_font_size - 1
        # Use ttk.Entry for text editing (will swap to Combobox for enums)
        self.edit_overlay_entry = ttk.Entry(
            self.edit_overlay_frame,
            font=("Helvetica", max(8, self.tree_font_size - 1)),
        )
        self.edit_overlay_entry.pack(padx=2, pady=2, fill="both", expand=True)
        # Also create a Combobox for enum fields (hidden by default)
        self.edit_overlay_combo = ttk.Combobox(
            self.edit_overlay_frame,
            font=("Helvetica", max(8, self.tree_font_size - 1)),
            width=40,
        )
        # Don't pack combo - will be managed dynamically

        # Store editing state
        self.editing_item: str | None = None
        self.editing_column: str | None = None
        self.editing_oid: str | None = None
        self._saving_cell: bool = False  # Flag to prevent re-entrant saves
        self._combo_just_selected: bool = False  # Flag to prevent double-save from FocusOut

        # Store current table context for cell editing
        self._current_table_columns: list[tuple[str, str, int]] = []  # (name, col_oid, col_num)
        self._current_index_columns: list[str] = []
        self._current_columns_meta: dict[str, Any] = {}
        self._current_table_item: str = ""
        self._current_table_oid: str | None = None

        # Message label for when no table is selected
        self.table_message_label = ctk.CTkLabel(
            table_frame,
            text="Select a table in the OID tree to view its data",
            font=("", 12),
        )
        self.table_message_label.pack(pady=20)
        self.table_message_label.pack_forget()  # Hide initially

    def _ensure_mib_browser_last(self) -> None:
        """Ensure MIB Browser tab is always last (rightmost).

        Removes and re-adds it if it already exists, or adds it for the first time.
        """
        was_active = False

        # Check if MIB Browser exists and is currently active
        if "MIB Browser" in self.tabview._tab_dict:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                was_active = self.tabview.get() == "MIB Browser"
            # Remove it
            self.tabview.delete("MIB Browser")

        # Add it back at the end
        self.tabview.add("MIB Browser")
        self._setup_mib_browser_tab()

        # Restore focus if it was active
        if was_active:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                self.tabview.set("MIB Browser")

    def enable_table_tab(self) -> None:
        """Enable the 'Table View' tab dynamically."""
        if "Table View" not in self.tabview._tab_dict:
            # Insert after OID Tree if it exists, otherwise after Configuration
            self.tabview.add("Table View")
            self._setup_table_tab()
            # Reposition MIB Browser to end
            self._ensure_mib_browser_last()

    def enable_oid_tree_tab(self) -> None:
        """Enable the 'OID Tree' tab after connecting."""
        if "OID Tree" not in self.tabview._tab_dict:
            # Insert after Configuration
            self.tabview.add("OID Tree")
            self._setup_oid_tab()
            # Populate the tree with data
            self._populate_oid_tree()
            # Reposition MIB Browser to end
            self._ensure_mib_browser_last()

    def enable_traps_tab(self) -> None:
        """Enable the 'Traps' tab after connecting."""
        if "Traps" not in self.tabview._tab_dict:
            # Add Traps tab
            self.tabview.add("Traps")
            self._setup_traps_tab()
            # Reposition MIB Browser to end
            self._ensure_mib_browser_last()

            # Reposition Scripts tab to come after Traps
            if "Scripts" in self.tabview._tab_dict:
                # Remove and re-add Scripts tab to place it after Traps
                self.tabview.delete("Scripts")
                self.tabview.add("Scripts")
                self._setup_scripts_tab()
                # Reposition MIB Browser again
                self._ensure_mib_browser_last()

    def enable_links_tab(self) -> None:
        """Enable the 'Links' tab after connecting."""
        if "Links" not in self.tabview._tab_dict:
            self.tabview.add("Links")
            self._setup_links_tab()
            self._ensure_mib_browser_last()

    def enable_mib_browser_tab(self) -> None:
        """Enable the 'MIB Browser' tab after connecting."""
        self._ensure_mib_browser_last()

    def _setup_config_tab(self) -> None:
        """Setup the configuration tab."""
        config_frame = self.tabview.tab("Configuration")

        # Connection frame
        conn_frame = ctk.CTkFrame(config_frame)
        conn_frame.pack(fill="x", padx=10, pady=10)

        conn_label = ctk.CTkLabel(conn_frame, text="Connection Settings", font=("", 14, "bold"))
        conn_label.grid(row=0, column=0, columnspan=2, pady=(10, 15), sticky="w", padx=10)

        # Host
        ctk.CTkLabel(conn_frame, text="Host:").grid(
            row=1,
            column=0,
            sticky="w",
            pady=5,
            padx=(10, 5),
        )
        self.host_var = ctk.StringVar(value="127.0.0.1")
        host_entry = ctk.CTkEntry(conn_frame, textvariable=self.host_var, width=200)
        host_entry.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=5)

        # Port
        ctk.CTkLabel(conn_frame, text="Port:").grid(
            row=2,
            column=0,
            sticky="w",
            pady=5,
            padx=(10, 5),
        )
        self.port_var = ctk.StringVar(value="8800")
        port_entry = ctk.CTkEntry(conn_frame, textvariable=self.port_var, width=200)
        port_entry.grid(row=2, column=1, sticky="ew", padx=(5, 10), pady=5)

        # Connect/Disconnect button
        self.connect_button = ctk.CTkButton(
            conn_frame,
            text="Connect",
            command=self._toggle_connection,
            width=150,
            height=32,
        )
        self.connect_button.grid(row=3, column=0, columnspan=2, pady=15)

        conn_frame.columnconfigure(1, weight=1)

        # MIBs section with resizable pane
        mibs_outer_frame = ctk.CTkFrame(config_frame)
        mibs_outer_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        mibs_label = ctk.CTkLabel(
            mibs_outer_frame,
            text="Implemented MIBs (with Dependencies)",
            font=("", 14, "bold"),
        )
        mibs_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Create a text widget to show summary and dependencies
        self.mibs_text = ctk.CTkTextbox(mibs_outer_frame, height=100, font=("Courier", 10))
        self.mibs_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.mibs_text.configure(state="disabled")

        # Store for later use
        self.mibs_data: dict[str, dict[str, Any]] = {}

    def _setup_scripts_tab(self) -> None:
        """Setup the Scripts tab."""
        scripts_frame = self.tabview.tab("Scripts")

        # Scripts content
        scripts_label = ctk.CTkLabel(scripts_frame, text="Scripts", font=("", 16, "bold"))
        scripts_label.pack(pady=20)

        scripts_text = ctk.CTkLabel(scripts_frame, text="TBD", font=("", 12))
        scripts_text.pack(pady=10)

    def _setup_traps_tab(self) -> None:
        """Setup the Traps tab."""
        traps_frame = self.tabview.tab("Traps")

        # Initialize trap destinations list (will be overridden by saved config)
        if not hasattr(self, "trap_destinations") or not self.trap_destinations:
            self.trap_destinations: list[tuple[str, int]] = [("localhost", 162)]
        self.oid_forces: dict[str, str] = {}  # oid -> value

        # Create scrollable frame for the entire tab
        self.traps_scrollable = ctk.CTkScrollableFrame(traps_frame)
        self.traps_scrollable.pack(fill="both", expand=True, padx=10, pady=10)

        # Top section: Trap destinations configuration
        dest_frame = ctk.CTkFrame(self.traps_scrollable)
        dest_frame.pack(fill="x", pady=(0, 10))

        dest_label = ctk.CTkLabel(dest_frame, text="Trap Destinations", font=("", 14, "bold"))
        dest_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Compact destination controls
        dest_controls = ctk.CTkFrame(dest_frame, fg_color="transparent")
        dest_controls.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(dest_controls, text="Host:").grid(row=0, column=0, padx=(0, 5))
        self.dest_host_var = ctk.StringVar(value="localhost")
        host_entry = ctk.CTkEntry(dest_controls, textvariable=self.dest_host_var, width=120)
        host_entry.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkLabel(dest_controls, text="Port:").grid(row=0, column=2, padx=(0, 5))
        self.dest_port_var = ctk.StringVar(value="162")
        port_entry = ctk.CTkEntry(dest_controls, textvariable=self.dest_port_var, width=60)
        port_entry.grid(row=0, column=3, padx=(0, 10))

        add_btn = ctk.CTkButton(dest_controls, text="Add", command=self._add_destination, width=60)
        add_btn.grid(row=0, column=4, padx=(0, 5))

        remove_btn = ctk.CTkButton(
            dest_controls,
            text="Remove Selected",
            command=self._remove_destination,
            width=120,
        )
        remove_btn.grid(row=0, column=5)

        # Destination list - compact table view
        dest_list_frame = ctk.CTkFrame(dest_frame)
        dest_list_frame.pack(fill="x", padx=10, pady=(0, 10))

        dest_list_label = ctk.CTkLabel(
            dest_list_frame,
            text="Current Destinations:",
            font=("", 11, "bold"),
        )
        dest_list_label.pack(anchor="w", padx=10, pady=(5, 0))

        # Create frame for treeview with scrollbar
        dest_tree_frame = ctk.CTkFrame(dest_list_frame, fg_color="transparent")
        dest_tree_frame.pack(padx=10, pady=(0, 5), fill="x")

        # Create Treeview for destinations - compact style with smaller font
        # Create a custom style for destinations with smaller row height
        dest_bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff"
        dest_fg_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        dest_selected_bg = "#1f538d" if ctk.get_appearance_mode() == "Dark" else "#0078d7"

        dest_style = ttk.Style()
        dest_style.configure(
            "Dest.Treeview",
            background=dest_bg_color,
            foreground=dest_fg_color,
            fieldbackground=dest_bg_color,
            borderwidth=1,
            relief="solid",
            rowheight=24,  # Larger row height for better readability
            font=("Helvetica", 12),  # Larger font
        )
        dest_style.configure(
            "Dest.Treeview.Heading",
            background="#1f1f1f" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0",
            foreground=dest_fg_color,
            borderwidth=1,
            relief="groove",
            padding=5,
            font=("Helvetica", 12, "bold"),  # Larger font
        )
        dest_style.map("Dest.Treeview", background=[("selected", dest_selected_bg)])

        # Scrollbar for destinations
        dest_scrollbar = ttk.Scrollbar(dest_tree_frame, orient="vertical")
        dest_scrollbar.pack(side="right", fill="y")

        self.dest_tree = ttk.Treeview(
            dest_tree_frame,
            columns=("host", "port"),
            show="headings",
            height=5,  # Show 5 rows, scrollbar will appear if more
            style="Dest.Treeview",
            selectmode="extended",
            yscrollcommand=dest_scrollbar.set,
        )
        self.dest_tree.heading("host", text="Host")
        self.dest_tree.heading("port", text="Port")
        self.dest_tree.column("host", width=150, minwidth=100)
        self.dest_tree.column("port", width=80, minwidth=60, anchor="center")

        dest_scrollbar.config(command=self.dest_tree.yview)
        self.dest_tree.pack(side="left", fill="x", expand=True)

        # Trap Receiver Section
        receiver_frame = ctk.CTkFrame(self.traps_scrollable)
        receiver_frame.pack(fill="x", pady=(0, 10))

        receiver_label = ctk.CTkLabel(receiver_frame, text="Trap Receiver", font=("", 14, "bold"))
        receiver_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Receiver controls
        receiver_controls = ctk.CTkFrame(receiver_frame, fg_color="transparent")
        receiver_controls.pack(fill="x", padx=10, pady=(0, 10))

        # Port configuration
        ctk.CTkLabel(receiver_controls, text="Listen Port:").grid(row=0, column=0, padx=(0, 5))
        self.receiver_port_var = ctk.StringVar(value="16662")
        port_entry = ctk.CTkEntry(receiver_controls, textvariable=self.receiver_port_var, width=80)
        port_entry.grid(row=0, column=1, padx=(0, 10))

        # Start/Stop buttons
        self.start_receiver_btn = ctk.CTkButton(
            receiver_controls,
            text="Start Receiver",
            command=self._start_trap_receiver,
            width=120,
            fg_color="green",
        )
        self.start_receiver_btn.grid(row=0, column=2, padx=(0, 5))

        self.stop_receiver_btn = ctk.CTkButton(
            receiver_controls,
            text="Stop Receiver",
            command=self._stop_trap_receiver,
            width=120,
            state="disabled",
            fg_color="red",
        )
        self.stop_receiver_btn.grid(row=0, column=3)

        # Receiver status
        self.receiver_status_var = ctk.StringVar(value="Receiver: Stopped")
        receiver_status = ctk.CTkLabel(
            receiver_frame,
            textvariable=self.receiver_status_var,
            font=("", 11),
            text_color="gray",
        )
        receiver_status.pack(pady=(0, 10), padx=10, anchor="w")

        # Main content in two columns
        main_frame = ctk.CTkFrame(self.traps_scrollable)
        main_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Left column: Trap selection and info
        left_frame = ctk.CTkFrame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Trap selection
        select_label = ctk.CTkLabel(left_frame, text="Select Trap", font=("", 12, "bold"))
        select_label.pack(pady=(10, 5), padx=10, anchor="w")

        select_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        select_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.trap_var = ctk.StringVar(value="")
        self.trap_dropdown = ctk.CTkComboBox(
            select_frame,
            variable=self.trap_var,
            values=["No traps available"],
            width=250,
            state="disabled",
        )
        self.trap_dropdown.pack(fill="x", anchor="w", pady=(0, 6))

        # Index selectors (initially hidden, created dynamically per trap)
        self.trap_index_var = ctk.StringVar(value="1")
        self.trap_index_vars: dict[str, ctk.StringVar] = {}
        self.trap_index_widgets: list[ctk.CTkBaseClass] = []
        self._trap_index_columns: list[str] = []
        self._trap_index_columns_meta: dict[str, Any] = {}
        self._trap_index_parent_table_oid = None

        self.trap_index_frame = ctk.CTkFrame(select_frame, fg_color="transparent")
        self.trap_index_frame.pack_forget()

        # Trap info
        info_label = ctk.CTkLabel(left_frame, text="Trap Details", font=("", 12, "bold"))
        info_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.trap_info_text = ctk.CTkTextbox(left_frame, height=150, font=("Courier", 12))
        self.trap_info_text.pack(fill="x", padx=10, pady=(0, 10))
        self.trap_info_text.configure(state="disabled")

        # Send buttons frame
        send_buttons_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        send_buttons_frame.pack(pady=(0, 10))

        self.send_trap_btn = ctk.CTkButton(
            send_buttons_frame,
            text="Send Trap",
            command=self._send_trap,
            width=120,
            state="disabled",
            height=35,
        )
        self.send_trap_btn.pack(side="left", padx=(0, 5))

        self.send_test_trap_btn = ctk.CTkButton(
            send_buttons_frame,
            text="Send Test Trap",
            command=self._send_test_trap,
            width=120,
            state="disabled",
            height=35,
            fg_color="orange",
        )
        self.send_test_trap_btn.pack(side="left")

        # Right column: OID overrides table
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # OID overrides section
        overrides_label = ctk.CTkLabel(
            right_frame,
            text="OID Overrides for Selected Trap",
            font=("", 12, "bold"),
        )
        overrides_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Column widths for the overrides table
        self.trap_table_col_widths = {
            "oid": 260,
            "current": 140,
            "checkbox": 30,
            "override": 180,
        }

        # Table header
        header_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(0, 5))

        # Configure grid columns to match row layout
        header_frame.grid_columnconfigure(0, weight=0, minsize=self.trap_table_col_widths["oid"])
        header_frame.grid_columnconfigure(
            1,
            weight=0,
            minsize=self.trap_table_col_widths["current"],
        )
        header_frame.grid_columnconfigure(
            2,
            weight=0,
            minsize=self.trap_table_col_widths["checkbox"],
        )
        header_frame.grid_columnconfigure(
            3,
            weight=0,
            minsize=self.trap_table_col_widths["override"],
        )

        ctk.CTkLabel(header_frame, text="OID", font=("", 10, "bold"), anchor="w").grid(
            row=0,
            column=0,
            padx=(5, 5),
            sticky="ew",
        )
        ctk.CTkLabel(header_frame, text="Current Value", font=("", 10, "bold"), anchor="w").grid(
            row=0,
            column=1,
            padx=(0, 5),
            sticky="ew",
        )
        ctk.CTkLabel(
            header_frame,
            text="Force Override",
            font=("", 10, "bold"),
            anchor="center",
        ).grid(row=0, column=2, padx=(0, 5))
        ctk.CTkLabel(header_frame, text="Override Value", font=("", 10, "bold"), anchor="w").grid(
            row=0,
            column=3,
            padx=(0, 5),
            sticky="ew",
        )

        # Scrollable table for OID overrides
        table_frame = ctk.CTkScrollableFrame(right_frame, height=200)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.oid_table_frame = table_frame

        # Bind trap selection change
        def on_trap_select(*args: Any) -> None:
            self._update_trap_info()

        self.trap_var.trace_add("write", on_trap_select)

        # Store trap metadata
        self.traps_metadata: dict[str, dict[str, Any]] = {}
        self._loading_trap_overrides = False
        self._last_trap_name: str | None = None
        self._last_trap_index = None

        # Load trap destinations from app config via API
        self._load_trap_destinations()

    def _expand_all(self) -> None:
        """Expand all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.oid_tree.item(item, open=True)
            for c in self.oid_tree.get_children(item):
                _recurse(c)

        for root in self.oid_tree.get_children(""):
            _recurse(root)

    def _collapse_all(self) -> None:
        """Collapse all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.oid_tree.item(item, open=False)
            for c in self.oid_tree.get_children(item):
                _recurse(c)

        for root in self.oid_tree.get_children(""):
            _recurse(root)

    def _setup_mib_browser_tab(self) -> None:
        """Setup the MIB Browser tab for testing SNMP commands."""
        browser_frame = self.tabview.tab("MIB Browser")

        # Get connection settings for MIB browser
        host = self.host_var.get().strip() if hasattr(self, "host_var") else "127.0.0.1"

        # Create embedded MIB browser
        self.mib_browser = MIBBrowserWindow(
            parent=browser_frame,
            logger=self.logger,
            default_host=host,
            default_port=161,
            default_community="public",
            oid_metadata=self.oid_metadata,
        )
