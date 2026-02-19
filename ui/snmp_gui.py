from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox, ttk
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Dict, Tuple, List, Literal,cast, TypedDict, Optional
import concurrent.futures
import requests
from datetime import datetime
import argparse
import json
import time
from pathlib import Path

# Import common utilities and MIB browser
try:
    from ui.common import Logger, save_gui_log
    from ui.mib_browser import MIBBrowserWindow
except ImportError:
    # Fallback for when running from ui directory
    try:
        from common import Logger, save_gui_log  # type: ignore[no-redef]
        from mib_browser import MIBBrowserWindow  # type: ignore[no-redef]
    except ImportError:
        # If module is not found, import from ui using absolute path
        import sys
        from pathlib import Path
        ui_dir = str(Path(__file__).parent)
        if ui_dir not in sys.path:
            sys.path.insert(0, ui_dir)
        from common import Logger, save_gui_log  # type: ignore[no-redef]
        from mib_browser import MIBBrowserWindow  # type: ignore[no-redef]

# Set appearance mode and color theme
ctk.set_appearance_mode("system")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

TrapType = Literal["trap", "inform"]

class SendTrapPayload(TypedDict):
    trap_name: str
    trap_type: TrapType
    dest_host: str
    dest_port: int
    community: str


def _oid_list_to_str(oid: Any) -> str:
    if isinstance(oid, (list, tuple)):
        return ".".join(str(x) for x in oid)
    return str(oid)

class SNMPControllerGUI:
    """GUI application for controlling SNMP agent with modern tabbed interface."""

    def __init__(self, root: ctk.CTk, api_url: str = "http://127.0.0.1:8800"):
        self.root = root
        self.api_url = api_url
        self.root.title("SNMP Simulator GUI")
        self.root.geometry("900x700")

        self.connected = False
        self.silent_errors = False  # If True, log errors without showing popup dialogs
        self.oids_data: Dict[str, Tuple[int, ...]] = {}  # Store OIDs for rebuilding (name -> OID tuple)
        self.oid_values: Dict[str, str] = {}  # oid_str -> value
        self.oid_metadata: Dict[str, Dict[str, Any]] = {}  # oid_str -> metadata
        self.table_instances_data: Dict[str, Dict[str, Any]] = {}  # Pre-loaded table instances data
        self.oid_to_item: Dict[str, str] = {}  # oid_str -> tree item id
        self._pending_oid_focus: Dict[str, Optional[str]] | None = None
        self._pending_oid_focus_retries: int = 0
        # Executor for background value fetching
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        
        # Initialize logger (will set log widget after UI setup)
        self.logger = Logger()
        
        # MIB Browser instance (will be created when tab is added)
        self.mib_browser: Optional[MIBBrowserWindow] = None
        
        self._setup_ui()
        self._log("Application started")

        # Initialize trap-related variables
        self.current_trap_overrides: Dict[str, str] = {}
        self.oid_rows: List[Dict[str, Any]] = []

        # Set initial sash position after window is displayed
        self.root.after(100, self._set_initial_sash_position)

        # Bind close handler to save GUI log and config
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
    
    def _setup_ui(self) -> None:
        """Setup the user interface components."""
        # Create a PanedWindow to split main content and log
        self.main_paned: tk.PanedWindow = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashwidth=5, bg="#2b2b2b")
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=10)

        # Top pane: Main tabview for tabs
        top_frame = ctk.CTkFrame(self.main_paned)
        self.main_paned.add(top_frame, minsize=300, stretch="always")

        self.tabview = ctk.CTkTabview(top_frame)
        self.tabview.pack(fill="both", expand=True)
        try:
            self.tabview.configure(command=self._on_tab_change)
        except Exception:
            try:
                # Fall back to the segmented button command hook if available.
                self.tabview._segmented_button.configure(command=self._on_tab_change)
            except Exception:
                pass

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
        self.log_text = tk.Text(log_text_frame, height=3, font=("Courier", 14), bg="#2b2b2b", fg="#ffffff",
                               yscrollcommand=log_scrollbar_y.set, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(state="disabled")

        # Configure scrollbar
        log_scrollbar_y.config(command=self.log_text.yview)

        # Set log widget for logger
        self.logger.set_log_widget(self.log_text)

        # Status bar
        self.status_var = ctk.StringVar(value="Disconnected")
        status_bar = ctk.CTkLabel(self.root, textvariable=self.status_var, anchor="w",
                                   fg_color=("gray85", "gray25"), corner_radius=0, height=25)
        status_bar.pack(fill="x", side="bottom")

    def _set_initial_sash_position(self) -> None:
        """Set the initial position of the log window splitter."""
        try:
            window_height = self.root.winfo_height()
            # Put splitter to give log pane ~120 pixels (enough for 3 lines + label + scrollbars + padding)
            sash_pos = window_height - 120 - 20  # 20 for padding
            if sash_pos > 300:  # Ensure main content area gets at least 300 pixels
                # Use sash_place for tkinter.PanedWindow (not ttk.PanedWindow)
                cast(Any, self.main_paned.sash_place)(0, 0, sash_pos)
        except Exception as e:
            # If setting sash position fails, just log and continue
            print(f"Warning: Could not set initial sash position: {e}")

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
        collapse_btn = ctk.CTkButton(toolbar, text="Collapse All", command=self._collapse_all, width=100)
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
        self._current_table_oid: str | None = None  # Track which table we're currently viewing
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
        font_inc_btn = ctk.CTkButton(toolbar, text="+", width=32, command=lambda: self._adjust_tree_font_size(1))
        font_dec_btn = ctk.CTkButton(toolbar, text="-", width=32, command=lambda: self._adjust_tree_font_size(-1))
        font_inc_btn.pack(side="right", padx=(6, 0))
        font_dec_btn.pack(side="right")

        # Frame for treeview (ttk.Treeview is used as customtkinter doesn't have a tree widget)
        tree_frame = ctk.CTkFrame(oid_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Configure Treeview style for better column distinction
        style = ttk.Style()
        # style.theme_use("default")
        style.theme_use('clam')                       # optional: helps rowheight be respected on some platforms
        self.tree_font_size = 22
        self.tree_row_height = 40
        style.configure("Treeview", font=('Helvetica', self.tree_font_size), rowheight=self.tree_row_height)
        style.configure("Treeview.Heading", font=('Helvetica', self.tree_font_size + 1, 'bold'))

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
        style.map("OID.Treeview",
                 background=[("selected", selected_bg)])

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
        size = 16
        icons = {}
        icons_dir = Path(__file__).parent / "icons"

        def make_generated(color: str, inner: str | None = None) -> tk.PhotoImage:
            img = tk.PhotoImage(width=size, height=size)
            img.put(color, to=(0, 0))
            if inner:
                img.put(inner, to=(2, 2))
            return img

        # Try to load from ui/icons/<name>.png, otherwise generate a simple icon
        icon_specs = {
            'folder': ('#f4c542', None),
            'table': ('#3b82f6', None),
            'lock': ('#9ca3af', None),
            'edit': ('#10b981', None),
            'doc': ('#ffffff', '#e5e7eb'),
            'chart': ('#a78bfa', None),
            'key': ('#f97316', None),
        }

        for name, (color, inner) in icon_specs.items():
            try:
                png_path = icons_dir / f"{name}.png"
                if png_path.exists():
                    icons[name] = tk.PhotoImage(file=str(png_path))
                else:
                    icons[name] = make_generated(color, inner)
            except Exception:
                # On any error fall back to generated icon
                icons[name] = make_generated(color, inner)

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
        self.add_instance_btn = ctk.CTkButton(buttons_frame, text="Add Instance", command=self._add_instance)
        self.add_instance_btn.pack(side="left", padx=(0, 10))

        # Remove instance button
        self.remove_instance_btn = ctk.CTkButton(buttons_frame, text="Remove Instance", command=self._remove_instance, fg_color="red", hover_color="darkred")
        self.remove_instance_btn.pack(side="left", padx=(0, 10))
        
        # Add index column button (only for no-index tables)
        self.add_index_col_btn = ctk.CTkButton(buttons_frame, text="Add Index Column", command=self._add_index_column, fg_color="green", hover_color="darkgreen")
        self.add_index_col_btn.pack(side="left")

        # Initially disable buttons
        self.add_instance_btn.configure(state="disabled")
        self.remove_instance_btn.configure(state="disabled")
        self.add_index_col_btn.configure(state="disabled")

        # Table view treeview
        self.table_tree = ttk.Treeview(table_frame, columns=("index",), show="headings", style="OID.Treeview")
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
        self.edit_overlay_entry = ttk.Entry(self.edit_overlay_frame, font=("Helvetica", max(8, self.tree_font_size - 1)))
        self.edit_overlay_entry.pack(padx=2, pady=2, fill="both", expand=True)
        # Also create a Combobox for enum fields (hidden by default)
        self.edit_overlay_combo = ttk.Combobox(self.edit_overlay_frame, font=("Helvetica", max(8, self.tree_font_size - 1)), width=40)
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
        self._current_table_item: str | None = None
        self._current_table_oid: str | None = None

        # Message label for when no table is selected
        self.table_message_label = ctk.CTkLabel(table_frame, text="Select a table in the OID tree to view its data", font=("", 12))
        self.table_message_label.pack(pady=20)
        self.table_message_label.pack_forget()  # Hide initially

    def _setup_links_tab(self) -> None:
        """Setup the links management tab."""
        links_frame = self.tabview.tab("Links")

        toolbar = ctk.CTkFrame(links_frame)
        toolbar.pack(fill="x", padx=10, pady=(10, 6))

        refresh_btn = ctk.CTkButton(toolbar, text="Refresh", command=self._refresh_links, width=100)
        add_btn = ctk.CTkButton(toolbar, text="Add", command=lambda: self._open_link_dialog(None), width=80)
        edit_btn = ctk.CTkButton(toolbar, text="Edit", command=self._edit_selected_link, width=80)
        delete_btn = ctk.CTkButton(toolbar, text="Delete", command=self._delete_selected_link, width=80)

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
        except Exception as exc:
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
        except Exception as exc:
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

    def _open_link_dialog(self, link: dict[str, Any] | None) -> None:
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
        id_entry = ctk.CTkEntry(frame, textvariable=id_var, width=260)
        id_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(frame, text="Scope:").grid(row=1, column=0, sticky="w", pady=6)
        scope_var = ctk.StringVar(value="per-instance" if link is None else link.get("scope", "per-instance"))
        scope_menu = ctk.CTkOptionMenu(frame, values=["per-instance", "global"], variable=scope_var)
        scope_menu.grid(row=1, column=1, sticky="w", pady=6)

        ctk.CTkLabel(frame, text="Match:").grid(row=2, column=0, sticky="w", pady=6)
        match_var = ctk.StringVar(value="shared-index" if link is None else link.get("match", "shared-index"))
        match_menu = ctk.CTkOptionMenu(frame, values=["shared-index"], variable=match_var)
        match_menu.grid(row=2, column=1, sticky="w", pady=6)

        ctk.CTkLabel(frame, text="Description:").grid(row=3, column=0, sticky="w", pady=6)
        desc_var = ctk.StringVar(value="" if link is None else link.get("description", ""))
        desc_entry = ctk.CTkEntry(frame, textvariable=desc_var)
        desc_entry.grid(row=3, column=1, sticky="ew", pady=6)

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

        selected_scroll = ttk.Scrollbar(selected_frame, orient="vertical", command=selected_tree.yview)
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

        available_scroll = ttk.Scrollbar(available_frame, orient="vertical", command=available_tree.yview)
        available_tree.configure(yscrollcommand=available_scroll.set)

        available_tree.pack(side="left", fill="both", expand=True)
        available_scroll.pack(side="right", fill="y")

        # Track selected endpoints: {oid_str: (name, table_oid, column)}
        selected_map: dict[str, tuple[str, str | None, str]] = {}

        def _build_available_endpoints() -> None:
            """Build available endpoints list based on scope."""
            available_tree.delete(*available_tree.get_children())
            scope = scope_var.get()
            
            if not hasattr(self, "oid_metadata") or not self.oid_metadata:
                return
            
            for oid_str, metadata in self.oid_metadata.items():
                if oid_str in selected_map:
                    continue
                
                parent_type = metadata.get("parent_type", "")
                name = metadata.get("name", "")
                
                if scope == "per-instance" and parent_type == "MibTableRow":
                    # Show columns for per-instance
                    parent_oid = metadata.get("parent_oid", "")
                    available_tree.insert("", "end", values=(name, oid_str), tags=(oid_str, parent_oid))
                elif scope == "global" and parent_type == "MibTable":
                    # Show scalars for global
                    available_tree.insert("", "end", values=(name, oid_str), tags=(oid_str, ""))

        def _refresh_selected_tree() -> None:
            """Refresh selected endpoints tree."""
            selected_tree.delete(*selected_tree.get_children())
            for oid_str in list(selected_map.keys()):
                name, _, _ = selected_map[oid_str]
                selected_tree.insert("", "end", values=(name, oid_str))

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
            
            # Extract column from name
            column = name.split(".")[-1] if "." in name else name
            table_oid = parent_oid if parent_oid else None
            
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

        def _on_scope_change(*args: Any) -> None:
            """Handle scope change: filter available list and clear incompatible selections."""
            scope = scope_var.get()
            # Clear selected items that don't match new scope
            to_remove = []
            for oid_str, (name, table_oid, column) in selected_map.items():
                if scope == "per-instance" and table_oid is None:
                    to_remove.append(oid_str)
                elif scope == "global" and table_oid is not None:
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
            # Load existing endpoints into selected_map
            for endpoint in link.get("endpoints", []):
                table_oid = endpoint.get("table_oid")
                column = endpoint.get("column", "")
                
                # Find the OID in metadata
                for oid_str, metadata in (self.oid_metadata or {}).items():
                    if metadata.get("name", "").split(".")[-1] == column:
                        parent_oid = metadata.get("parent_oid", "")
                        if (table_oid and parent_oid == table_oid) or (not table_oid and not parent_oid):
                            name = metadata.get("name", "")
                            selected_map[oid_str] = (name, table_oid, column)
                            break
            _refresh_selected_tree()
            _build_available_endpoints()

        if not is_state:
            # Disable editing for schema links
            pass

        button_frame = ctk.CTkFrame(frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky="e")

        def _save() -> None:
            endpoints = []
            for oid_str in selected_map.keys():
                name, table_oid, column = selected_map[oid_str]
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
            except Exception as exc:
                messagebox.showerror("Links", f"Failed to save link: {exc}")

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

    def _ensure_mib_browser_last(self) -> None:
        """Ensure MIB Browser tab is always last (rightmost).
        
        Removes and re-adds it if it already exists, or adds it for the first time.
        """
        was_active = False
        
        # Check if MIB Browser exists and is currently active
        if "MIB Browser" in self.tabview._tab_dict:
            try:
                was_active = (self.tabview.get() == "MIB Browser")
            except Exception:
                pass
            # Remove it
            self.tabview.delete("MIB Browser")
        
        # Add it back at the end
        self.tabview.add("MIB Browser")
        self._setup_mib_browser_tab()
        
        # Restore focus if it was active
        if was_active:
            try:
                self.tabview.set("MIB Browser")
            except Exception:
                pass
    
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
        ctk.CTkLabel(conn_frame, text="Host:").grid(row=1, column=0, sticky="w", pady=5, padx=(10, 5))
        self.host_var = ctk.StringVar(value="127.0.0.1")
        host_entry = ctk.CTkEntry(conn_frame, textvariable=self.host_var, width=200)
        host_entry.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=5)

        # Port
        ctk.CTkLabel(conn_frame, text="Port:").grid(row=2, column=0, sticky="w", pady=5, padx=(10, 5))
        self.port_var = ctk.StringVar(value="8800")
        port_entry = ctk.CTkEntry(conn_frame, textvariable=self.port_var, width=200)
        port_entry.grid(row=2, column=1, sticky="ew", padx=(5, 10), pady=5)

        # Connect/Disconnect button
        self.connect_button = ctk.CTkButton(conn_frame, text="Connect", command=self._toggle_connection,
                                            width=150, height=32)
        self.connect_button.grid(row=3, column=0, columnspan=2, pady=15)

        conn_frame.columnconfigure(1, weight=1)

        # MIBs section with resizable pane
        mibs_outer_frame = ctk.CTkFrame(config_frame)
        mibs_outer_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        mibs_label = ctk.CTkLabel(mibs_outer_frame, text="Implemented MIBs (with Dependencies)", font=("", 14, "bold"))
        mibs_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Create a text widget to show summary and dependencies
        self.mibs_text = ctk.CTkTextbox(mibs_outer_frame, height=100, font=("Courier", 10))
        self.mibs_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.mibs_text.configure(state="disabled")

        # Store for later use
        self.mibs_data: Dict[str, Dict[str, Any]] = {}


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
        if not hasattr(self, 'trap_destinations') or not self.trap_destinations:
            self.trap_destinations: List[Tuple[str, int]] = [("localhost", 162)]
        self.oid_forces: Dict[str, str] = {}  # oid -> value

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

        remove_btn = ctk.CTkButton(dest_controls, text="Remove Selected", command=self._remove_destination, width=120)
        remove_btn.grid(row=0, column=5)

        # Destination list - compact table view
        dest_list_frame = ctk.CTkFrame(dest_frame)
        dest_list_frame.pack(fill="x", padx=10, pady=(0, 10))

        dest_list_label = ctk.CTkLabel(dest_list_frame, text="Current Destinations:", font=("", 11, "bold"))
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
            font=('Helvetica', 12)  # Larger font
        )
        dest_style.configure(
            "Dest.Treeview.Heading",
            background="#1f1f1f" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0",
            foreground=dest_fg_color,
            borderwidth=1,
            relief="groove",
            padding=5,
            font=('Helvetica', 12, 'bold')  # Larger font
        )
        dest_style.map("Dest.Treeview",
                      background=[("selected", dest_selected_bg)])

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
            yscrollcommand=dest_scrollbar.set
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
            fg_color="green"
        )
        self.start_receiver_btn.grid(row=0, column=2, padx=(0, 5))

        self.stop_receiver_btn = ctk.CTkButton(
            receiver_controls,
            text="Stop Receiver",
            command=self._stop_trap_receiver,
            width=120,
            state="disabled",
            fg_color="red"
        )
        self.stop_receiver_btn.grid(row=0, column=3)

        # Receiver status
        self.receiver_status_var = ctk.StringVar(value="Receiver: Stopped")
        receiver_status = ctk.CTkLabel(
            receiver_frame,
            textvariable=self.receiver_status_var,
            font=("", 11),
            text_color="gray"
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
            state="disabled"
        )
        self.trap_dropdown.pack(fill="x", anchor="w", pady=(0, 6))

        # Index selectors (initially hidden, created dynamically per trap)
        self.trap_index_var = ctk.StringVar(value="1")
        self.trap_index_vars: dict[str, ctk.StringVar] = {}
        self.trap_index_widgets: list[ctk.CTkBaseClass] = []
        self._trap_index_columns: list[str] = []
        self._trap_index_columns_meta: dict[str, Any] = {}
        self._trap_index_parent_table_oid: str | None = None

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
            height=35
        )
        self.send_trap_btn.pack(side="left", padx=(0, 5))

        self.send_test_trap_btn = ctk.CTkButton(
            send_buttons_frame,
            text="Send Test Trap",
            command=self._send_test_trap,
            width=120,
            state="disabled",
            height=35,
            fg_color="orange"
        )
        self.send_test_trap_btn.pack(side="left")

        # Right column: OID overrides table
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # OID overrides section
        overrides_label = ctk.CTkLabel(right_frame, text="OID Overrides for Selected Trap", font=("", 12, "bold"))
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
        header_frame.grid_columnconfigure(1, weight=0, minsize=self.trap_table_col_widths["current"])
        header_frame.grid_columnconfigure(2, weight=0, minsize=self.trap_table_col_widths["checkbox"])
        header_frame.grid_columnconfigure(3, weight=0, minsize=self.trap_table_col_widths["override"])

        ctk.CTkLabel(header_frame, text="OID", font=("", 10, "bold"), anchor="w").grid(row=0, column=0, padx=(5, 5), sticky="ew")
        ctk.CTkLabel(header_frame, text="Current Value", font=("", 10, "bold"), anchor="w").grid(row=0, column=1, padx=(0, 5), sticky="ew")
        ctk.CTkLabel(header_frame, text="Force Override", font=("", 10, "bold"), anchor="center").grid(row=0, column=2, padx=(0, 5))
        ctk.CTkLabel(header_frame, text="Override Value", font=("", 10, "bold"), anchor="w").grid(row=0, column=3, padx=(0, 5), sticky="ew")

        # Scrollable table for OID overrides
        table_frame = ctk.CTkScrollableFrame(right_frame, height=200)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.oid_table_frame = table_frame

        # Bind trap selection change
        def on_trap_select(*args: Any) -> None:
            self._update_trap_info()
        self.trap_var.trace_add("write", on_trap_select)
        
        # Store trap metadata
        self.traps_metadata: Dict[str, Dict[str, Any]] = {}
        self._loading_trap_overrides = False
        self._last_trap_name: str | None = None
        self._last_trap_index: str | None = None

        # Load trap destinations from app config via API
        self._load_trap_destinations()

    def _is_index_varbind(self, oid_name: str) -> bool:
        """Check if the given OID name is an index varbind."""
        # Known INDEX object names that should not be overridden
        index_object_names = {
            "ifIndex",  # IF-MIB ifEntry index
            # Add more known INDEX objects here as discovered
        }

        # Extract the object name from the OID string (e.g., "IF-MIB::ifIndex.1" -> "ifIndex")
        if "::" in oid_name:
            parts = oid_name.split("::")
            if len(parts) == 2:
                obj_name = parts[1].split(".")[0]  # Remove any .N suffix
                return obj_name in index_object_names

        return False

    def _is_sysuptime_varbind(self, oid_name: str) -> bool:
        """Check if the given OID name is sysUpTime."""
        # sysUpTime OID: 1.3.6.1.2.1.1.3.0
        # Could be represented as "SNMPv2-MIB::sysUpTime.0" or similar
        if "::" in oid_name:
            parts = oid_name.split("::")
            if len(parts) == 2:
                obj_name = parts[1].split(".")[0]
                return obj_name == "sysUpTime"
        return False

    def _create_oid_table_row(self, oid_name: str, current_value: str = "") -> Dict[str, Any]:
        """Create a row in the OID overrides table."""
        row_frame = ctk.CTkFrame(self.oid_table_frame)
        row_frame.pack(fill="x", pady=2)

        # Fixed widths keep checkbox alignment stable across rows
        col_widths = getattr(self, "trap_table_col_widths", {})
        oid_col_width = col_widths.get("oid", 260)
        current_col_width = col_widths.get("current", 140)
        checkbox_col_width = col_widths.get("checkbox", 30)
        override_col_width = col_widths.get("override", 180)

        # Configure grid columns with proper weights
        row_frame.grid_columnconfigure(0, weight=0, minsize=oid_col_width)
        row_frame.grid_columnconfigure(1, weight=0, minsize=current_col_width)
        row_frame.grid_columnconfigure(2, weight=0, minsize=checkbox_col_width)
        row_frame.grid_columnconfigure(3, weight=0, minsize=override_col_width)

        # Check if this is a table OID (ends with .N where N is a digit)
        is_table_oid = False
        base_oid_name = oid_name
        index_part = ""
        if "." in oid_name and oid_name[-1].isdigit():
            # Check if ends with .N format (table instance)
            parts = oid_name.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                is_table_oid = True
                base_oid_name = parts[0]
                index_part = "." + parts[1]

        # Check if this is an index varbind (e.g., ifIndex)
        plain_name = base_oid_name.split("::", 1)[1] if "::" in base_oid_name else base_oid_name
        is_index = self._is_index_varbind(oid_name) or plain_name in self._trap_index_columns

        # Check if this is sysUpTime (special case - always real-time)
        is_sysuptime = self._is_sysuptime_varbind(oid_name)

        # Check if this OID has enums
        metadata = self._get_oid_metadata_by_name(base_oid_name)
        enums = metadata.get("enums") or {}
        has_enums = bool(enums)

        # OID name label (display without MIB prefix or extraneous detail)
        # Input: "TEST-ENUM-MIB::endPointName.192.168.1.1.1" -> "endPointName.192.168.1.1.1"
        # But show only the core name: "endPointName.192.168.1.1.1" (keep the instance suffixes)
        raw_display = oid_name.split("::", 1)[1] if "::" in oid_name else oid_name
        # The raw_display already has no MIB prefix; use as-is for trap varbinds
        display_name = raw_display
        oid_label = ctk.CTkLabel(
            row_frame,
            text=display_name,
            anchor="w",
            font=("", 10),
            width=oid_col_width,
        )
        oid_label.grid(row=0, column=0, padx=(5, 5), sticky="ew")

        # Current value label (show enums as "value (name)")
        current_label = ctk.CTkLabel(
            row_frame,
            text=current_value if current_value else "Loading...",
            anchor="w",
            font=("", 10),
            width=current_col_width,
        )
        current_label.grid(row=0, column=1, padx=(0, 5), sticky="ew")

        # Force override checkbox (hidden for index varbinds and sysUpTime)
        use_override_var = ctk.BooleanVar(value=False)
        override_value_var = ctk.StringVar(value="")
        override_check = ctk.CTkCheckBox(
            row_frame,
            text="",
            variable=use_override_var,
            width=checkbox_col_width,
        )

        # Override value widget (entry or enum dropdown)
        override_entry: Any
        if has_enums and not is_index and not is_sysuptime:
            enum_values = [f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])]
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

        def schedule_save_event(*args: Any) -> None:
            self._schedule_trap_override_save()

        if is_sysuptime:
            # Special handling for sysUpTime - show it as real-time
            sysuptime_label = ctk.CTkLabel(row_frame, text="(Real-time)", width=170, anchor="w", font=("", 10), text_color="#4a9eff")
            sysuptime_label.grid(row=0, column=2, columnspan=2, padx=(0, 5), sticky="w")

            # Add click handlers for sysUpTime row
            def on_sysuptime_single_click(event: Any) -> None:
                """Refresh sysUpTime value on single click."""
                self._refresh_sysuptime_value(oid_name, current_label)

            def on_sysuptime_double_click(event: Any) -> None:
                """Show notification on double click."""
                messagebox.showinfo(
                    "sysUpTime is Real-time",
                    "sysUpTime reflects the actual agent uptime and cannot be overridden.\n\n"
                    "It is automatically calculated based on how long the SNMP agent has been running.\n\n"
                    "Single-click on this row to refresh the current value."
                )

            # Bind click events to all widgets in the row
            for widget in [row_frame, oid_label, current_label, sysuptime_label]:
                widget.bind("<Button-1>", on_sysuptime_single_click)
                widget.bind("<Double-Button-1>", on_sysuptime_double_click)
        elif is_index:
            # Hide checkbox/entry/current value for index varbinds
            current_label.configure(text="")
            spacer = ctk.CTkLabel(row_frame, text="", width=checkbox_col_width + override_col_width)
            spacer.grid(row=0, column=2, columnspan=2, padx=(0, 5), sticky="ew")
        else:
            # Show checkbox and entry for non-index varbinds
            override_check.grid(row=0, column=2, padx=(0, 5))
            override_entry.grid(row=0, column=3, padx=(0, 5), sticky="ew")
            # Start with entry disabled
            override_entry.configure(state="disabled")

            # Enable/disable entry based on checkbox state
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

            # Auto-save when override values change
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
        
        # Get current trap index (supports multi-part indices)
        current_index = self._get_selected_trap_index()
        
        # Update labels for each row in the overrides table
        for row in self.oid_rows:
            base_oid_name = row.get("base_oid_name", row["oid_name"])
            
            # Check if this is a table OID that should have index updated
            if row["is_table_oid"]:
                # Strip MIB prefix from base_oid_name for display
                display_base = base_oid_name.split("::", 1)[1] if "::" in base_oid_name else base_oid_name
                # Update the index part with dot notation and rebuild the display name
                new_display_name = f"{display_base}.{current_index}"
                row["oid_label"].configure(text=new_display_name)
                # Update the stored oid_name with full name for API calls
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
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

        self._trap_override_save_job = self.root.after(400, self._save_all_overrides_silent)

    def _clear_oid_table(self) -> None:
        """Clear all rows from the OID overrides table."""
        job = getattr(self, "_trap_override_save_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._trap_override_save_job = None
        for row in self.oid_rows:
            row["frame"].destroy()
        self.oid_rows.clear()

    def _update_available_oids(self, trap_name: str, trap_data: Dict[str, Any]) -> None:
        """Update the available OIDs dropdown and create table for the selected trap."""
        objects = trap_data.get("objects", [])
        
        # Build OID list with index appended
        oid_list = []
        current_index = self._get_selected_trap_index()
        index_column_set = {col.lower() for col in self._trap_index_columns}
        for obj in objects:
            obj_mib = obj.get("mib", "")
            obj_name = obj.get("name", "")
            if obj_mib and obj_name:
                if self._trap_index_columns:
                    if obj_name.lower() in index_column_set or self._is_index_varbind(f"{obj_mib}::{obj_name}"):
                        continue
                # For traps with index columns, append the index with dot notation
                if self._trap_index_columns and current_index:
                    oid_list.append(f"{obj_mib}::{obj_name}.{current_index}")
                else:
                    oid_list.append(f"{obj_mib}::{obj_name}")
        
        print(f"DEBUG _update_available_oids: trap_name={trap_name}, objects count={len(objects)}, oid_list={oid_list}")

        # Adjust OID column width to fit the widest entry
        try:
            font = tkfont.Font(family="Helvetica", size=10)
            max_width = self.trap_table_col_widths.get("oid", 260)
            for oid_name in oid_list:
                display_name = oid_name.split("::", 1)[1] if "::" in oid_name else oid_name
                measured = font.measure(display_name) + 20
                if measured > max_width:
                    max_width = measured
            self.trap_table_col_widths["oid"] = max_width
        except Exception:
            pass
        
        # Clear existing table
        self._clear_oid_table()
        
        # Create table rows for each OID
        for oid_name in oid_list:
            row = self._create_oid_table_row(oid_name)
            self.oid_rows.append(row)
            print(f"DEBUG: Created row for {oid_name}")
        
        # Load existing overrides for this trap
        self._load_trap_overrides(trap_name)
        
        # Refresh current values after loading overrides
        self._refresh_current_values()

    def _load_trap_overrides(self, trap_name: str) -> None:
        """Load stored overrides for the specified trap and update table."""
        self._loading_trap_overrides = True
        try:
            response = requests.get(f"{self.api_url}/trap-overrides/{trap_name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.current_trap_overrides = data.get("overrides", {})
                
                # Update table rows with override values
                for row in self.oid_rows:
                    # Skip sysUpTime and index varbinds
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
                            display_val = self._format_enum_display(override_val, row.get("enums", {}))
                            if row.get("override_var") is not None:
                                row["override_var"].set(display_val)
                            else:
                                row["override_entry"].set(display_val)
                        else:
                            # Entry will be enabled by the trace callback
                            if row.get("override_var") is not None:
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
                        else:
                            if row.get("override_var") is not None:
                                row["override_var"].set("")
                            else:
                                row["override_entry"].delete(0, "end")
            else:
                self.current_trap_overrides = {}
                # Clear all checkboxes and entries
                for row in self.oid_rows:
                    # Skip sysUpTime and index varbinds
                    if row.get("is_sysuptime", False) or row.get("is_index", False):
                        continue
                    row["use_override_var"].set(False)
                    if row.get("is_enum"):
                        row["override_entry"].set("")
                    else:
                        row["override_entry"].delete(0, "end")
        except Exception as e:
            self._log(f"Failed to load trap overrides: {e}", "WARNING")
            self.current_trap_overrides = {}
            # Clear all checkboxes and entries
            for row in self.oid_rows:
                # Skip sysUpTime and index varbinds
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
                
                # Resolve OID to actual dotted notation
                actual_oid = self._resolve_table_oid(oid_name, row)
                if actual_oid:
                    response = requests.get(f"{self.api_url}/value?oid={actual_oid}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        current_value = str(data.get("value", "N/A"))
                        if row.get("is_enum"):
                            display_value = self._format_enum_display(current_value, row.get("enums", {}))
                            row["current_label"].configure(text=display_value)
                        else:
                            row["current_label"].configure(text=current_value)
                    else:
                        if row.get("current_label") is not None:
                            row["current_label"].configure(text="")
                else:
                    if row.get("current_label") is not None:
                        row["current_label"].configure(text="")
            except Exception as e:
                if row.get("current_label") is not None:
                    row["current_label"].configure(text="")
                self._log(f"Failed to get current value for {oid_name}: {e}", "WARNING")

    def _refresh_sysuptime_value(self, oid_name: str, label_widget: Any) -> None:
        """Refresh the sysUpTime value for a specific label widget."""
        if not self.connected:
            return

        try:
            # sysUpTime OID: 1.3.6.1.2.1.1.3.0
            response = requests.get(f"{self.api_url}/value?oid=1.3.6.1.2.1.1.3.0", timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_value = str(data.get("value", "N/A"))
                label_widget.configure(text=current_value)
                self._log(f"Refreshed sysUpTime: {current_value}")
            else:
                label_widget.configure(text="Error")
                self._log(f"Failed to refresh sysUpTime: {response.text}", "WARNING")
        except Exception as e:
            label_widget.configure(text="Error")
            self._log(f"Failed to refresh sysUpTime: {e}", "WARNING")

    def _save_trap_config(self) -> None:
        """Save trap configuration including host/port and overrides."""
        # Save host/port and trap settings to server
        # Note: trap_destinations are now managed via app config, not GUI config
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "selected_trap": self.trap_var.get(),
            "trap_index": self._get_selected_trap_index(),
            "trap_overrides": self.current_trap_overrides
        }
        try:
            resp = requests.post(f"{self.api_url}/config", json=cfg, timeout=5)
            resp.raise_for_status()
            self._log("Configuration saved to server")
            messagebox.showinfo("Success", "Configuration saved successfully")
        except requests.exceptions.RequestException as e:
            self._log(f"Failed to save config to server: {e}", "ERROR")
            # Fallback to local file if server save fails
            self._save_config_locally(cfg)
            messagebox.showwarning("Warning", "Saved locally - server not available")
        
        # Also save overrides for current trap
        self._save_all_overrides_silent()

    def _save_all_overrides_silent(self, trap_name_override: str | None = None) -> None:
        """Save all overrides from the table to the API without showing messages."""
        trap_name = trap_name_override or self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return
        
        # Collect overrides from table (current index)
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

        # Merge with existing overrides so other indices are preserved
        existing_overrides: dict[str, Any] = dict(self.current_trap_overrides or {})
        removed_any = False
        for oid_name in list(existing_overrides.keys()):
            if oid_name in current_oid_names:
                existing_overrides.pop(oid_name, None)
                removed_any = True

        merged_overrides = {**existing_overrides, **overrides}
        if not merged_overrides and not removed_any:
            # Nothing to save and no changes detected.
            return

        # Save to API
        try:
            response = requests.post(
                f"{self.api_url}/trap-overrides/{trap_name}",
                json=merged_overrides,
                timeout=5,
            )
            if response.status_code == 200:
                self.current_trap_overrides = merged_overrides
                self._log(f"Saved {len(merged_overrides)} overrides for trap: {trap_name}")
        except Exception as e:
            self._log(f"Failed to save overrides: {e}", "ERROR")

    def _load_trap_destinations(self) -> None:
        """Load trap destinations from app config via API."""
        try:
            response = requests.get(f"{self.api_url}/trap-destinations", timeout=5)
            if response.status_code == 200:
                data = response.json()
                destinations = data.get("destinations", [])
                # Convert to tuple format
                self.trap_destinations = [(d["host"], d["port"]) for d in destinations]
                self._update_dest_display()
                self._log(f"Loaded {len(self.trap_destinations)} trap destination(s) from config")
            else:
                self._log(f"Failed to load trap destinations: {response.text}", "WARNING")
                # Fallback to default
                self.trap_destinations = [("localhost", 162)]
        except Exception as e:
            self._log(f"Failed to load trap destinations: {e}", "WARNING")
            # Fallback to default
            self.trap_destinations = [("localhost", 162)]

    def _update_dest_display(self) -> None:
        """Update the destination display in the Treeview."""
        # Clear existing items
        for item in self.dest_tree.get_children():
            self.dest_tree.delete(item)

        # Add current destinations - ensure port is displayed as string
        for host, port in self.trap_destinations:
            # Store host and str(port) in treeview values for consistency
            self.dest_tree.insert("", "end", values=(str(host), str(port)))

    def _add_destination(self) -> None:
        """Add a new trap destination via API."""
        try:
            host = self.dest_host_var.get().strip()
            port = int(self.dest_port_var.get().strip())
            if not host:
                messagebox.showerror("Error", "Host cannot be empty")
                return
            if port < 1 or port > 65535:
                messagebox.showerror("Error", "Port must be between 1 and 65535")
                return

            # Add via API
            response = requests.post(
                f"{self.api_url}/trap-destinations",
                json={"host": host, "port": port},
                timeout=5
            )
            if response.status_code == 200:
                # Reload destinations from API
                self._load_trap_destinations()
                self._log(f"Added trap destination: {host}:{port}")
            else:
                messagebox.showerror("Error", f"Failed to add destination: {response.text}")
        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add destination: {e}")

    def _remove_destination(self) -> None:
        """Remove the selected destinations via API."""
        selected_items = self.dest_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select destinations to remove.")
            return

        # Get the values of selected items
        to_remove = []
        for item in selected_items:
            values = self.dest_tree.item(item, "values")
            if len(values) >= 2:
                host, port = values[0], values[1]
                try:
                    port_int = int(port)
                    to_remove.append((host, port_int))
                except ValueError:
                    self._log(f"Error converting port '{port}' to int", "WARNING")

        # Remove via API
        removed_hosts = []
        for host, port in to_remove:
            try:
                response = requests.request(
                    "DELETE",
                    f"{self.api_url}/trap-destinations",
                    json={"host": host, "port": port},
                    timeout=5
                )
                if response.status_code == 200:
                    removed_hosts.append(f"{host}:{port}")
                else:
                    self._log(f"Failed to remove {host}:{port}: {response.text}", "WARNING")
            except Exception as e:
                self._log(f"Failed to remove {host}:{port}: {e}", "ERROR")

        # Reload destinations from API
        self._load_trap_destinations()

        if removed_hosts:
            self._log(f"Removed trap destinations: {', '.join(removed_hosts)}")
        else:
            self._log("No destinations were removed", "WARNING")

    def _update_forced_display(self) -> None:
        """Update the forced OIDs display (legacy method - kept for compatibility)."""
        pass  # No longer used with table-based system

    def _set_trap_override(self) -> None:
        """Set a trap-specific OID override (legacy method - kept for compatibility)."""
        messagebox.showinfo("Use Table", "Please use the table above to set overrides and click 'Save Overrides'")



    def _clear_trap_overrides(self) -> None:
        """Clear all overrides for the current trap."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap first.")
            return

        # Clear local copy
        self.current_trap_overrides.clear()

        # Clear from API
        try:
            response = requests.delete(f"{self.api_url}/trap-overrides/{trap_name}", timeout=5)
            if response.status_code == 200:
                # Clear table checkboxes and entries
                for row in self.oid_rows:
                    # Skip index varbinds
                    if row.get("is_index", False):
                        continue
                    row["use_override_var"].set(False)
                    row["override_entry"].delete(0, "end")
                self._log(f"Cleared all overrides for trap: {trap_name}")
            else:
                messagebox.showerror("Error", f"Failed to clear overrides: {response.text}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear overrides: {e}")


    
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

            # Store trap metadata
            self.traps_metadata = traps

            # Update dropdown
            trap_names = sorted(traps.keys())
            self.trap_dropdown.configure(values=trap_names, state="readonly")
            self.send_trap_btn.configure(state="normal")
            self.send_test_trap_btn.configure(state="normal")
            
            # Select first trap
            if trap_names:
                self.trap_var.set(trap_names[0])
            
            self._log(f"Loaded {len(traps)} trap(s)")
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to load traps: {e}"
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
        
        # Build info text
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
        
        # Update display
        self.trap_info_text.configure(state="normal")
        self.trap_info_text.delete("1.0", "end")
        self.trap_info_text.insert("1.0", "\n".join(info_lines))
        self.trap_info_text.configure(state="disabled")
        
        # Configure index selectors for this trap
        self._setup_trap_index_selectors(trap_name)
        
        # Update available OIDs for this trap
        self._update_available_oids(trap_name, trap_data)
        
        # Update override labels with current index
        self._update_override_labels()

        self._last_trap_name = trap_name
        self._last_trap_index = self._get_selected_trap_index()
    
    def _trap_has_index_objects(self, trap_data: Dict[str, Any]) -> bool:
        """Check if the trap contains any Index-type varbinds that require instance values."""
        objects = trap_data.get("objects", [])
        
        # Known INDEX object names that require instance values
        index_object_names = {
            "ifIndex",  # IF-MIB ifEntry index
            # Add more known INDEX objects here as discovered
        }
        
        for obj in objects:
            obj_name = obj.get("name", "")
            if obj_name in index_object_names:
                return True
        
        return False
    
    def _get_trap_indices(self, trap_data: Dict[str, Any]) -> List[str]:
        """Get available indices for the trap's index objects."""
        objects = trap_data.get("objects", [])
        
        # For now, handle ifIndex specifically
        for obj in objects:
            obj_name = obj.get("name", "")
            if obj_name == "ifIndex":
                return self._get_interface_indices()
        
        # Default fallback
        return ["1"]
    
    def _get_interface_indices(self) -> List[str]:
        """Get available interface indices."""
        try:
            # Prefer the actual ifTable instances for accurate indices
            schema_resp = requests.get(
                f"{self.api_url}/table-schema",
                params={"oid": "1.3.6.1.2.1.2.2"},
                timeout=3,
            )
            if schema_resp.status_code == 200:
                schema = schema_resp.json()
                instances = [str(inst) for inst in schema.get("instances", [])]
                if instances:
                    # Sort numerically where possible
                    def _sort_key(val: str) -> tuple[int, int | str]:
                        return (0, int(val)) if val.isdigit() else (1, val)

                    return sorted(instances, key=_sort_key)
        except Exception:
            pass

        try:
            # Fallback: use ifNumber to build a range
            resp = requests.get(
                f"{self.api_url}/value",
                params={"oid": "1.3.6.1.2.1.2.1.0"},
                timeout=2,
            )
            if resp.status_code == 200:
                data = resp.json()
                if_number = int(data.get("value", 1))
                return [str(i) for i in range(1, if_number + 1)]
        except Exception:
            pass

        # Final fallback: probe a few ifIndex values
        indices = []
        for i in range(1, 11):
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": f"1.3.6.1.2.1.2.2.1.1.{i}"},
                    timeout=1,
                )
                if resp.status_code == 200:
                    indices.append(str(i))
                else:
                    break
            except Exception:
                break

        return indices if indices else ["1"]

    def _clear_trap_index_selectors(self) -> None:
        """Remove dynamic index selectors from the trap UI."""
        for widget in self.trap_index_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self.trap_index_widgets.clear()
        self.trap_index_vars.clear()
        self._trap_index_columns = []
        self._trap_index_columns_meta = {}
        self._trap_index_parent_table_oid = None
        self.trap_index_frame.pack_forget()

    def _get_selected_trap_index(self) -> str:
        """Build the current index string from dynamic selectors."""
        if not self._trap_index_columns:
            return self.trap_index_var.get()

        index_values: Dict[str, str] = {}
        for col_name in self._trap_index_columns:
            var = self.trap_index_vars.get(col_name)
            if var is not None:
                index_values[col_name] = var.get()

        return self._build_instance_from_index_values(
            index_values,
            self._trap_index_columns,
            self._trap_index_columns_meta,
        )

    def _setup_trap_index_selectors(self, trap_name: str) -> None:
        """Create index dropdowns for traps with index varbinds."""
        self._clear_trap_index_selectors()

        try:
            response = requests.get(f"{self.api_url}/trap-varbinds/{trap_name}", timeout=5)
            if response.status_code != 200:
                return
            data = response.json()
        except Exception:
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
            except Exception:
                pass

        self._trap_index_columns = list(index_columns)
        self._trap_index_columns_meta = columns_meta
        self._trap_index_parent_table_oid = ".".join(str(x) for x in parent_table_oid) if parent_table_oid else None

        # Build value lists for each index column
        values_by_column: Dict[str, list[str]] = {col: [] for col in index_columns}
        for inst in instances:
            inst_str = str(inst)
            index_values = self._extract_index_values(inst_str, index_columns, columns_meta)
            for col in index_columns:
                val = index_values.get(col, "")
                if val and val not in values_by_column[col]:
                    values_by_column[col].append(val)

        for col in index_columns:
            values_by_column[col].sort()

        # Create selectors
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
                values=values if values else [""],
                width=160,
                font=("", 10),
                state="readonly",
            )
            combo.pack(side="left")
            self.trap_index_widgets.append(combo)
            self.trap_index_vars[col_name] = var
            var.trace_add("write", lambda *args: self._on_trap_index_change())

        self.trap_index_frame.pack(fill="x", pady=(0, 5), anchor="w")
    
    def _resolve_table_oid(self, oid_str: str, row: Dict[str, Any] | None = None) -> str | None:
        """Resolve a table OID with .index suffix to an actual OID with instance number."""
        # Handle dot notation (e.g., "IF-MIB::ifAdminStatus.1")
        if "." in oid_str and oid_str[-1].isdigit():
            parts = oid_str.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_name = parts[0]
                index_str = parts[1]

                # Look up the base OID in metadata by name
                for oid, metadata in self.oid_metadata.items():
                    metadata_name = metadata.get("name", "")
                    mib_name = metadata.get("mib", "")
                    full_name = f"{mib_name}::{metadata_name}"

                    if full_name == base_name:
                        # Found the base OID, append the index
                        return f"{oid}.{index_str}"

        # For MIB::name format without instance, try to find exact match
        if "::" in oid_str:
            for oid, metadata in self.oid_metadata.items():
                metadata_name = metadata.get("name", "")
                mib_name = metadata.get("mib", "")
                full_name = f"{mib_name}::{metadata_name}"

                if full_name == oid_str:
                    # Found exact match, but no instance specified
                    # Check if this is a scalar or table column
                    obj_type = metadata.get("type", "")
                    access = metadata.get("access", "").lower()

                    # Check if this is a table column by looking at parent OID
                    oid_parts = tuple(int(x) for x in oid.split("."))
                    if len(oid_parts) > 1:
                        # Get parent OID
                        parent_oid = ".".join(str(x) for x in oid_parts[:-1])
                        parent_metadata = self.oid_metadata.get(parent_oid, {})
                        parent_type = parent_metadata.get("type", "")

                        # If parent is MibTableRow, this is a table column
                        if parent_type == "MibTableRow":
                            # Table column without instance - cannot resolve
                            return None

                    # Not a table column, check if it's a scalar
                    if "not-accessible" not in access and obj_type not in ["MibTable", "MibTableRow"]:
                        # Scalar - append .0
                        return f"{oid}.0"
                    else:
                        # Cannot resolve
                        return None

        return None

    def _get_oid_metadata_by_name(self, oid_name: str) -> Dict[str, Any]:
        """Get OID metadata by MIB::name string."""
        if "::" not in oid_name:
            return {}

        for oid, metadata in self.oid_metadata.items():
            metadata_name = metadata.get("name", "")
            mib_name = metadata.get("mib", "")
            if mib_name and metadata_name:
                if f"{mib_name}::{metadata_name}" == oid_name:
                    return metadata

        return {}

    def _format_enum_display(self, value: str, enums: Dict[str, int]) -> str:
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

    def _extract_enum_value(self, display_value: str, enums: Dict[str, int]) -> str:
        """Extract a raw enum value from a display string."""
        if " (" in display_value and display_value.endswith(")"):
            return display_value.split(" (")[0]

        if display_value.isdigit():
            return display_value

        for enum_name, enum_value in enums.items():
            if enum_name == display_value:
                return str(enum_value)

        return display_value

    def _start_trap_receiver(self) -> None:
        """Start the trap receiver."""
        try:
            port = int(self.receiver_port_var.get())
            payload = {
                "port": port,
                "community": "public"
            }

            response = requests.post(f"{self.api_url}/trap-receiver/start", json=payload, timeout=5)
            response.raise_for_status()
            result = response.json()

            if result.get("status") in ["started", "already_running"]:
                self.receiver_status_var.set(f"Receiver: Running on port {port}")
                self.start_receiver_btn.configure(state="disabled")
                self.stop_receiver_btn.configure(state="normal")
                self._log(f"Trap receiver started on port {port}")
            else:
                messagebox.showerror("Error", f"Failed to start receiver: {result.get('message', 'Unknown error')}")

        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except Exception as e:
            error_msg = f"Failed to start trap receiver: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _stop_trap_receiver(self) -> None:
        """Stop the trap receiver."""
        try:
            response = requests.post(f"{self.api_url}/trap-receiver/stop", timeout=5)
            response.raise_for_status()
            response.json()

            self.receiver_status_var.set("Receiver: Stopped")
            self.start_receiver_btn.configure(state="normal")
            self.stop_receiver_btn.configure(state="disabled")
            self._log("Trap receiver stopped")

        except Exception as e:
            error_msg = f"Failed to stop trap receiver: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _show_trap_notification(self, trap_name: str, trap_oid: str, timestamp: str, varbinds: list[dict[str, Any]]) -> None:
        """Show a custom notification dialog with trap details and varbinds table."""
        # Create custom dialog window
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Test Trap Received!")
        dialog.geometry("700x400")  # Smaller window

        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()

        # Header with trap info
        header_frame = ctk.CTkFrame(dialog)
        header_frame.pack(fill="x", padx=20, pady=20)

        title_label = ctk.CTkLabel(header_frame, text="✓ Successfully sent and received test trap!",
                                   font=("", 16, "bold"), text_color="green")
        title_label.pack(pady=(0, 10))

        info_frame = ctk.CTkFrame(header_frame)
        info_frame.pack(fill="x")

        ctk.CTkLabel(info_frame, text=f"Trap: {trap_name}", font=("", 13)).pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"OID: {trap_oid}", font=("", 13)).pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"Received at: {timestamp}", font=("", 13)).pack(anchor="w", pady=2)

        # Varbinds section
        varbinds_label = ctk.CTkLabel(dialog, text="Varbinds:", font=("", 14, "bold"))
        varbinds_label.pack(anchor="w", padx=20, pady=(10, 5))

        # Create frame for treeview (using tkinter's ttk.Treeview for table)
        from tkinter import ttk

        tree_frame = ctk.CTkFrame(dialog)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        varbinds_tree = ttk.Treeview(tree_frame, columns=("OID", "Value", "Type"),
                                     show="headings", yscrollcommand=tree_scroll.set, height=10)
        varbinds_tree.pack(fill="both", expand=True)
        tree_scroll.config(command=varbinds_tree.yview)

        # Configure columns
        varbinds_tree.heading("OID", text="OID")
        varbinds_tree.heading("Value", text="Value")
        varbinds_tree.heading("Type", text="Type")

        varbinds_tree.column("OID", width=300)
        varbinds_tree.column("Value", width=300)
        varbinds_tree.column("Type", width=150)

        # Populate with varbinds
        for vb in varbinds:
            vb_oid = vb.get("oid_str", "unknown")
            vb_value = vb.get("value", "")
            vb_type = vb.get("type", "")
            varbinds_tree.insert("", "end", values=(vb_oid, vb_value, vb_type))

        # Close button
        close_btn = ctk.CTkButton(dialog, text="Close", command=dialog.destroy, width=100)
        close_btn.pack(pady=(0, 20))

        # Center the dialog on the parent window
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

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
        host = self.host_var.get().strip() if hasattr(self, 'host_var') else "127.0.0.1"
        
        # Create embedded MIB browser
        self.mib_browser = MIBBrowserWindow(
            parent=browser_frame,
            logger=self.logger,
            default_host=host,
            default_port=161,
            default_community="public",
            oid_metadata=self.oid_metadata
        )

    def _populate_oid_tree(self) -> None:
        """Populate the OID tree with data."""
        # Clear existing
        for item in self.oid_tree.get_children():
            self.oid_tree.delete(item)
        self.oid_to_item.clear()

        if self.oids_data:
            # Build hierarchical tree
            root = self.oid_tree.insert("", "end", text="MIB Tree", values=("", "", "", "", "", ""))
            self.oid_tree.item(root, open=True)  # Expand root by default
            self._build_tree_from_oids(root, self.oids_data)
            # Fetch values for top-level leaves
            self.executor.submit(self._fetch_values_for_node, root)
            # Expand common MIB groups like system
            system_oid = "1.3.6.1.2.1.1"
            if system_oid in self.oid_to_item:
                self._expand_path_to_item(self.oid_to_item[system_oid])
                # Fetch values for system scalars
                self.executor.submit(self._fetch_values_for_node, self.oid_to_item[system_oid])
            # Ensure tree column width accommodates visible items
            self._ensure_tree_column_width()
        # If not connected or no data, leave empty
    
    def _build_tree_from_oids(self, parent: str, oids: Dict[str, Tuple[int, ...]]) -> None:
        """Recursively build the tree from OID dict."""
        # Filter out scalar instance OIDs (those ending with .0)
        # We'll show them as instance "0" in the parent OID row instead
        filtered_oids: Dict[str, Tuple[int, ...]] = {}
        scalar_instances: Dict[Tuple[int, ...], str] = {}  # base_oid -> instance_name

        for name, oid_tuple in oids.items():
            # Check if this looks like a scalar instance (name ends with "Inst" or "Inst_N")
            # and OID ends with .0
            if len(oid_tuple) > 0 and oid_tuple[-1] == 0 and ("Inst" in name):
                # This is a scalar instance - store it separately
                base_oid = oid_tuple[:-1]  # Remove the .0
                scalar_instances[base_oid] = name
            else:
                # Regular OID - keep it
                filtered_oids[name] = oid_tuple

        # Add base OIDs for scalars
        for base_oid, instance_name in scalar_instances.items():
            base_name = instance_name[:-4] if instance_name.endswith("Inst") else instance_name
            filtered_oids[base_name] = base_oid

        # Create a tree structure
        # Use a generic dict for the transient tree structure to satisfy static checkers
        tree: Dict[Any, Any] = {}
        for name, oid_tuple in filtered_oids.items():
            current = tree
            for num in oid_tuple:
                if num not in current:
                    current[num] = {}
                current = current[num]
            # At the leaf, store the name
            current['__name__'] = name
            # If this OID has a scalar instance, mark it
            if oid_tuple in scalar_instances:
                current['__has_instance__'] = True

        self._mark_tables(tree)

        # Now build the Treeview from the tree dict
        self._insert_tree_nodes(parent, tree, ())
    
    def _mark_tables(self, tree: Dict[Any, Any]) -> None:
        """Mark nodes that are table entries."""
        for key, value in list(tree.items()):
            if key in ('__name__', '__has_instance__', '__is_table__'):
                continue
            if isinstance(value, dict):
                if '__name__' in value and 'Table' in value['__name__']:
                    value['__is_table__'] = True
                self._mark_tables(value)
    
    def _insert_tree_nodes(self, parent: str, tree: Dict[Any, Any], current_oid: Tuple[int, ...], row_count: int = 0) -> int:
        """Insert nodes into Treeview recursively.

        Returns the updated row count for alternating row colors.
        """
        # Sort keys without comparing ints to strings (avoid TypeError)
        for key, value in sorted(tree.items(), key=lambda kv: (isinstance(kv[0], str), str(kv[0]))):
            if key == '__name__' or key == '__has_instance__':
                continue
            # Ensure key is an int before extending current_oid so typing stays as tuple[int, ...]
            if not isinstance(key, int):
                continue

            new_oid = current_oid + (key,)
            oid_str = ".".join(str(x) for x in new_oid)

            # Determine if this node is a leaf (only a name) or a folder (has children)
            child_keys = [k for k in value.keys() if k not in ('__name__', '__has_instance__')]
            is_leaf = len(child_keys) == 0

            # Prefer stored name for leaves, otherwise try name on this node
            stored_name = value.get('__name__')

            # Determine row color tag
            row_tag = "evenrow" if row_count % 2 == 0 else "oddrow"
            row_count += 1

            if is_leaf:
                # Check if this is a scalar with an instance
                has_instance = value.get('__has_instance__', False)

                if has_instance:
                    # Scalar - use base OID for access info
                    access = str(self.oid_metadata.get(oid_str, {}).get("access", "")).lower()
                    if "write" in access:
                        icon_key = "edit"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon_key = "lock"
                    else:
                        icon_key = "chart"
                    instance_str = "0"
                    instance_oid_str = oid_str + ".0"
                    val = self.oid_values.get(instance_oid_str, "")
                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "Unknown"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or "N/A"  # Use base OID
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"  # Use base OID
                else:
                    # Regular leaf
                    access = str(self.oid_metadata.get(oid_str, {}).get("access", "")).lower()
                    if "write" in access:
                        icon_key = "edit"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon_key = "lock"
                    else:
                        icon_key = "doc"
                    instance_str = ""
                    val = self.oid_values.get(oid_str, "")
                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "Unknown"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or "N/A"
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"

                display_text = stored_name if stored_name else str(key)

                # Add INDEX indicator to type column for known index columns
                if stored_name in ["ifIndex", "ifStackHigherLayer", "ifStackLowerLayer", "ifRcvAddressAddress"]:
                    type_val += " [INDEX]"

                # For Unknown types with no value, show "Empty Node" in Type column, not Value column
                if type_val == "Unknown" and not val:
                    type_val = "Empty Node"
                    display_val = ""
                else:
                    display_val = val
                    # Add enum name if available
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

                img = None
                if getattr(self, 'oid_icon_images', None):
                    img = self.oid_icon_images.get(icon_key)
                img_ref = cast(Any, img) if img is not None else ""

                node = self.oid_tree.insert(parent, "end", text=display_text, image=img_ref,
                                           values=(oid_str, instance_str, display_val, type_val, access_val, mib_val),
                                           tags=(row_tag,))
                self.oid_to_item[oid_str] = node
            else:
                # Folder/container node
                if value.get('__is_table__'):
                    icon_key = "table"
                    display_text = stored_name if stored_name else str(key)

                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "branch"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or ""
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"
                    img = None
                    if getattr(self, 'oid_icon_images', None):
                        img = self.oid_icon_images.get(icon_key)
                    img_ref = cast(Any, img) if img is not None else ""
                    node = self.oid_tree.insert(parent, "end", text=display_text, image=img_ref,
                                               values=(oid_str, "", "", type_val, access_val, mib_val),
                                               tags=(row_tag, 'table'))
                    self.oid_to_item[oid_str] = node
                    # Populate table instances immediately if we have the data
                    if hasattr(self, 'table_instances_data') and oid_str in self.table_instances_data:
                        self._log(f"Pre-populating table {oid_str} from table_instances_data", "DEBUG")
                        self._populate_table_instances_immediate(node, oid_str)
                    else:
                        if hasattr(self, 'table_instances_data'):
                            self._log(f"Table {oid_str} NOT in table_instances_data (have {len(self.table_instances_data)} tables)", "DEBUG")
                        else:
                            self._log(f"table_instances_data not loaded yet for table {oid_str}", "DEBUG")
                else:
                    icon_key = "folder"
                    display_text = stored_name if stored_name else str(key)

                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "branch"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or "N/A"
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"
                    img = None
                    if getattr(self, 'oid_icon_images', None):
                        img = self.oid_icon_images.get(icon_key)
                    img_ref = cast(Any, img) if img is not None else ""
                    node = self.oid_tree.insert(parent, "end", text=display_text, image=img_ref,
                                               values=(oid_str, "", "", type_val, access_val, mib_val),
                                               tags=(row_tag,))
                    self.oid_to_item[oid_str] = node
                    # Recurse into children
                    row_count = self._insert_tree_nodes(node, value, new_oid, row_count)

        return row_count

    def _on_node_open(self, event: Any) -> None:
        """Handler called when a tree node is expanded; fetch values for its immediate children."""
        try:
            item = event.widget.focus()
        except Exception:
            item = None

        if not item:
            return

        # Ensure the tree column is wide enough for this item
        self._ensure_oid_name_width(item)

        # Schedule background fetch for this node's children
        self.executor.submit(self._fetch_values_for_node, item)

        # Check if this is a table that needs instance discovery/refresh
        tags = self.oid_tree.item(item, 'tags')
        if 'table' in tags:
            # This is a table node - always refresh to show latest instances
            oid_str = self.oid_tree.set(item, "oid")
            if oid_str:
                children = self.oid_tree.get_children(item)
                if not children:
                    self._log(f"Table {oid_str} has no children, discovering instances...", "DEBUG")
                else:
                    self._log(f"Table {oid_str} has {len(children)} children, refreshing to show latest...", "INFO")
                # Always refresh table instances when expanding to show latest data
                self.executor.submit(self._discover_table_instances, item, oid_str)

    def _on_double_click(self, event: Any) -> None:
        """Handler called when a tree item is double-clicked; allows editing values for writable items."""
        try:
            item = self.oid_tree.identify_row(event.y)
        except Exception:
            return

        if not item:
            return

        # Check if this is a leaf node (no children)
        children = self.oid_tree.get_children(item)
        if children:
            # This is a container node (folder/table/entry), toggle expand/collapse
            if self.oid_tree.item(item, "open"):
                self.oid_tree.item(item, open=False)
            else:
                self.oid_tree.item(item, open=True)
            return

        # Get the OID and instance
        oid_str = self.oid_tree.set(item, "oid")
        instance_str = self.oid_tree.set(item, "instance")

        if not oid_str:
            return  # Not a leaf node

        # Check if this is a scalar with instance or regular leaf
        if instance_str:
            full_oid = f"{oid_str}.{instance_str}"
        else:
            full_oid = oid_str

        # Check if it's writable
        is_writable = self._is_oid_writable(full_oid)
        # Always show edit dialog - read-only items will have unlock checkbox

        # Get current value
        current_value = self.oid_tree.set(item, "value")

        # Show edit dialog
        self._show_edit_dialog(full_oid, current_value, item, is_writable)

    def _on_tree_select(self, event: Any) -> None:
        """Handler called when tree selection changes; populates Table View if table or table entry selected."""
        # If this selection wasn't from search, reset search state
        if not self._search_setting_selection:
            self._search_matches.clear()
            self._search_current_index = 0
            self._search_term = ""
        # Note: flag is reset by search code after this handler completes
        
        selected_items = self.oid_tree.selection()
        print(f"\n[DEBUG] _on_tree_select called, selected_items: {selected_items}")
        if not selected_items:
            # Don't hide table tab if user is currently on it (viewing/editing)
            try:
                current_tab = self.tabview.get()
                if current_tab == "Table View":
                    return
            except Exception:
                pass
            # Hide table tab if no selection
            if "Table View" in self.tabview._tab_dict:
                self.tabview.delete("Table View")
            self._update_selected_info(None)
            return

        # Check if any selected item is a table, table entry, or table column
        table_item = None
        table_entry_item = None
        selected_instance = None
        
        for item in selected_items:
            tags = self.oid_tree.item(item, 'tags')
            if 'table' in tags:
                table_item = item
                break
            elif 'table-entry' in tags:
                table_entry_item = item
                # Extract instance number from the instance column
                instance_str = self.oid_tree.set(item, "instance")
                if instance_str:
                    selected_instance = instance_str
                break
            elif 'table-column' in tags:
                # This is a column inside an entry, get the instance and find parent table
                instance_str = self.oid_tree.set(item, "instance")
                if instance_str:
                    selected_instance = instance_str
                # Find the parent entry
                parent = self.oid_tree.parent(item)
                if parent and 'table-entry' in self.oid_tree.item(parent, 'tags'):
                    table_entry_item = parent
                break

        # Update the selected item display for the first selected item
        print(f"[DEBUG] Calling _ensure_oid_name_width for item: {selected_items[0]}")
        self._ensure_oid_name_width(selected_items[0])
        self._update_selected_info(selected_items[0])

        if table_item or table_entry_item:
            # Determine which table to show
            if table_entry_item and not table_item:
                # Find the parent table
                parent = self.oid_tree.parent(table_entry_item)
                if parent and 'table' in self.oid_tree.item(parent, 'tags'):
                    table_item = parent
            
            if table_item:
                # Show table tab if not already shown
                if "Table View" not in self.tabview._tab_dict:
                    self.enable_table_tab()
                table_oid = self.oid_tree.set(table_item, "oid")
                self._log(
                    f"Table selection: table_oid={table_oid}, selected_instance={selected_instance}",
                    "DEBUG",
                )
                self._populate_table_view(table_item, selected_instance)
                # Enable add button
                self.add_instance_btn.configure(state="normal")
        else:
            # Don't hide table tab if user is currently on it (viewing/editing)
            try:
                current_tab = self.tabview.get()
                if current_tab == "Table View":
                    return
            except Exception:
                pass
            # Hide table tab if not on table-related item
            if "Table View" in self.tabview._tab_dict:
                self.tabview.delete("Table View")

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

        # For index columns, the value is already extracted and stored in the tree
        value_str = self.oid_tree.set(item, "value")
        if not value_str:
            try:
                resp = requests.get(
                    f"{self.api_url}/value",
                    params={"oid": full_oid},
                    timeout=2,
                )
                if resp.status_code == 200:
                    value_str = str(resp.json().get("value", ""))
                else:
                    value_str = "N/A"
            except Exception:
                value_str = "N/A"

        display = self._format_selected_info(full_oid, type_str, value_str)
        self._set_selected_info_text(display)

    def _ensure_tree_column_width(self) -> None:
        """Scan visible tree items and ensure column #0 is wide enough for all of them."""
        try:
            if getattr(self, "_oid_tree_user_resized", False):
                return  # User manually resized, don't auto-adjust
            
            max_width = int(self.oid_tree.column("#0", "width"))
            
            def check_item(item: str, depth: int = 0) -> int:
                """Recursively check item and its open children, return max width needed."""
                nonlocal max_width
                
                # Check this item
                text = self.oid_tree.item(item, "text")
                if text:
                    # Calculate text width
                    try:
                        font_obj = tkfont.Font(family='Helvetica', size=int(getattr(self, "tree_font_size", 22)))
                        text_width = font_obj.measure(str(text))
                    except Exception:
                        text_width = len(text) * 10
                    
                    indent_per_level = 20
                    icon_width = 20
                    padding = 40
                    indentation = depth * indent_per_level + icon_width
                    desired_width = indentation + text_width + padding
                    
                    if desired_width > max_width:
                        max_width = desired_width
                
                # Check children if item is open
                if self.oid_tree.item(item, "open"):
                    for child in self.oid_tree.get_children(item):
                        check_item(child, depth + 1)
                
                return max_width
            
            # Check all root items
            for root_item in self.oid_tree.get_children():
                check_item(root_item, 0)
            
            # Update column width if needed
            current_width = int(self.oid_tree.column("#0", "width"))
            if max_width > current_width:
                self.oid_tree.column("#0", width=max_width)
                
        except Exception as e:
            print(f"[DEBUG] Exception in _ensure_tree_column_width: {e}")

    def _ensure_oid_name_width(self, item: str) -> None:
        """Ensure the name column is wide enough to display the selected item's text."""
        try:
            # Only skip auto-expand if user manually resized
            if getattr(self, "_oid_tree_user_resized", False):
                print("[DEBUG] User manually resized, skipping auto-expansion")
                return
            text = self.oid_tree.item(item, "text") or ""
            if not text:
                print(f"[DEBUG] No text for item {item}, skipping expansion")
                return
            
            # Get the actual font size from our stored value
            size = getattr(self, "tree_font_size", 22)
            font = tkfont.Font(family="Helvetica", size=size)
            
            text_width = font.measure(text)
            
            # Calculate indentation based on depth in tree
            depth = 0
            parent = self.oid_tree.parent(item)
            while parent:
                depth += 1
                parent = self.oid_tree.parent(parent)
            
            # Standard tree values: ~20px indent per level, ~20px for icon/image
            indent_per_level = 20
            icon_width = 20
            indentation = depth * indent_per_level + icon_width
            
            # More generous padding to ensure text is fully visible
            padding = 40
            desired_width = indentation + text_width + padding
            current_width = int(self.oid_tree.column("#0", "width"))
            
            print("[DEBUG] _ensure_oid_name_width:")
            print(f"  text: '{text}'")
            print(f"  depth: {depth}, indentation: {indentation}px (indent/level: {indent_per_level}, icon: {icon_width})")
            print(f"  font size: {size}, text_width: {text_width}px")
            print(f"  padding: {padding}px")
            print(f"  desired_width: {indentation} + {text_width} + {padding} = {desired_width}px")
            print(f"  current_width: {current_width}px")
            
            if desired_width > current_width:
                print(f"  ACTION: Expanding column from {current_width} to {desired_width}")
                self.oid_tree.column("#0", width=desired_width)
            else:
                print(f"  ACTION: No expansion needed (desired {desired_width} <= current {current_width})")
        except Exception as e:
            print(f"[DEBUG] Exception in _ensure_oid_name_width: {e}")
            import traceback
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
        except Exception:
            return

    def _adjust_tree_font_size(self, delta: int) -> None:
        """Increase or decrease the tree font size and row height."""
        try:
            size = int(getattr(self, "tree_font_size", 22)) + delta
            size = max(12, min(34, size))
            self.tree_font_size = size
            self.tree_row_height = max(24, size + 8)
            style = ttk.Style()
            style.configure("Treeview", font=('Helvetica', size), rowheight=self.tree_row_height)
            style.configure("Treeview.Heading", font=('Helvetica', size + 1, 'bold'))
            # Update edit overlay fonts as well
            self.edit_overlay_combo.configure(font=("Helvetica", max(8, size - 1)))
            self.edit_overlay_entry.configure(font=("Helvetica", max(8, size - 1)))
            self._ensure_oid_name_width(self.oid_tree.focus())
        except Exception:
            pass

    def _format_selected_info(self, full_oid: str, type_str: str, value_str: str) -> str:
        """Format selected item display to match snmpget-like output with enum names."""
        if not full_oid.startswith("."):
            full_oid = "." + full_oid
        
        # Try to get enum name if this is an enum type
        enum_display = ""
        base_oid = full_oid.split(".0")[0] if full_oid.endswith(".0") else full_oid.rsplit(".", 1)[0]
        metadata = self.oid_metadata.get(base_oid, {})
        enums = metadata.get("enums")
        
        if enums and value_str and value_str not in ("N/A", "unset"):
            try:
                int_value = int(value_str)
                # Find enum name for this value
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
        columns_meta: Dict[str, Any],
    ) -> Dict[str, str]:
        """Decode index values from a dotted instance string."""
        if not index_columns:
            return {"__index__": instance or "1"}
        parts = instance.split(".") if instance else []
        values: Dict[str, str] = {}
        pos = 0
        for col_name in index_columns:
            if col_name == "__index__":
                values[col_name] = instance or "1"
                continue
            col_info = columns_meta.get(col_name, {}) if columns_meta else {}
            col_type = str(col_info.get("type", "")).lower()
            if col_type == "ipaddress":
                if pos + 4 <= len(parts):
                    values[col_name] = ".".join(parts[pos:pos + 4])
                    pos += 4
                else:
                    values[col_name] = instance
            else:
                if pos < len(parts):
                    values[col_name] = parts[pos]
                    pos += 1
                else:
                    values[col_name] = instance
        return values

    def _build_instance_from_index_values(
        self,
        index_values: Dict[str, str],
        index_columns: list[str],
        columns_meta: Dict[str, Any],
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
        try:
            self.selected_info_entry.configure(state="normal")
            self.selected_info_var.set(text)
            self.selected_info_entry.configure(state="readonly")
        except Exception:
            pass

    def _on_table_row_select(self, event: Any) -> None:
        """Handler called when table row selection changes."""
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
            except Exception:
                pass
        else:
            self.remove_instance_btn.configure(state="disabled")

    def _on_table_double_click(self, event: Any) -> None:
        """Handle double-click on table cell to enable in-place editing."""
        # Get the region that was clicked
        region = self.table_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        
        # Get the item and column that were clicked
        item = self.table_tree.identify_row(event.y)
        column = self.table_tree.identify_column(event.x)
        
        if not item or not column:
            return
        
        # Don't allow editing the index display column (column 0)
        col_num = int(column[1:]) - 1  # Convert #1, #2, etc to 0, 1, etc
        if col_num == 0:
            return
        
        # Get current value
        values = self.table_tree.item(item, "values")
        if col_num >= len(values):
            return
        
        current_value = str(values[col_num])
        
        # Show edit overlay
        self._show_edit_overlay(event, item, column, current_value)
    
    def _show_edit_overlay(self, event: Any, item: str, column: str, current_value: str) -> None:
        """Show edit overlay at the clicked cell location."""
        # Hide any existing overlay first
        self._hide_edit_overlay()
        
        # Get the bounding box of the cell (relative to treeview)
        bbox = self.table_tree.bbox(item, column)
        if not bbox:
            return
        
        cell_x, cell_y, cell_width, cell_height = bbox
        
        # Get absolute screen coordinates for the treeview
        tree_rootx = self.table_tree.winfo_rootx()
        tree_rooty = self.table_tree.winfo_rooty()
        
        # Get absolute screen coordinates for the root window
        root_rootx = self.root.winfo_rootx()
        root_rooty = self.root.winfo_rooty()
        
        # Calculate overlay position relative to root window
        overlay_x = tree_rootx + cell_x - root_rootx
        overlay_y = tree_rooty + cell_y - root_rooty
        
        # Store references for later
        self.editing_item = item
        self.editing_column = column
        
        # Position and show the overlay relative to root window
        self.edit_overlay_frame.place(x=overlay_x, y=overlay_y, width=cell_width, height=cell_height)
        self.edit_overlay_frame.lift()  # Bring to front
        
        # Check if this column has enum metadata
        enum_values: list[str] = []
        if hasattr(self, '_current_table_columns'):
            col_num = int(column[1:]) - 1  # Convert #1, #2, etc to 0-indexed
            # Adjust for "index" display column - column #1 is "index", #2 is columns[0], etc.
            data_col_index = col_num - 1
            columns = self._current_table_columns
            if 0 <= data_col_index < len(columns):
                col_name, col_oid, _ = columns[data_col_index]
                metadata = self.oid_metadata.get(col_oid, {})
                enums = metadata.get("enums", {})
                if enums:
                    # Build list of "value (name)" strings, sorted by value
                    enum_values = [f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])]
        
        # Use Entry for non-enum fields, Combobox for enums
        if enum_values:
            # Hide entry, show combo
            self.edit_overlay_entry.pack_forget()
            self.edit_overlay_combo.pack(padx=2, pady=2, fill="both", expand=True)
            
            self.edit_overlay_combo.config(values=enum_values, state="readonly")
            # Find and select the matching value
            for enum_val in enum_values:
                if enum_val.startswith(current_value.split()[0]):  # Match the integer part
                    self.edit_overlay_combo.set(enum_val)
                    break
            
            # Unbind all previous events first
            self.edit_overlay_combo.unbind("<Return>")
            self.edit_overlay_combo.unbind("<Escape>")
            self.edit_overlay_combo.unbind("<<ComboboxSelected>>")
            self.edit_overlay_combo.unbind("<FocusOut>")
            
            # Bind keys for save/cancel
            self.edit_overlay_combo.bind("<Return>", lambda e: self._save_cell_edit())
            self.edit_overlay_combo.bind("<Escape>", lambda e: self._hide_edit_overlay())
            self.edit_overlay_combo.bind("<<ComboboxSelected>>", lambda e: self._on_combo_selected())
            self.edit_overlay_combo.bind("<FocusOut>", lambda e: self._on_edit_focus_out())
            
            self.edit_overlay_combo.focus()
        else:
            # Hide combo, show entry
            self.edit_overlay_combo.pack_forget()
            self.edit_overlay_entry.pack(padx=2, pady=2, fill="both", expand=True)
            
            self.edit_overlay_entry.delete(0, "end")
            self.edit_overlay_entry.insert(0, current_value)
            self.edit_overlay_entry.selection_range(0, "end")
            
            # Unbind all previous events first
            self.edit_overlay_entry.unbind("<Return>")
            self.edit_overlay_entry.unbind("<Escape>")
            self.edit_overlay_entry.unbind("<FocusOut>")
            
            # Bind keys for save/cancel
            self.edit_overlay_entry.bind("<Return>", lambda e: self._save_cell_edit())
            self.edit_overlay_entry.bind("<Escape>", lambda e: self._hide_edit_overlay())
            self.edit_overlay_entry.bind("<FocusOut>", lambda e: self._on_edit_focus_out())
            
            self.edit_overlay_entry.focus()
    
    def _on_table_click(self, event: Any) -> None:
        """Handle click on table - save edit if clicking outside edit area."""
        if not self.editing_item:
            return
        # Check if click is outside the edit overlay
        try:
            widget = event.widget.winfo_containing(event.x_root, event.y_root)
            # If click is not in the edit widgets, save the edit
            if widget not in (self.edit_overlay_combo, self.edit_overlay_entry):
                self._save_cell_edit()
        except Exception:
            pass
    
    def _on_table_configure(self, event: Any) -> None:
        """Handle table configuration changes (resize, scroll) - hide edit overlay."""
        if self.editing_item:
            self._save_cell_edit()
    
    def _on_combo_selected(self) -> None:
        """Handle combobox selection - save immediately.

        CRITICAL INSIGHT from testing: On macOS, FocusOut fires BEFORE ComboboxSelected!
        By the time we get here, the dropdown grab is already released.
        We can save immediately without any lockup.
        """
        if not self.editing_item:
            return

        self._log("DEBUG: Combo selected - saving immediately", "DEBUG")
        # Save immediately - the grab is already released by this point
        self._save_cell_edit()

    def _on_edit_focus_out(self) -> None:
        """Handle focus leaving edit entry.

        On macOS, this fires BEFORE ComboboxSelected, so we don't save here.
        For text entry fields (non-combo), we still need to save on FocusOut.
        """
        self._log("DEBUG: Edit focus out event (happens before ComboboxSelected on macOS)", "DEBUG")

        # Only save if this is NOT a combobox selection
        # (For text entry fields, we still need FocusOut to trigger save)
        if self.editing_item and not hasattr(self, '_combo_just_selected'):
            self._log("DEBUG: FocusOut triggering save for text entry", "DEBUG")
            self.root.after(50, self._save_cell_edit)
    
    def _hide_edit_overlay(self) -> None:
        """Hide the edit overlay and cancel editing."""
        self._log("DEBUG: _hide_edit_overlay called", "DEBUG")
        
        # DO NOT unbind events - this causes deadlock when called from event handlers
        # The handlers check editing_item to know if they should do anything
        
        # Hide the overlay
        self.edit_overlay_frame.place_forget()
        self._log("DEBUG: Overlay frame hidden", "DEBUG")
        
        # Clear editing state - this disables all event handlers
        self.editing_item = None
        self.editing_column = None
        self.editing_oid = None
        self._log("DEBUG: Editing state cleared", "DEBUG")
        
        # DO NOT try to set focus - let tkinter handle focus naturally
        # Forcing focus changes during dropdown closure causes focus deadlock
        
        self._log("DEBUG: _hide_edit_overlay complete", "DEBUG")
    
    
    def _save_cell_edit(self) -> None:
        """Save the edited cell value."""
        # Guard against multiple calls and re-entry
        if not self.editing_item or not self.editing_column or self._saving_cell:
            self._log("DEBUG: _save_cell_edit blocked - already saving or no edit active", "DEBUG")
            return
        
        # Set flag to prevent re-entry
        self._saving_cell = True
        self._log("DEBUG: _save_cell_edit STARTED", "DEBUG")
        
        try:
            # Store editing context
            editing_item = self.editing_item
            editing_column = self.editing_column
            
            # Get value from whichever widget is packed (entry or combo)
            if self.edit_overlay_combo.winfo_ismapped():
                new_value = self.edit_overlay_combo.get()
                self._log(f"DEBUG: Got value from combo: {new_value}", "DEBUG")
            else:
                new_value = self.edit_overlay_entry.get()
                self._log(f"DEBUG: Got value from entry: {new_value}", "DEBUG")
            
            # Parse enum format "value (name)" to extract just the integer value
            if ' (' in new_value and new_value.endswith(')'):
                # Extract the value part before the opening parenthesis
                new_value = new_value.split(' (')[0]
                self._log(f"DEBUG: Parsed enum value: {new_value}", "DEBUG")
            
            # Get the item's values to construct the OID
            item_values = self.table_tree.item(editing_item, "values")
            col_num = int(editing_column[1:]) - 1  # Convert #1, #2, etc to 0, 1, etc
            
            self._log(f"DEBUG: Saving cell edit - col_num={col_num}, new_value={new_value}", "DEBUG")
            
            # Try to get table info and construct OID
            # We need to find the column name and table OID from context
            # Get the current table being shown
            if not hasattr(self, '_current_table_columns'):
                self._log("ERROR: _current_table_columns not found", "ERROR")
                return
            
            columns = self._current_table_columns  # (name, col_oid, col_num)
            # col_num is the treeview column number (0=index, 1=first data col, etc)
            # We need to map this to the columns array (0-indexed)
            data_col_index = col_num - 1  # Subtract 1 because col 0 is the index display
            
            if data_col_index < 0 or data_col_index >= len(columns):
                self._log(f"ERROR: data_col_index {data_col_index} out of bounds (columns len={len(columns)})", "ERROR")
                messagebox.showerror("Error", "Column index out of bounds")
                return  # This will trigger finally to clean up
            
            col_name, col_oid, _ = columns[data_col_index]
            instance_index = item_values[0]  # First value is the instance index

            index_columns = getattr(self, "_current_index_columns", [])
            columns_meta = getattr(self, "_current_columns_meta", {})
            table_oid = getattr(self, "_current_table_oid", None)
            
            # Prepare column_values dict for API calls
            column_values: Dict[str, str] = {}
            
            if col_name in index_columns:
                # For index column updates, we need to delete old instance and create new one
                if not table_oid:
                    messagebox.showerror("Error", "Table OID not available")
                    return  # This will trigger finally to clean up
                
                # Build old index values from current instance
                old_index_values: Dict[str, str] = self._extract_index_values(
                    instance_index, index_columns, columns_meta
                )
                
                # Build new index values with the updated value
                updated_values = list(item_values)
                updated_values[col_num] = new_value
                new_index_values: Dict[str, str] = {}
                for idx_name in index_columns:
                    try:
                        idx_pos = [c[0] for c in columns].index(idx_name)
                        new_index_values[idx_name] = str(updated_values[1 + idx_pos])
                    except ValueError:
                        new_index_values[idx_name] = "unset"
                
                # Get all non-index column values
                column_values = {}
                for i, (c_name, _, _) in enumerate(columns):
                    if c_name not in index_columns:
                        val = str(updated_values[1 + i])
                        # Strip enum format "value (name)" if present
                        if ' (' in val and val.endswith(')'):
                            val = val.split(' (')[0]
                        column_values[c_name] = val
                
                try:
                    # Delete old instance
                    self._log("DEBUG: Calling DELETE /table-row for index update", "DEBUG")
                    del_resp = requests.delete(
                        f"{self.api_url}/table-row",
                        json={
                            "table_oid": table_oid,
                            "index_values": old_index_values,
                            "column_values": {}
                        },
                        timeout=5,
                    )
                    self._log(f"DEBUG: DELETE response: {del_resp.status_code}", "DEBUG")
                    
                    if del_resp.status_code != 200:
                        messagebox.showerror("Error", f"Failed to delete old instance: {del_resp.text}")
                        return

                    # Immediately remove old instance from OID tree
                    old_instance_str = ".".join(str(old_index_values[k]) for k in index_columns)
                    if hasattr(self, "_current_table_item") and self._current_table_item:
                        self._remove_instance_from_oid_tree(self._current_table_item, old_instance_str)

                    # Create new instance with new index values
                    self._log("DEBUG: Calling POST /table-row for index update", "DEBUG")
                    create_resp = requests.post(
                        f"{self.api_url}/table-row",
                        json={
                            "table_oid": table_oid,
                            "index_values": new_index_values,
                            "column_values": column_values
                        },
                        timeout=5,
                    )

                    if create_resp.status_code == 200:
                        self._log(f"Updated index {col_name} from {old_index_values[col_name]} to {new_value}")
                        # Refresh the entire table view
                        if hasattr(self, "_current_table_item") and self._current_table_item:
                            new_instance = ".".join(
                                str(new_index_values.get(idx_name, "")) for idx_name in index_columns
                            )
                            self._populate_table_view(self._current_table_item, new_instance)
                            # Immediately add new instance to OID tree (will handle sorting)
                            self._add_instance_to_oid_tree(self._current_table_item, new_instance)
                            if table_oid:
                                self._set_pending_oid_focus(table_oid, new_instance, col_oid)
                    else:
                        messagebox.showerror("Error", f"Failed to create new instance: {create_resp.text}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to update index: {e}")
                    self._log(f"Error updating index: {e}", "ERROR")
            else:
                # For non-index column updates, use the table-row API
                # which handles both creating and updating cell values
                
                # Extract current index values
                index_values = self._extract_index_values(
                    instance_index, index_columns, columns_meta
                )
                
                # Build current column values from the row
                column_values = {}
                for i, (c_name, _, _) in enumerate(columns):
                    if c_name not in index_columns:
                        # Use the new value for the column being edited, current value for others
                        if c_name == col_name:
                            column_values[c_name] = new_value
                        else:
                            # Get current value from the table display
                            col_index = i + 1  # +1 because column 0 is the index display
                            if col_index < len(item_values):
                                val = str(item_values[col_index])
                                # Strip enum format "value (name)" if present
                                if ' (' in val and val.endswith(')'):
                                    val = val.split(' (')[0]
                                column_values[c_name] = val
                            else:
                                column_values[c_name] = "unset"
                
                try:
                    # Check if this instance exists in the OID tree before saving
                    # If it doesn't exist, we're creating a new instance
                    full_oid = f"{col_oid}.{instance_index}"
                    is_new_instance = full_oid not in self.oid_values

                    # Use table-row endpoint to update (creates if doesn't exist)
                    self._log(f"DEBUG: Calling POST /table-row for cell update (col={col_name}, val={new_value}, new_instance={is_new_instance})", "DEBUG")
                    resp = requests.post(
                        f"{self.api_url}/table-row",
                        json={
                            "table_oid": table_oid,
                            "index_values": index_values,
                            "column_values": column_values
                        },
                        timeout=5,
                    )
                    self._log(f"DEBUG: POST response: {resp.status_code}", "DEBUG")

                    if resp.status_code == 200:
                        self._log("DEBUG: Starting UI update for cell", "DEBUG")
                        # Format value with enum name if applicable
                        display_value = new_value
                        col_metadata = self.oid_metadata.get(col_oid, {})
                        enums = col_metadata.get("enums")
                        if enums and new_value:
                            try:
                                int_value = int(new_value)
                                for enum_name, enum_value in enums.items():
                                    if enum_value == int_value:
                                        display_value = f"{new_value} ({enum_name})"
                                        break
                            except (ValueError, TypeError):
                                pass

                        # Update the cell display
                        updated_values = list(item_values)
                        updated_values[col_num] = display_value
                        self.table_tree.item(editing_item, values=updated_values)
                        self._log("DEBUG: Cell display updated in treeview", "DEBUG")
                        self._log(f"Updated {col_name} (OID {full_oid}) to: {new_value}")
                        # Also update the oid_values cache
                        self.oid_values[full_oid] = new_value
                        self._log("DEBUG: Cache updated, cell save complete", "DEBUG")

                        # Refresh the OID tree to show the updated value
                        self._refresh_oid_tree_value(full_oid, display_value)
                        if table_oid:
                            self._set_pending_oid_focus(table_oid, str(instance_index), col_oid)

                        # If this was a new instance, also refresh the entire table to show the new row
                        if is_new_instance and hasattr(self, "_current_table_item") and self._current_table_item:
                            self._log("DEBUG: New instance detected, refreshing OID tree table", "DEBUG")
                            self._refresh_oid_tree_table(self._current_table_item)
                    else:
                        error_msg = f"Failed to update value: {resp.status_code} - {resp.text}"
                        self._log(error_msg, "ERROR")
                        messagebox.showerror("Error", error_msg)
                except Exception as e:
                    error_msg = f"Failed to update cell via table-row API: {e}"
                    self._log(error_msg, "ERROR")
                    messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Failed to save cell: {e}"
            self._log(error_msg, "ERROR")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", error_msg)
        finally:
            # Clear the saving flag
            self._log("DEBUG: Entering finally block - clearing flag", "DEBUG")
            self._saving_cell = False
            # Clear the combo selection flag
            self._combo_just_selected = False
            # CRITICAL for macOS: Use a time delay (not after_idle) to hide the overlay.
            # On macOS, the dropdown maintains a modal grab that persists even after
            # all events are processed. We need a real time delay (150ms) to ensure
            # the grab is fully released before hiding the widget.
            self.root.after(150, self._hide_edit_overlay)
            self._log("DEBUG: finally block complete, hide deferred 150ms", "DEBUG")

    def _populate_table_view(self, table_item: str, selected_instance: str | None = None) -> None:
        """Populate the table view with data from the selected table."""
        oid_str = self.oid_tree.set(table_item, "oid")
        if not oid_str:
            self._log("No OID found for table item", "WARNING")
            return

        preserved_yview = None
        if self.table_tree.winfo_exists():
            preserved_yview = self.table_tree.yview()
        if selected_instance is None:
            selected_rows = self.table_tree.selection()
            if selected_rows:
                selected_values = self.table_tree.item(selected_rows[0], "values")
                if selected_values:
                    selected_instance = str(selected_values[0])

        # Preserve current column widths to avoid jarring resizes on refresh
        existing_columns = self.table_tree["columns"]
        preserved_widths: dict[str, int] = {}
        for col_id in existing_columns:
            try:
                preserved_widths[col_id] = int(self.table_tree.column(col_id, "width"))
            except Exception:
                continue

        # Clear existing
        for child in self.table_tree.get_children():
            self.table_tree.delete(child)

        # Find entry OID (assume .1 is the entry)
        entry_oid = oid_str + ".1"
        entry_tuple = tuple(int(x) for x in entry_oid.split("."))

        # Find entry name
        entry_name = None
        for name, oid_t in self.oids_data.items():
            if oid_t == entry_tuple:
                entry_name = name
                break
        if not entry_name:
            entry_name = "Entry"

        # Get columns
        columns = []
        for name, oid_t in self.oids_data.items():
            if oid_t[:len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                col_num = oid_t[-1]
                col_oid = ".".join(str(x) for x in oid_t)
                columns.append((name, col_oid, col_num))
        columns.sort(key=lambda x: x[2])

        if not columns:
            self._log(f"No columns found for table {oid_str}", "WARNING")
            return
        
        self._log(f"Found {len(columns)} columns for table {oid_str}")

        # Get table schema including instances from API
        index_columns: list[str] = []
        schema: Dict[str, Any] = {}  # Initialize to empty dict
        try:
            resp = requests.get(f"{self.api_url}/table-schema", params={"oid": oid_str}, timeout=5)
            if resp.status_code == 200:
                schema = resp.json()
                instances = schema.get("instances", [])
                index_columns = schema.get("index_columns", [])
                if not index_columns:
                    index_columns = ["__index__"]
                self._log(
                    f"Loaded {len(instances)} instances from table schema for {oid_str}: "
                    f"instances={instances}, index_columns={index_columns}",
                    "DEBUG",
                )
            else:
                self._log("Failed to get table schema, using fallback discovery", "WARNING")
                instances = self._discover_instances_fallback(columns[0][1])
        except Exception as e:
            self._log(f"Error loading table schema: {e}, using fallback discovery", "WARNING")
            instances = self._discover_instances_fallback(columns[0][1])

        def _instance_sort_key(inst: Any) -> list[tuple[int, Any]]:
            parts = str(inst).split(".")
            key: list[tuple[int, Any]] = []
            for part in parts:
                if part.isdigit():
                    key.append((0, int(part)))
                else:
                    key.append((1, part))
            return key

        instances = sorted(instances, key=_instance_sort_key)

        # Set columns
        col_names = [col[0] for col in columns]
        self.table_tree["columns"] = ("index",) + tuple(col_names)
        index_header = "__Index__" if index_columns == ["__index__"] else "Index"
        self.table_tree.heading("index", text=index_header)
        
        # Calculate column widths - use preserved if available, otherwise distribute available width
        # Initialize defaults
        index_width = 120
        col_width = 150
        
        if preserved_widths:
            # Use preserved widths
            index_width = preserved_widths.get("index", 100)
        else:
            # Calculate widths to fill available space
            try:
                available_width = self.table_tree.winfo_width()
                if available_width <= 1:  # Not yet rendered
                    available_width = 800  # Reasonable default
                # Reserve width for scrollbar
                available_width -= 20
                # Give index column slightly more space, distribute rest evenly
                index_width = max(120, int(available_width * 0.15))
                remaining_width = available_width - index_width
                col_width = max(100, int(remaining_width / len(col_names))) if col_names else 150
            except Exception:
                index_width = 120
                col_width = 150
        
        self.table_tree.column("index", width=index_width, minwidth=50, stretch=False, anchor="w")
        
        index_column_set = {name.lower() for name in index_columns}
        for i, col_name in enumerate(col_names):
            if col_name.lower() in index_column_set:
                header_text = f"🔑 {col_name}"
            else:
                header_text = col_name
            self.table_tree.heading(col_name, text=header_text)
            if preserved_widths:
                width = preserved_widths.get(col_name, 150)
            else:
                width = col_width
            # Make last column stretch to fill remaining space
            is_last = (i == len(col_names) - 1)
            self.table_tree.column(col_name, width=width, minwidth=100, stretch=is_last, anchor="w")
        
        # Store columns for later use in cell editing
        self._current_table_columns = columns
        self._current_index_columns = index_columns
        self._current_columns_meta = schema.get("columns", {})
        self._current_table_item = table_item
        self._current_table_oid = oid_str

        # Populate rows
        row_items = []
        index_column_set = {name.lower() for name in index_columns}
        columns_meta = schema.get("columns", {})
        for inst in instances:
            values = [inst]
            inst_str = str(inst)
            index_values = self._extract_index_values(inst_str, index_columns, columns_meta)
            for name, col_oid, col_num in columns:
                if name.lower() in index_column_set:
                    val = index_values.get(name, inst_str)
                else:
                    full_oid = f"{col_oid}.{inst_str}"
                    try:
                        resp = requests.get(
                            f"{self.api_url}/value",
                            params={"oid": full_oid},
                            timeout=1,
                        )
                        if resp.status_code == 200:
                            val = resp.json().get("value", "unset")
                        else:
                            val = "unset"
                    except Exception:
                        val = "unset"
                    
                    # Add enum name if available
                    if val not in ("unset", "N/A", ""):
                        col_metadata = self.oid_metadata.get(col_oid, {})
                        enums = col_metadata.get("enums")
                        if enums:
                            try:
                                int_value = int(val)
                                for enum_name, enum_value in enums.items():
                                    if enum_value == int_value:
                                        val = f"{val} ({enum_name})"
                                        break
                            except (ValueError, TypeError):
                                pass
                
                values.append(val)
            item = self.table_tree.insert("", "end", values=values)
            row_items.append((inst, item))

        # Select the row corresponding to selected_instance if provided
        found_selection = False
        if selected_instance:
            for inst, item in row_items:
                if inst == selected_instance:
                    self.table_tree.selection_set(item)
                    self.table_tree.see(item)
                    # Enable remove button since we have a selection
                    self.remove_instance_btn.configure(state="normal")
                    found_selection = True
                    self._set_pending_oid_focus(oid_str, str(selected_instance))
                    break

        if not found_selection and preserved_yview is not None:
            self.table_tree.yview_moveto(preserved_yview[0])
        
        # Enable "Add Index Column" button only for no-index tables  
        is_no_index_table = all(col.startswith("__index") for col in index_columns) if index_columns else True
        if is_no_index_table:
            self.add_index_col_btn.configure(state="normal")
        else:
            self.add_index_col_btn.configure(state="disabled")

    def _discover_instances_fallback(self, first_col_oid: str) -> list[str]:
        """Fallback method to discover table instances by trying sequential indexes.
        
        This is used when the table-schema API doesn't return instances.
        Only works for simple single-index tables.
        """
        instances: list[str] = []
        index = 1
        max_attempts = 20  # Limit the number of attempts to prevent infinite loading
        while len(instances) < max_attempts:
            try:
                resp = requests.get(f"{self.api_url}/value", params={"oid": first_col_oid + "." + str(index)}, timeout=1)
                if resp.status_code == 200:
                    instances.append(str(index))
                    index += 1
                else:
                    break
            except Exception as e:
                self._log(f"Error loading instance {index}: {e}", "DEBUG")
                break
        
        if len(instances) == max_attempts:
            self._log("Reached maximum attempts while discovering instances", "WARNING")
        
        return instances

    def _add_instance(self) -> None:
        """Add a new instance to the current table."""
        try:
            # Get current table OID from the selected item in oid_tree
            selected_items = self.oid_tree.selection()
        except Exception as e:
            messagebox.showerror("Error", f"Error getting selected item: {e}")
            return
        if not selected_items:
            selected_items = ()
        table_item = None
        for item in selected_items:
            if 'table' in self.oid_tree.item(item, 'tags'):
                table_item = item
                break
            if 'table-entry' in self.oid_tree.item(item, 'tags'):
                parent = self.oid_tree.parent(item)
                if parent and 'table' in self.oid_tree.item(parent, 'tags'):
                    table_item = parent
                    break
            if 'table-column' in self.oid_tree.item(item, 'tags'):
                parent = self.oid_tree.parent(item)
                if parent and 'table-entry' in self.oid_tree.item(parent, 'tags'):
                    table_parent = self.oid_tree.parent(parent)
                    if table_parent and 'table' in self.oid_tree.item(table_parent, 'tags'):
                        table_item = table_parent
                        break
        if not table_item:
            table_item = getattr(self, "_current_table_item", None)
        if not table_item:
            messagebox.showwarning("No Table Selected", "Select a table or table entry first.")
            return

        table_oid = self.oid_tree.set(table_item, "oid")
        if not table_oid:
            return

        # Get table schema to find index columns
        try:
            resp = requests.get(f"{self.api_url}/table-schema", params={"oid": table_oid}, timeout=5)
            if resp.status_code != 200:
                messagebox.showerror("Error", "Failed to get table schema")
                return
            schema = resp.json()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get schema: {e}")
            return

        # Find index columns - use actual column names from schema
        index_columns = []
        for col_name in schema.get("index_columns", []):
            if col_name in schema.get("columns", {}):
                col_info = schema["columns"][col_name]
                index_columns.append((col_name, col_info))

        # Check if this is an augmented table
        index_from = schema.get("index_from", [])
        if index_from:
            # This is an augmented table - cannot add instances directly
            parent_info = index_from[0] if index_from else {}
            parent_mib = parent_info.get("mib", "Unknown MIB")
            parent_col = parent_info.get("column", "Unknown")
            messagebox.showerror(
                "Cannot Add to Augmented Table",
                f"This table (indexed by {parent_col}) is an augmented table that inherits instances from {parent_mib}.\n\n"
                f"You cannot add instances directly to this table. Instead, add instances to the parent table in {parent_mib}, "
                f"and the new instances will automatically appear here."
            )
            return

        # Fallback if no index columns found (shouldn't happen with proper schema)
        if not index_columns:
            messagebox.showerror("Error", "Table has no index columns in schema")
            return

        # Get non-key column values from the last row
        instances = schema.get("instances", [])
        columns_meta = schema.get("columns", {})
        index_column_names = [name for name, _ in index_columns]
        column_defaults = {}

        if instances:
            # Get the last instance
            last_instance = instances[-1]

            # Fetch values for all non-index columns from the last row
            for col_name, col_info in columns_meta.items():
                # Skip index columns
                if col_name in index_column_names:
                    continue
                    
                # This is a non-key column, get its value from the last row
                col_oid = ".".join(str(x) for x in col_info["oid"])
                full_oid = f"{col_oid}.{last_instance}"

                try:
                    resp = requests.get(f"{self.api_url}/value", params={"oid": full_oid}, timeout=5)
                    if resp.status_code == 200:
                        value_data = resp.json()
                        column_defaults[col_name] = str(value_data.get("value", "unset"))
                    else:
                        column_defaults[col_name] = "unset"
                except Exception as e:
                    self._log(f"Could not fetch value for {col_name}: {e}", "WARNING")
                    column_defaults[col_name] = "unset"
        else:
            # No existing instances, default all non-index columns to "unset"
            for col_name, col_info in columns_meta.items():
                # Skip index columns
                if col_name not in index_column_names:
                    column_defaults[col_name] = "unset"

        # Create dialog for index values
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Add Table Instance")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Title
        title_label = ctk.CTkLabel(dialog, text=f"Add instance to {schema.get('name', table_oid)}", font=("", 14, "bold"))
        title_label.pack(pady=10)

        # Frame for inputs
        input_frame = ctk.CTkFrame(dialog)
        input_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # State for dynamic index fields
        entries = {}
        index_field_widgets = []  # Track widgets for cleanup
        num_index_parts = len(index_columns) if index_columns else 1
        
        def get_next_default() -> str:
            """Calculate default for the last index field based on existing instances."""
            instances = [str(inst) for inst in schema.get("instances", [])]
            columns_meta = schema.get("columns", {})
            if not instances:
                return "1"
            
            # Get all values for the last part of multi-part indexes
            numeric_vals: list[int] = []
            for inst in instances:
                parts = str(inst).split(".")
                if parts:
                    last_part = parts[-1]
                    if last_part.isdigit():
                        numeric_vals.append(int(last_part))
            
            if numeric_vals:
                return str(max(numeric_vals) + 1)
            return "1"
        
        def render_index_fields() -> None:
            """Render index entry fields dynamically."""
            nonlocal num_index_parts
            
            # Clear existing widgets
            for widget_list in index_field_widgets:
                for widget in widget_list:
                    widget.destroy()
            index_field_widgets.clear()
            entries.clear()
            
            # Create entry fields for each index column
            for i in range(num_index_parts):
                if i < len(index_columns):
                    col_name, col_info = index_columns[i]
                else:
                    # Shouldn't happen if num_index_parts matches index_columns
                    col_name = f"index{i}"
                    col_info = {}
                
                # Label with actual column name
                label = ctk.CTkLabel(input_frame, text=f"{col_name}:")
                label.grid(row=i, column=0, sticky="w", pady=5, padx=10)
                
                # Entry
                entry = ctk.CTkEntry(input_frame)
                default_val = get_next_default() if i == num_index_parts - 1 else "1"
                entry.insert(0, default_val)
                entry.grid(row=i, column=1, sticky="ew", pady=5, padx=(0, 10))
                
                # Store entry using actual column name
                entries[col_name] = entry
                index_field_widgets.append([label, entry])
            
            # Add +/- buttons row
            button_row = num_index_parts
            
            add_btn = ctk.CTkButton(input_frame, text="+", width=40, command=add_index_part)
            add_btn.grid(row=button_row, column=0, pady=5, padx=10, sticky="w")
            
            remove_btn = ctk.CTkButton(input_frame, text="-", width=40, command=remove_index_part)
            remove_btn.grid(row=button_row, column=1, pady=5, padx=(0, 10), sticky="w")
            if num_index_parts <= 1:
                remove_btn.configure(state="disabled")
            
            index_field_widgets.append([add_btn, remove_btn])
            
            input_frame.columnconfigure(1, weight=1)
        
        def add_index_part() -> None:
            """Add another index part field."""
            nonlocal num_index_parts
            num_index_parts += 1
            render_index_fields()
        
        def remove_index_part() -> None:
            """Remove the last index part field (minimum 1)."""
            nonlocal num_index_parts
            if num_index_parts > 1:
                num_index_parts -= 1
                render_index_fields()
        
        # Initial render
        render_index_fields()

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_cancel() -> None:
            dialog.destroy()

        def on_add() -> None:
            # Collect index values using actual column names
            index_values = {}
            index_parts_ordered = []  # Keep track of order for building instance_str
            for i, (col_name, col_info) in enumerate(index_columns[:num_index_parts]):
                if col_name not in entries:
                    continue
                val = entries[col_name].get().strip()
                if not val:
                    messagebox.showerror("Error", f"{col_name} cannot be empty")
                    return
                # Store using actual column name
                index_values[col_name] = val
                index_parts_ordered.append(val)

            # Create the table row using the new endpoint
            try:
                payload = {
                    "table_oid": table_oid,
                    "index_values": index_values,
                    "column_values": column_defaults  # Copy non-key values from last row
                }
                resp = requests.post(f"{self.api_url}/table-row", json=payload, timeout=5)
                if resp.status_code == 200:
                    result = resp.json()
                    messagebox.showinfo("Success", f"Instance added successfully: {result.get('instance_oid')}")
                    # Refresh table view
                    self._populate_table_view(table_item)
                    # Immediately add to OID tree
                    instance_str = ".".join(index_parts_ordered)
                    self._add_instance_to_oid_tree(table_item, instance_str)
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", f"Failed to add instance: {resp.text}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add instance: {e}")

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = ctk.CTkButton(button_frame, text="Add", command=on_add)
        add_btn.pack(side="right")

    def _add_index_column(self) -> None:
        """Add an extra index column to a no-index table by recreating all instances."""
        table_item = getattr(self, "_current_table_item", None)
        if not table_item:
            messagebox.showwarning("No Table Selected", "Select a table first.")
            return

        table_oid = self.oid_tree.set(table_item, "oid")
        if not table_oid:
            return

        # Get table schema
        try:
            resp = requests.get(f"{self.api_url}/table-schema", params={"oid": table_oid}, timeout=5)
            if resp.status_code != 200:
                messagebox.showerror("Error", "Failed to get table schema")
                return
            schema = resp.json()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get schema: {e}")
            return

        instances = schema.get("instances", [])
        if not instances:
            messagebox.showinfo("No Instances", "Table has no instances. Add instances first, then add more index columns.")
            return
        
        index_columns = schema.get("index_columns", [])
        columns_meta = schema.get("columns", {})
        
        # Determine current number of index parts
        current_parts = len(index_columns) if index_columns else 1
        
        # Prompt for default value for the new index part
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Add Index Column")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Add index part #{current_parts + 1}", font=("", 14, "bold")).pack(pady=10)
        ctk.CTkLabel(dialog, text=f"This will recreate all {len(instances)} instances\nwith an extra index part.", font=("", 11)).pack(pady=5)

        input_frame = ctk.CTkFrame(dialog)
        input_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(input_frame, text="Default value for new index part:").pack(side="left", padx=(0, 10))
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
            
            # Process each instance: delete and recreate with extra index part
            success_count = 0
            fail_count = 0
            
            for inst in instances:
                try:
                    # Parse current index parts
                    current_index_parts = str(inst).split(".")
                    
                    # Build current index_values dict
                    current_index_values = {}
                    for i, part in enumerate(current_index_parts):
                        col_name = "__index__" if i == 0 else f"__index_{i + 1}__"
                        current_index_values[col_name] = part
                    
                    # Get current column values for this instance
                    column_values = {}
                    for col_name, col_info in columns_meta.items():
                        if col_name.startswith("__index"):
                            continue
                        col_oid = ".".join(str(x) for x in col_info["oid"])
                        full_oid = f"{col_oid}.{inst}"
                        try:
                            resp = requests.get(f"{self.api_url}/value", params={"oid": full_oid}, timeout=5)
                            if resp.status_code == 200:
                                value_data = resp.json()
                                column_values[col_name] = str(value_data.get("value", ""))
                        except Exception:
                            pass
                    
                    # Delete old instance
                    del_payload = {
                        "table_oid": table_oid,
                        "index_values": current_index_values
                    }
                    resp = requests.delete(f"{self.api_url}/table-row", json=del_payload, timeout=5)
                    if resp.status_code != 200:
                        self._log(f"Failed to delete instance {inst}: {resp.text}", "WARNING")
                        fail_count += 1
                        continue
                    
                    # Create new instance with extra index part
                    new_index_values = current_index_values.copy()
                    new_col_name = f"__index_{current_parts + 1}__" if current_parts > 0 else "__index_2__"
                    new_index_values[new_col_name] = default_val
                    
                    create_payload = {
                        "table_oid": table_oid,
                        "index_values": new_index_values,
                        "column_values": column_values
                    }
                    resp = requests.post(f"{self.api_url}/table-row", json=create_payload, timeout=5)
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        self._log(f"Failed to recreate instance {inst}: {resp.text}", "WARNING")
                        fail_count += 1
                        
                except Exception as e:
                    self._log(f"Error processing instance {inst}: {e}", "ERROR")
                    fail_count += 1
            
            # Show result
            if fail_count == 0:
                messagebox.showinfo("Success", f"Added index column to {success_count} instances")
            else:
                messagebox.showwarning("Partial Success", f"Updated {success_count} instances, {fail_count} failed")
            
            # Refresh both views
            self._populate_table_view(table_item)
            self._populate_oid_tree()

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = ctk.CTkButton(button_frame, text="Add Column", command=on_add_column, fg_color="green", hover_color="darkgreen")
        add_btn.pack(side="right")

    def _remove_instance(self) -> None:
        """Remove the selected instance from the table."""
        try:
            selected_rows = self.table_tree.selection()
            if not selected_rows:
                messagebox.showwarning("No Selection", "Please select an instance to remove.")
                return
            
            # Get table OID from current table item
            if not hasattr(self, "_current_table_item") or self._current_table_item is None:
                messagebox.showerror("Error", "No table selected")
                return
            
            try:
                table_oid = self.oid_tree.set(self._current_table_item, "oid")
            except Exception as e:
                messagebox.showerror("Error", f"Could not get table OID: {e}")
                return
            
            if not table_oid:
                messagebox.showerror("Error", "Table OID not found")
                return
            
            # Check if this is an augmented table
            try:
                resp = requests.get(f"{self.api_url}/table-schema", params={"oid": table_oid}, timeout=5)
                if resp.status_code == 200:
                    schema = resp.json()
                    index_from = schema.get("index_from", [])
                    if index_from:
                        # This is an augmented table - cannot remove instances directly
                        parent_info = index_from[0] if index_from else {}
                        parent_mib = parent_info.get("mib", "Unknown MIB")
                        parent_col = parent_info.get("column", "Unknown")
                        messagebox.showerror(
                            "Cannot Remove from Augmented Table",
                            f"This table (indexed by {parent_col}) is an augmented table that inherits instances from {parent_mib}.\n\n"
                            f"You cannot remove instances from this table. Instead, remove instances from the parent table in {parent_mib}, "
                            f"and the instances will automatically be removed from here."
                        )
                        return
            except Exception as e:
                self._log(f"Error checking if table is augmented: {e}", "WARNING")
                # Continue anyway - if we can't verify, let the user try
            
            # Confirm deletion
            if len(selected_rows) == 1:
                msg = "Are you sure you want to delete this instance?"
            else:
                msg = f"Are you sure you want to delete {len(selected_rows)} instances?"
            
            if not messagebox.askyesno("Confirm Deletion", msg):
                return
            
            # Delete each selected instance
            deleted_count = 0
            failed_count = 0
            
            for selected_item in selected_rows:
                try:
                    # Get the row values
                    values = self.table_tree.item(selected_item, "values")
                    if not values:
                        failed_count += 1
                        continue
                    
                    # First value is the instance string
                    instance_str = values[0]
                    
                    # Extract index values from the instance string
                    index_columns = getattr(self, "_current_index_columns", [])
                    columns_meta = getattr(self, "_current_columns_meta", {})
                    
                    index_values = self._extract_index_values(instance_str, index_columns, columns_meta)
                    
                    # Call DELETE /table-row endpoint
                    payload = {
                        "table_oid": table_oid,
                        "index_values": index_values
                    }
                    resp = requests.delete(f"{self.api_url}/table-row", json=payload, timeout=5)
                    
                    if resp.status_code == 200:
                        deleted_count += 1
                        self._log(f"Deleted instance: {instance_str}", "INFO")
                        # Immediately remove from OID tree
                        if self._current_table_item:
                            self._remove_instance_from_oid_tree(self._current_table_item, instance_str)
                    else:
                        failed_count += 1
                        self._log(f"Failed to delete instance {instance_str}: {resp.text}", "ERROR")
                except Exception as e:
                    failed_count += 1
                    self._log(f"Error deleting instance: {e}", "ERROR")
            
            # Show result and refresh
            if deleted_count > 0:
                messagebox.showinfo("Success", f"Deleted {deleted_count} instance(s)")
                # Refresh table view
                if self._current_table_item is not None:
                    self._populate_table_view(self._current_table_item)
            
            if failed_count > 0:
                messagebox.showwarning("Partial Failure", f"Failed to delete {failed_count} instance(s)")
        
        except Exception as e:
            messagebox.showerror("Error", f"Error removing instance: {e}")
            self._log(f"Error in _remove_instance: {e}", "ERROR")

    def _show_edit_dialog(self, oid: str, current_value: str, item: str, is_writable: bool) -> None:
        """Show a dialog to edit the value of an OID."""
        # DEBUG: Print what we're getting
        print(f"DEBUG: _show_edit_dialog called with oid={oid}, is_writable={is_writable}")

        # Strip instance suffix for metadata lookup
        base_oid = oid.split('.')[:-1] if '.' in oid and oid.split('.')[-1].isdigit() else oid
        base_oid_str = '.'.join(base_oid) if isinstance(base_oid, list) else base_oid

        # Get the type information from metadata
        metadata = self.oid_metadata.get(base_oid_str, {})
        value_type = metadata.get("type", "Unknown")
        access = metadata.get("access", "read-only").lower()

        print(f"DEBUG: Looking up metadata for base_oid={base_oid_str}, found metadata={metadata}")

        # Check if this is an index/key column
        type_from_tree = self.oid_tree.set(item, "type")
        is_index = "[INDEX]" in type_from_tree

        if is_index:
            messagebox.showinfo("Cannot Edit", "Index/key columns cannot be edited.")
            return

        # Create custom dialog using customtkinter
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Edit OID Value")
        dialog.geometry("450x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        # dialog.grab_set()  # Commented out for testing multiple dialogs

        # Center the dialog
        dialog.geometry("+{}+{}".format(
            self.root.winfo_x() + (self.root.winfo_width() // 2) - 225,
            self.root.winfo_y() + (self.root.winfo_height() // 2) - 150
        ))

        # Main frame with padding
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        title_label = ctk.CTkLabel(main_frame, text="Edit OID Value",
                                 font=ctk.CTkFont(size=16, weight="bold"))
        title_label.pack(pady=(0, 15))

        # OID info
        info_text = f"OID: {oid}\nType: {value_type}"
        info_label = ctk.CTkLabel(main_frame, text=info_text, justify="left",
                                font=ctk.CTkFont(size=11))
        info_label.pack(anchor="w", pady=(0, 10))

        # Current value
        current_text = f"Current: {current_value}"
        current_label = ctk.CTkLabel(main_frame, text=current_text, justify="left",
                                   font=ctk.CTkFont(size=11))
        current_label.pack(anchor="w", pady=(0, 15))

        # New value section
        value_label = ctk.CTkLabel(main_frame, text="New value:", font=ctk.CTkFont(weight="bold"))
        value_label.pack(anchor="w")

        # Check if this OID has enum metadata
        enums = metadata.get("enums", {})
        value_var = ctk.StringVar(value=current_value)
        value_widget: Any  # Will be either CTkEntry or CTkComboBox
        
        if enums:
            # Create dropdown with enum values in "value (name)" format
            enum_values = [f"{val} ({name})" for name, val in sorted(enums.items(), key=lambda x: x[1])]
            value_widget = ctk.CTkComboBox(main_frame, variable=value_var, values=enum_values, width=400, state="readonly")
            # Find and set the current value
            for enum_val in enum_values:
                if enum_val.startswith(current_value.split()[0]):  # Match the integer part
                    value_var.set(enum_val)
                    break
        else:
            # Create text entry for non-enum values
            value_widget = ctk.CTkEntry(main_frame, textvariable=value_var, width=400)
        
        value_widget.pack(pady=(5, 10), fill="x")

        # Track if value has changed from original
        original_value = current_value
        value_changed = ctk.BooleanVar(value=False)

        def on_value_change(*args: Any) -> None:
            """Enable OK button only if value is different from original."""
            current = value_var.get()
            changed = current != original_value
            value_changed.set(changed)
            ok_button.configure(state="normal" if changed else "disabled")

        # Bind to value changes
        value_var.trace_add("write", on_value_change)

        # Bottom frame for checkbox and buttons
        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", pady=(15, 0))

        # Unlock checkbox (only for read-only items) - left side
        unlock_var = ctk.BooleanVar(value=False)
        unlock_checkbox = None

        # Only show checkbox for read-only items
        # write-only and read-write items don't need a checkbox
        show_checkbox = (access == "read-only")

        print(f"DEBUG: access={access}, show_checkbox={show_checkbox}")

        if show_checkbox:
            print("DEBUG: Creating unlock checkbox for read-only item")
            def on_checkbox_toggle() -> None:
                """Handle checkbox toggle - reset value when unchecked."""
                unlocked = unlock_var.get()
                if not unlocked:
                    # Reset to original value when unchecked
                    value_var.set(original_value)
                self._toggle_entry_state(value_widget, unlocked)

            unlock_checkbox = ctk.CTkCheckBox(bottom_frame, text="Unlock for editing",
                                            variable=unlock_var,
                                            command=on_checkbox_toggle)
            unlock_checkbox.pack(side="left", anchor="w")
            value_widget.configure(state="disabled")  # Start disabled
            print("DEBUG: Checkbox created and packed, entry disabled")
        else:
            print(f"DEBUG: No checkbox needed for {access} OID")

        # Buttons - right side
        def on_ok() -> None:
            new_value = value_var.get()
            if new_value is not None:
                # For read-only items, only allow if unlocked
                if show_checkbox and not unlock_var.get():
                    messagebox.showwarning("Read-Only", "Please check 'Unlock for editing' to modify this read-only object.")
                    return
                # Only proceed if value has actually changed
                if not value_changed.get():
                    messagebox.showinfo("No Change", "Value has not been modified.")
                    return
                # Parse enum format "value (name)" to extract just the integer value
                if ' (' in new_value and new_value.endswith(')'):
                    new_value = new_value.split(' (')[0]
                # Send the new value to the API
                self._set_oid_value(oid, new_value, item)
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        # Button container for right alignment
        button_container = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        button_container.pack(side="right")

        cancel_button = ctk.CTkButton(button_container, text="Cancel", command=on_cancel, width=80)
        cancel_button.pack(side="right", padx=(10, 0))

        ok_button = ctk.CTkButton(button_container, text="OK", command=on_ok, width=80, state="disabled")
        ok_button.pack(side="right")

        # Focus handling
        if not show_checkbox:
            # For write-only and read-write, widget is enabled by default
            value_widget.focus()
            # Only select text for entry widgets (not combobox)
            if not enums and hasattr(value_widget, 'select_range'):
                value_widget.select_range(0, 'end')
        elif unlock_checkbox:
            # For read-only, focus on checkbox
            unlock_checkbox.focus()

        # Bind keys
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())

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
            parts = oid_str.split('.')
            # Find which schema has this OID as a table entry
            for table_name, table_data in self.table_schemas.items():
                table_oid = '.'.join(str(x) for x in table_data.get("oid", []))
                entry_oid = '.'.join(str(x) for x in table_data.get("entry_oid", []))
                
                # Check if this OID starts with the entry OID
                if oid_str.startswith(entry_oid + '.'):
                    # This is a table column instance OID
                    # Extract column index and instance index from the end
                    entry_parts = entry_oid.split('.')
                    num_indices = len(table_data.get("index_columns", []))
                    
                    # Column index is the next part after entry
                    if len(parts) > len(entry_parts) + num_indices:
                        column_index = int(parts[len(entry_parts)])
                        # Find the column name by matching the OID
                        for col_name, col_data in table_data.get("columns", {}).items():
                            col_oid = '.'.join(str(x) for x in col_data.get("oid", []))
                            col_oid_parts = col_oid.split('.')
                            if len(col_oid_parts) > len(entry_parts):
                                if int(col_oid_parts[len(entry_parts)]) == column_index:
                                    # Extract instance (remaining parts)
                                    instance = '.'.join(parts[len(entry_parts) + 1:])
                                    return (table_oid, col_name, instance)
        except Exception as e:
            self._log(f"Error decomposing table OID {oid_str}: {e}", "DEBUG")
        
        return None

    def _set_oid_value(self, oid: str, new_value: str, item: str) -> None:
        """Set the value for an OID via the API.
        
        Handles both scalar OIDs and table column OIDs by routing to appropriate endpoint.
        """
        try:
            self._log(f"Setting value for OID {oid} to: {new_value}")
            
            # First try as a scalar OID
            resp = requests.post(f"{self.api_url}/value",
                               json={"oid": oid, "value": new_value},
                               timeout=5)
            
            # If 404, try as a table column OID
            if resp.status_code == 404:
                decomposed = self._decompose_table_oid(oid)
                if decomposed:
                    table_oid, column_name, instance = decomposed
                    # Convert instance string to index dict
                    # For simple single-index tables, instance is just the index value
                    # For multi-index tables, instance is dot-separated values
                    schema = self.table_schemas.get(None)  # Find matching schema
                    index_cols = []
                    for schema_name, schema_data in self.table_schemas.items():
                        if schema_data.get("oid") and '.'.join(str(x) for x in schema_data["oid"]) == table_oid:
                            index_cols = schema_data.get("index_columns", [])
                            break
                    
                    # Build index_values dict
                    index_values = {}
                    instance_parts = instance.split('.')
                    for i, col_name in enumerate(index_cols):
                        if i < len(instance_parts):
                            index_values[col_name] = instance_parts[i]
                    
                    # Call table-row endpoint
                    self._log(f"Trying table-row endpoint: table_oid={table_oid}, index_values={index_values}, column={column_name}")
                    resp = requests.post(f"{self.api_url}/table-row",
                                       json={
                                           "table_oid": table_oid,
                                           "index_values": index_values,
                                           "column_values": {column_name: new_value}
                                       },
                                       timeout=5)
            
            resp.raise_for_status()
            result = resp.json()

            # Log the API response for debugging
            self._log(f"API response: {result}")

            # Update the local value cache
            self.oid_values[oid] = new_value

            # Update the UI with formatted value (include enum name if applicable)
            display_value = new_value
            # Get metadata to check for enums
            base_oid = oid.rsplit('.', 1)[0] if '.' in oid else oid
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
        except Exception as e:
            error_msg = f"Unexpected error setting value for OID {oid}: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Set Error", error_msg)

    def _is_oid_writable(self, oid: str) -> bool:
        """Check if an OID is writable based on metadata."""
        # Strip instance suffix (e.g., .0) for metadata lookup
        base_oid = oid.split('.')[:-1] if '.' in oid and oid.split('.')[-1].isdigit() else oid
        base_oid_str = '.'.join(base_oid) if isinstance(base_oid, list) else base_oid

        metadata = self.oid_metadata.get(base_oid_str, {})
        access = metadata.get("access", "").lower()
        result = access in ["read-write", "readwrite", "write-only", "writeonly"]

        # DEBUG: Print what we're checking
        print(f"DEBUG: _is_oid_writable({oid}) -> base_oid={base_oid_str}, access='{access}', result={result}")

        return result

    def _on_search_first(self, event: Any = None) -> None:
        """Start a new search or continue if search term changed."""
        search_term = self.search_var.get().strip()
        if not search_term:
            messagebox.showwarning("Search", "Please enter a search term")
            return

        if search_term == self._search_term and self._search_matches:
            self._search_current_index = (self._search_current_index + 1) % len(self._search_matches)
            self._show_search_match(self._search_current_index)
            return
        
        # Depth-first traversal of tree structure, including metadata for unloaded nodes
        matches: list[tuple[str, str]] = []
        seen_oids: set[str] = set()
        
        def dfs_search(item: str) -> None:
            """Recursively search tree in depth-first order, including metadata."""
            # Get OID from values column
            item_values = self.oid_tree.item(item, "values")
            base_oid = item_values[0] if item_values else ""
            
            # For entry nodes, construct full OID from table + instance
            # Entry nodes store (table_oid, instance, ...) in values
            item_tags = self.oid_tree.item(item, "tags")
            is_entry = "table-entry" in item_tags
            oid = base_oid
            if is_entry and len(item_values) >= 2:
                table_oid = item_values[0]
                instance = item_values[1]
                if table_oid and instance:
                    oid = f"{table_oid}.{instance}"
            
            # Get display name
            item_text = self.oid_tree.item(item, "text")
            
            # Check if this node matches
            if oid and oid not in seen_oids:
                if (search_term.lower() in item_text.lower() or
                    search_term in oid or
                    search_term.lower() in oid.lower()):
                    matches.append((oid, item_text))
                    seen_oids.add(oid)
            
            # Recursively search visible children in tree FIRST (before metadata)
            # This ensures proper depth-first order
            for child_item in self.oid_tree.get_children(item):
                dfs_search(child_item)
            
            # Then check metadata for unloaded children (only for non-entry nodes)
            # Entry nodes shouldn't search metadata because their children are loaded
            if oid and not is_entry:
                for oid_str, metadata in self.oid_metadata.items():
                    if oid_str not in seen_oids and oid_str.startswith(oid + "."):
                        # This is a potential child
                        name = metadata.get("name", "")
                        mib = metadata.get("mib", "")
                        obj_type = metadata.get("type", "")
                        display_name = name if name else oid_str
                        
                        # Skip table entry definitions (e.g., table.1) from metadata
                        # Entry instances (e.g., table.192.168.1.1.1) are tree nodes, but
                        # the entry definition OID itself is metadata-only
                        if "SEQUENCE" in obj_type and "Entry" in name:
                            continue
                        
                        if (search_term.lower() in name.lower() or
                            search_term.lower() in mib.lower() or
                            search_term in oid_str or
                            search_term.lower() in oid_str.lower()):
                            matches.append((oid_str, display_name))
                            seen_oids.add(oid_str)
        
        # Start search from root
        root_items = self.oid_tree.get_children("")
        for root_item in root_items:
            dfs_search(root_item)
        
        if not matches:
            messagebox.showinfo("Search", f"No matches found for '{search_term}'")
            self._search_matches.clear()
            self._search_term = ""
            return
        
        # Store matches and show first one
        self._search_matches = matches
        self._search_current_index = 0
        self._search_term = search_term
        
        # Show the first match
        self._show_search_match(0)
        
        self._log(f"Found {len(matches)} match(es) for '{search_term}'")
    
    def _on_search_next(self) -> None:
        """Show the next search match."""
        if not self._search_matches:
            return
        
        # Move to next match (with wrapping)
        self._search_current_index = (self._search_current_index + 1) % len(self._search_matches)
        self._show_search_match(self._search_current_index)
    
    def _show_search_match(self, index: int) -> None:
        """Display the search match at the given index. Loads missing hierarchy if needed."""
        if index >= len(self._search_matches):
            return
        
        oid_str, display_name = self._search_matches[index]
        match_num = index + 1
        total_matches = len(self._search_matches)
        
        # If already in tree, just select it (works for any node: OID, table, entry, or column)
        if oid_str in self.oid_to_item:
            item_id = self.oid_to_item[oid_str]
            self._expand_path_to_item(item_id)
            self.oid_tree.see(item_id)
            self._search_setting_selection = True  # Mark that we're setting selection from search
            self.oid_tree.selection_set(item_id)
            self._ensure_oid_name_width(item_id)
            self._log(f"Match {match_num}/{total_matches}: {display_name} ({oid_str})")
            # Reset flag after tree has processed the selection
            self.root.after(10, lambda: setattr(self, '_search_setting_selection', False))
            return
        
        # Not yet in tree - need to load the hierarchy. Find deepest loaded ancestor.
        oid_parts = oid_str.split('.')
        deepest_parent_oid = None
        for depth in range(len(oid_parts), 0, -1):
            parent_oid = ".".join(oid_parts[:depth])
            if parent_oid in self.oid_to_item:
                deepest_parent_oid = parent_oid
                break
        
        if deepest_parent_oid is None:
            self._log(f"Match {match_num}/{total_matches} (root not found): {display_name} ({oid_str})")
            return
        
        # Expand the parent and load children
        parent_item = self.oid_to_item[deepest_parent_oid]
        parent_tags = self.oid_tree.item(parent_item, 'tags')
        is_table_parent = 'table' in parent_tags
        
        # Show loading message for tables since they take longer
        if is_table_parent:
            self._log(f"Loading table {deepest_parent_oid}...", "INFO")
        
        self.oid_tree.item(parent_item, open=True)
        self.oid_tree.update_idletasks()
        
        # Now load children by calling the node open handler
        event_mock = type('Event', (), {'widget': self.oid_tree})()
        self._on_node_open(event_mock)
        
        # Wait for children to load, then try to select target
        # Tables need longer wait times due to HTTP requests
        max_retries = 20 if is_table_parent else 10
        base_wait = 200 if is_table_parent else 100
        long_wait = 500 if is_table_parent else 300
        
        def attempt_select(retry_count: int = 0) -> None:
            # Check both oid_to_item AND if item exists in tree widget
            if oid_str in self.oid_to_item:
                item_id = self.oid_to_item[oid_str]
                try:
                    # Verify item actually exists in tree
                    self.oid_tree.item(item_id)
                    # Item exists, select it
                    self._expand_path_to_item(item_id)
                    self.oid_tree.see(item_id)
                    self._search_setting_selection = True  # Mark that we're setting selection from search
                    self.oid_tree.selection_set(item_id)
                    self._ensure_oid_name_width(item_id)
                    self._log(f"Match {match_num}/{total_matches}: {display_name} ({oid_str})")
                    # Reset flag after tree has processed the selection
                    self.root.after(10, lambda: setattr(self, '_search_setting_selection', False))
                    return
                except tk.TclError:
                    # Item in dict but not in tree widget yet
                    pass
            
            # Show progress for tables (every 5 retries)
            if is_table_parent and retry_count > 0 and retry_count % 5 == 0:
                self._log(f"Still loading table... ({retry_count}/{max_retries})", "DEBUG")
            
            # Retry with exponential backoff
            if retry_count < max_retries:
                wait_time = base_wait if retry_count < 3 else long_wait
                self.root.after(wait_time, lambda: attempt_select(retry_count + 1))
            else:
                self._search_setting_selection = False  # Reset flag on failure
                self._log(f"Match {match_num}/{total_matches} (could not load): {display_name} ({oid_str})")
        
        self.root.after(base_wait, attempt_select)

    def _expand_path_to_oid(self, target_oid: Tuple[int, ...]) -> None:
        """Expand the tree path to make the given OID visible."""
        if not self.oids_data:
            return

        # Build the full path by checking each prefix of the target OID
        path_oids = []
        for i in range(1, len(target_oid) + 1):
            partial_oid = target_oid[:i]
            oid_str = ".".join(str(x) for x in partial_oid)
            # Check if this OID exists in our data
            if oid_str in self.oid_to_item:
                path_oids.append(oid_str)

        # Expand each node in the path from root to target
        for path_oid in path_oids:
            if path_oid in self.oid_to_item:
                item = self.oid_to_item[path_oid]
                # Expand this node
                self.oid_tree.item(item, open=True)
                # Force UI update
                self.oid_tree.update_idletasks()

    def _expand_path_to_item(self, item: str) -> None:
        """Expand all ancestors of the given item."""
        path = []
        current = item
        while current:
            path.append(current)
            current = self.oid_tree.parent(current)
        path.reverse()
        for node in path:
            self.oid_tree.item(node, open=True)
            # If this is a table node with placeholder, trigger table discovery
            if 'table' in self.oid_tree.item(node, 'tags'):
                children = self.oid_tree.get_children(node)
                if children and 'placeholder' in self.oid_tree.item(children[0], 'tags'):
                    oid_str = self.oid_tree.set(node, "oid")
                    if oid_str:
                        self.executor.submit(self._discover_table_instances, node, oid_str)

    def _populate_table_instances_immediate(self, table_item: str, table_oid: str) -> None:
        """Pre-populate table instances from bulk-loaded data."""
        try:
            if table_oid not in self.table_instances_data:
                self._log(f"Cannot pre-populate {table_oid}: not in table_instances_data", "DEBUG")
                return
            
            table_data = self.table_instances_data[table_oid]
            instances = table_data.get("instances", [])
            entry_name = table_data.get("entry_name", "Entry")
            index_columns = table_data.get("index_columns", [])
            
            self._log(f"Pre-populating table {table_oid}: {len(instances)} instances", "DEBUG")
            
            if not instances:
                self._log(f"No instances to pre-populate for {table_oid}", "DEBUG")
                return
            
            # Find entry OID (table + .1)
            entry_oid = table_oid + ".1"
            entry_tuple = tuple(int(x) for x in entry_oid.split("."))
            
            # Get columns for this table
            columns = []
            for name, oid_t in self.oids_data.items():
                if oid_t[:len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                    col_num = oid_t[-1]
                    col_oid = ".".join(str(x) for x in oid_t)
                    columns.append((name, col_oid, col_num))
            columns.sort(key=lambda x: x[2])
            
            # Build columns metadata for index value extraction
            columns_meta: dict[str, Any] = {}
            for col_name, col_oid, _ in columns:
                col_metadata = self.oid_metadata.get(col_oid, {})
                columns_meta[col_name] = col_metadata
            
            index_column_set = {name.lower() for name in index_columns}
            
            # Sort instances using same logic as table view
            def _instance_sort_key(inst: Any) -> list[tuple[int, Any]]:
                parts = str(inst).split(".")
                key: list[tuple[int, Any]] = []
                for part in parts:
                    if part.isdigit():
                        key.append((0, int(part)))
                    else:
                        key.append((1, part))
                return key
            
            instances = sorted(instances, key=_instance_sort_key)
            
            # Group columns by instance
            for inst in instances:
                entry_display = f"{entry_name}.{inst}"
                entry_item = self.oid_tree.insert(
                    table_item,
                    "end",
                    text=entry_display,
                    values=(table_oid, inst, "", "Entry", "N/A", self.oid_metadata.get(table_oid, {}).get("mib") or "N/A"),
                    tags=("table-entry",),
                )
                # Track entry in oid_to_item with the entry OID (table.instance)
                entry_oid = f"{table_oid}.{inst}"
                self.oid_to_item[entry_oid] = entry_item
                
                # Extract index values for this instance
                index_values = self._extract_index_values(inst, index_columns, columns_meta)
                
                # Add columns under the entry
                for name, col_oid, col_num in columns:
                    full_col_oid = f"{col_oid}.{inst}"
                    is_index = name.lower() in index_column_set
                    
                    # Get value - either from index or from bulk loaded values
                    if is_index:
                        value_here = index_values.get(name, "N/A")
                    else:
                        value_here = self.oid_values.get(full_col_oid, "unset")
                    
                    access = str(self.oid_metadata.get(col_oid, {}).get("access", "")).lower()
                    type_str = self.oid_metadata.get(col_oid, {}).get("type") or "Unknown"
                    access_str = self.oid_metadata.get(col_oid, {}).get("access") or "N/A"
                    
                    # Determine icon
                    if is_index:
                        icon_key = "key"
                    elif "write" in access:
                        icon_key = "edit"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon_key = "lock"
                    else:
                        icon_key = "chart"
                    
                    img = None
                    if getattr(self, 'oid_icon_images', None):
                        img = self.oid_icon_images.get(icon_key)
                    mib_val = self.oid_metadata.get(col_oid, {}).get("mib") or "N/A"
                    img_ref = cast(Any, img) if img is not None else ""
                    
                    tags = ("evenrow", "table-column", "table-index") if is_index else ("evenrow", "table-column")
                    col_item = self.oid_tree.insert(
                        entry_item,
                        "end",
                        text=name,
                        image=img_ref,
                        values=(col_oid, inst, value_here, type_str, access_str, mib_val),
                        tags=tags,
                    )
                    # Track column in oid_to_item with the full column OID (table.column.instance)
                    self.oid_to_item[full_col_oid] = col_item
                    # Also store base column OID for search purposes
                    # (search finds base OIDs without instances in metadata)
                    if col_oid not in self.oid_to_item:
                        self.oid_to_item[col_oid] = col_item
            
            self._log(f"Pre-populated {len(instances)} instances for table {table_oid}", "DEBUG")
            # Ensure tree column is wide enough for new items
            self._ensure_tree_column_width()
            
        except Exception as e:
            self._log(f"Error pre-populating table {table_oid}: {e}", "WARNING")
            import traceback
            traceback.print_exc()

    def _discover_table_instances(self, item: str, entry_oid: str) -> None:
        """Discover table instances and populate the tree."""
        self._log(f"Discovering table instances for table OID {entry_oid}", "DEBUG")

        # Find the entry name
        entry_name = None
        entry_tuple = tuple(int(x) for x in (entry_oid + '.1').split("."))
        for name, oid_t in self.oids_data.items():
            if oid_t == entry_tuple:
                entry_name = name
                break
        
        if not entry_name:
            self._log(f"Could not find name for entry OID {entry_oid}.1", "WARNING")
            entry_name = "Entry"  # fallback
        
        # Find the first column OID
        first_col_oid = None
        for name, oid_t in self.oids_data.items():
            if oid_t[:len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                first_col_oid = ".".join(str(x) for x in oid_t)
                break
        if not first_col_oid:
            self._log(f"No columns found for table {entry_oid}", "WARNING")
            return

        instances: list[str] = []
        index_columns: list[str] = []
        try:
            resp = requests.get(f"{self.api_url}/table-schema", params={"oid": entry_oid}, timeout=5)
            if resp.status_code == 200:
                schema = resp.json()
                instances = [str(inst) for inst in schema.get("instances", [])]
                index_columns = list(schema.get("index_columns", []))
                self._log(
                    f"Table schema loaded for {entry_oid}: found {len(instances)} instances: {instances}, index_columns={index_columns}",
                    "INFO",
                )
            else:
                self._log(
                    f"Table schema request failed for {entry_oid}: {resp.status_code} {resp.text}",
                    "WARNING",
                )
        except Exception as e:
            self._log(f"Error loading table schema for {entry_oid}: {e}", "WARNING")

        if not instances:
            index = 1
            max_attempts = 20  # Limit the number of attempts to prevent infinite loading
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
                except Exception:
                    break

            if len(instances) == max_attempts:
                messagebox.showwarning("Warning", "Reached maximum attempts while loading instances.")

            self._log(
                f"Fallback instance discovery used for {entry_oid}: instances={instances}",
                "DEBUG",
            )

        # Get columns
        columns = []
        for name, oid_t in self.oids_data.items():
            if oid_t[:len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                col_num = oid_t[-1]
                col_oid = ".".join(str(x) for x in oid_t)
                columns.append((name, col_oid, col_num))
        columns.sort(key=lambda x: x[2])

        # Sort instances using same logic as table view
        def _instance_sort_key(inst: Any) -> list[tuple[int, Any]]:
            parts = str(inst).split(".")
            key: list[tuple[int, Any]] = []
            for part in parts:
                if part.isdigit():
                    key.append((0, int(part)))
                else:
                    key.append((1, part))
            return key
        
        instances = sorted(instances, key=_instance_sort_key)

        # Build columns metadata dict for index value extraction
        columns_meta: Dict[str, Any] = {}
        for name, col_oid, col_num in columns:
            if name in index_columns:
                col_metadata = self.oid_metadata.get(col_oid, {})
                columns_meta[name] = col_metadata
        
        grouped: Dict[str, List[Tuple[str, str, str, str, bool]]] = {}
        # Extract index values once per instance for efficiency
        instances_index_values: Dict[str, Dict[str, str]] = {}
        for inst in instances:
            instances_index_values[inst] = self._extract_index_values(inst, index_columns, columns_meta)
        
        for inst in instances:
            grouped[inst] = []
            for name, col_oid, col_num in columns:
                full_col_oid = f"{col_oid}.{inst}"
                is_index = name.lower() in {idx.lower() for idx in index_columns}

                # Check if value is already loaded (from bulk or previous fetch)
                if full_col_oid in self.oid_values:
                    value_here = self.oid_values[full_col_oid]
                    if is_index:
                        # Get the actual index value for display
                        value_here = instances_index_values[inst].get(name, "N/A")
                else:
                    # Not loaded yet - try to fetch it once
                    if is_index:
                        # Get the actual index value for display
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
                                # Mark as attempted to avoid repeated failures
                                value_here = "unset"
                                self.oid_values[full_col_oid] = value_here
                        except Exception:
                            # Mark as attempted to avoid repeated failures
                            value_here = "unset"
                            self.oid_values[full_col_oid] = value_here
                grouped[inst].append((name, col_oid, full_col_oid, value_here, is_index))

        # Update UI
        def update_ui() -> None:
            # Remove existing children
            existing_children = self.oid_tree.get_children(item)
            self._log(f"Removing {len(existing_children)} existing children from table", "DEBUG")
            for child in existing_children:
                self.oid_tree.delete(child)

            # Add entry nodes under the table
            self._log(f"Adding {len(grouped)} new instances to OID tree: {list(grouped.keys())}", "INFO")
            index_column_set = {name.lower() for name in index_columns}
            added_count = 0
            for inst, cols in grouped.items():
                entry_display = f"{entry_name}.{inst}"
                # Store table OID (not including instance) - _update_selected_info will append instance
                mib_val = self.oid_metadata.get(entry_oid, {}).get("mib") or "N/A"
                entry_item = self.oid_tree.insert(
                    item,
                    "end",
                    text=entry_display,
                    values=(entry_oid, inst, "", "Entry", "N/A", mib_val),
                    tags=("table-entry",),
                )
                # Track entry in oid_to_item with the entry OID (table.instance)
                entry_full_oid = f"{entry_oid}.{inst}"
                self.oid_to_item[entry_full_oid] = entry_item
                added_count += 1

                # Add columns under the entry
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

                    display_text = name
                    
                    # Format value with enum name if applicable
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
                    if getattr(self, 'oid_icon_images', None):
                        img = self.oid_icon_images.get(icon_key)
                    mib_val = self.oid_metadata.get(col_oid, {}).get("mib") or "N/A"
                    img_ref = cast(Any, img) if img is not None else ""
                    col_item = self.oid_tree.insert(
                        entry_item,
                        "end",
                        text=display_text,
                        image=img_ref,
                        values=(col_oid, inst, display_value, type_str, access_str, mib_val),
                        tags=("evenrow", "table-column", "table-index") if is_index else ("evenrow", "table-column"),
                    )
                    # Track column in oid_to_item with the full column OID (table.column.instance)
                    self.oid_to_item[full_col_oid] = col_item
                    # Also store base column OID for search purposes
                    # (search finds base OIDs without instances in metadata)
                    if col_oid not in self.oid_to_item:
                        self.oid_to_item[col_oid] = col_item

            self._log(f"Successfully added {added_count} instances to OID tree", "INFO")
            # Expand the table node to show the new instances
            self.oid_tree.item(item, open=True)
            # Ensure tree column is wide enough for new items
            self._ensure_tree_column_width()

        self.root.after(0, update_ui)
    
    def _fetch_values_for_node(self, item: str) -> None:
        """Background worker: fetch values for immediate children of `item`.

        This runs in a worker thread and updates the UI via `root.after`.
        """
        try:
            children = list(self.oid_tree.get_children(item))
        except Exception:
            return

        for child in children:
            # If child has no further children, it's a leaf candidate
            if not self.oid_tree.get_children(child):
                oid_str = self.oid_tree.set(child, "oid")
                instance_str = self.oid_tree.set(child, "instance")
                tags = self.oid_tree.item(child, "tags")
                if not oid_str:
                    continue

                if "table-index" in tags:
                    continue

                # Fetch values for scalars (instance = "0") or table columns (instance is numeric or dotted)
                if instance_str == "0":
                    fetch_oid = oid_str + ".0"
                elif instance_str:
                    parts = instance_str.split(".")
                    if all(part.isdigit() for part in parts if part):
                        fetch_oid = oid_str + "." + instance_str
                    else:
                        continue
                else:
                    continue

                # Skip if already fetched (even if empty) since we now do bulk loading
                if fetch_oid in self.oid_values:
                    continue  # already fetched in bulk or previously

                # Only fetch if not already loaded (for backwards compatibility with lazy loading)
                try:
                    self._log(f"Fetching value for OID {fetch_oid} (instance={instance_str})")
                    resp = requests.get(f"{self.api_url}/value", params={"oid": fetch_oid}, timeout=3)
                    resp.raise_for_status()
                    val = resp.json().get("value", "unset")
                    val_str = "unset" if val is None else str(val)
                    self.oid_values[fetch_oid] = val_str

                    # Format value with enum name if applicable
                    display_val = val_str
                    if val_str not in ("unset", "N/A", ""):
                        # Get base OID for metadata lookup (strip instance)
                        base_oid = oid_str
                        metadata = self.oid_metadata.get(base_oid, {})
                        enums = metadata.get("enums")
                        if enums:
                            try:
                                int_value = int(val_str)
                                for enum_name, enum_value in enums.items():
                                    if enum_value == int_value:
                                        display_val = f"{val_str} ({enum_name})"
                                        break
                            except (ValueError, TypeError):
                                pass

                    # Update the UI on the main thread
                    def update_ui(c: str = child, v: str = display_val) -> None:
                        self.oid_tree.set(c, "value", v)
                    self.root.after(0, update_ui)
                    self._log(f"Fetched value for OID {fetch_oid}: {val_str}")
                except Exception as e:
                    # Mark as attempted to avoid repeated failures
                    self.oid_values[fetch_oid] = ""
                    self._log(f"Failed to fetch value for OID {fetch_oid}: {e}", "WARNING")
            else:
                # Non-leaf: optionally prefetch its leaf children; skip to avoid deep recursion
                continue

    def _refresh_oid_tree_value(self, full_oid: str, display_value: str) -> None:
        """Refresh a specific OID value in the tree after it's been updated.

        Args:
            full_oid: The full OID including instance (e.g., "1.3.6.1.2.1.2.2.1.8.1")
            display_value: The formatted display value to show
        """
        # Parse the OID to find the tree item
        # For table columns, the OID format is: col_oid.instance
        # We need to find the tree item that matches this

        # Try to find the item in the OID tree
        # The tree stores base OID (without instance) in the "oid" column
        # and instance in the "instance" column

        parts = full_oid.rsplit(".", 1)
        if len(parts) == 2:
            base_oid, instance = parts
        else:
            # Scalar OID
            base_oid = full_oid
            instance = ""

        # Search through the tree for matching items
        def find_and_update(item: str) -> bool:
            """Recursively search for the matching tree item."""
            try:
                item_oid = self.oid_tree.set(item, "oid")
                item_instance = self.oid_tree.set(item, "instance")

                # Check if this item matches
                if item_oid == base_oid and item_instance == instance:
                    # Found it! Update the value
                    self.oid_tree.set(item, "value", display_value)
                    self._log(f"Refreshed OID tree value for {full_oid}: {display_value}", "DEBUG")
                    return True

                # Search children
                for child in self.oid_tree.get_children(item):
                    if find_and_update(child):
                        return True

            except Exception as e:
                self._log(f"Error searching tree item: {e}", "DEBUG")

            return False

        # Start search from root
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

            # Refresh the parent table
            self.executor.submit(self._discover_table_instances, table_item, table_oid)
            
            # Also refresh any augmented tables that depend on this parent table
            def refresh_augmented_tables() -> None:
                """Find and refresh all augmented tables that depend on this parent."""
                try:
                    # Search the entire tree for tables that have index_from pointing to this parent
                    self._refresh_augmented_tables_for_parent(table_oid)
                except Exception as e:
                    self._log(f"Error refreshing augmented tables: {e}", "WARNING")
            
            # Submit with a small delay to allow the parent table to refresh first
            self.root.after(500, lambda: self.executor.submit(refresh_augmented_tables))

        except Exception as e:
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

            # Find and delete the entry node for this instance
            def delete_entry() -> None:
                children = self.oid_tree.get_children(table_item)
                for child in children:
                    child_instance = self.oid_tree.set(child, "instance")
                    if child_instance == instance:
                        self.oid_tree.delete(child)
                        self._log(f"Deleted instance {instance} from OID tree", "DEBUG")
                        return
                self._log(f"Instance {instance} not found in OID tree", "DEBUG")

            # Delete on UI thread
            self.root.after(0, delete_entry)

        except Exception as e:
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

            self._log(f"Refreshing OID tree table {oid_str} - will re-query /table-schema", "INFO")

            # Re-discover table instances in the background
            # Note: This is called after edits. The main refresh happens in _on_node_open
            # when the user expands the table node.
            self.executor.submit(self._discover_table_instances, table_item, oid_str)

        except Exception as e:
            self._log(f"Error refreshing OID tree table: {e}", "ERROR")
            import traceback
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
            self._log(f"Looking for augmented tables that depend on parent {parent_table_oid}", "INFO")
            
            # Find all tables in the OID tree
            def search_for_augmented_tables(item: str) -> None:
                """Recursively search the tree for augmented table nodes."""
                try:
                    # Check if this is a table node
                    item_oid = self.oid_tree.set(item, "oid")
                    item_tags = self.oid_tree.item(item, "tags")
                    
                    if "table" in item_tags and item_oid and item_oid != parent_table_oid:
                        # This is a table - check if it's augmented from the parent
                        try:
                            resp = requests.get(
                                f"{self.api_url}/table-schema",
                                params={"oid": item_oid},
                                timeout=5
                            )
                            if resp.status_code == 200:
                                schema = resp.json()
                                index_from = schema.get("index_from", [])
                                
                                # Check if index_from references the parent table
                                if index_from:
                                    # index_from is a list of dicts with 'column' info
                                    # We need to check if this augmented table would
                                    # inherit indexes from the parent
                                    # For now, we'll just refresh any table that has index_from
                                    # since it means it's augmented
                                    self._log(f"Found augmented table {item_oid} (index_from={index_from})", "DEBUG")
                                    # Refresh this augmented table
                                    self.executor.submit(self._discover_table_instances, item, item_oid)
                        except Exception as e:
                            self._log(f"Error checking table schema for {item_oid}: {e}", "DEBUG")
                    
                    # Recurse into children
                    for child in self.oid_tree.get_children(item):
                        search_for_augmented_tables(child)
                        
                except Exception as e:
                    self._log(f"Error searching for augmented tables: {e}", "DEBUG")
            
            # Start search from tree root
            for root_item in self.oid_tree.get_children():
                search_for_augmented_tables(root_item)
                
        except Exception as e:
            self._log(f"Error in _refresh_augmented_tables_for_parent: {e}", "ERROR")

    def _on_tab_change(self) -> None:
        """Handle tab changes to restore OID tree focus when returning from Table View."""
        try:
            current_tab = self.tabview.get()
        except Exception:
            current_tab = None

        if current_tab == "OID Tree":
            self._apply_pending_oid_focus()

    def _set_pending_oid_focus(
        self,
        table_oid: str,
        instance: str | None,
        column_oid: str | None = None,
    ) -> None:
        """Store a pending focus request for the OID tree."""
        self._pending_oid_focus = {
            "table_oid": table_oid,
            "instance": instance,
            "column_oid": column_oid,
        }
        self._pending_oid_focus_retries = 0

    def _apply_pending_oid_focus(self) -> None:
        """Restore focus in the OID tree based on the last table selection/edit."""
        if not self._pending_oid_focus:
            return

        table_oid = self._pending_oid_focus.get("table_oid")
        instance = self._pending_oid_focus.get("instance")
        column_oid = self._pending_oid_focus.get("column_oid")

        if not table_oid:
            return

        table_item = self.oid_to_item.get(table_oid)
        if not table_item:
            return

        self._expand_path_to_item(table_item)
        self.oid_tree.item(table_item, open=True)

        target_item = table_item
        if instance:
            entry_item = self._find_table_entry_item(table_item, instance)
            if entry_item:
                target_item = entry_item
                if column_oid:
                    column_item = self._find_table_column_item(entry_item, column_oid, instance)
                    if column_item:
                        target_item = column_item
            else:
                if self._pending_oid_focus_retries < 5:
                    self._pending_oid_focus_retries += 1
                    self.executor.submit(self._discover_table_instances, table_item, table_oid)
                    self.root.after(200, self._apply_pending_oid_focus)
                    return

        self.oid_tree.selection_set(target_item)
        self.oid_tree.focus(target_item)
        self.oid_tree.see(target_item)
        self._update_selected_info(target_item)
        self._ensure_oid_name_width(target_item)
        self._pending_oid_focus = None

    def _find_table_entry_item(self, table_item: str, instance: str) -> str | None:
        """Find a table-entry item under the table node for the given instance."""
        for child in self.oid_tree.get_children(table_item):
            if "table-entry" in self.oid_tree.item(child, "tags"):
                child_instance = self.oid_tree.set(child, "instance")
                if child_instance == instance:
                    return child
        return None

    def _find_table_column_item(self, entry_item: str, column_oid: str, instance: str) -> str | None:
        """Find a table-column item under an entry for a given column OID and instance."""
        for child in self.oid_tree.get_children(entry_item):
            if "table-column" in self.oid_tree.item(child, "tags"):
                child_oid = self.oid_tree.set(child, "oid")
                child_instance = self.oid_tree.set(child, "instance")
                if child_oid == column_oid and child_instance == instance:
                    return child
        return None

    def _toggle_connection(self) -> None:
        """Connect or disconnect from the REST API."""
        if self.connected:
            self._disconnect()
        else:
            self._connect()
    
    def _connect(self) -> None:
        """Connect to the REST API."""
        host = self.host_var.get().strip()
        port = self.port_var.get().strip()
        self.api_url = f"http://{host}:{port}"
        
        try:
            self.status_var.set("Connecting...")
            self._log(f"Connecting to {self.api_url}")
            
            # Test connection by fetching MIBs with dependencies
            try:
                response = requests.get(f"{self.api_url}/mibs-with-dependencies", timeout=5)
                response.raise_for_status()
                mibs_dep_data = response.json()
            except Exception:
                # Fallback to simple /mibs endpoint if the new endpoint is not available
                response = requests.get(f"{self.api_url}/mibs", timeout=5)
                response.raise_for_status()
                mibs_data = response.json()
                configured_mibs = mibs_data.get("mibs", [])
                mibs_dep_data = {
                    "configured_mibs": configured_mibs,
                    "tree": {mib: {"direct_deps": [], "transitive_deps": [], "is_configured": True} for mib in configured_mibs},
                }

            # Populate MIB tree with dependencies
            self._populate_mibs_tree(mibs_dep_data)
            
            # Get MIBs count for logging
            configured_mibs_list = mibs_dep_data.get("configured_mibs", [])
            
            # Fetch OIDs
            response = requests.get(f"{self.api_url}/oids", timeout=5)
            response.raise_for_status()
            
            oids_data = response.json()
            oids = oids_data.get("oids", {})
            # Convert OID lists (from JSON) to tuples to match the annotated type
            try:
                converted = {str(k): tuple(v) for k, v in oids.items()}
            except Exception:
                converted = {}
            self.oids_data = converted

            # Fetch OID metadata
            try:
                response = requests.get(f"{self.api_url}/oid-metadata", timeout=5)
                response.raise_for_status()
                metadata_data = response.json()
                self.oid_metadata = metadata_data.get("metadata", {})
            except Exception as e:
                self._log(f"Failed to fetch OID metadata: {e}", "WARNING")
                self.oid_metadata = {}

            # Fetch all OID values in bulk for efficient loading
            self._log("Loading all OID values in bulk...")
            try:
                response = requests.get(f"{self.api_url}/values/bulk", timeout=30)
                response.raise_for_status()
                values_data = response.json()
                self.oid_values = values_data.get("values", {})
                self._log(f"Loaded {len(self.oid_values)} OID values")
            except Exception as e:
                self._log(f"Failed to fetch bulk values: {e}", "WARNING")
                self.oid_values = {}
            
            # Fetch all table instances in bulk
            self._log("Loading all table instances in bulk...")
            try:
                response = requests.get(f"{self.api_url}/tree/bulk", timeout=30)
                response.raise_for_status()
                tree_data = response.json()
                self.table_instances_data = tree_data.get("tables", {})
                total_instances = sum(len(t.get("instances", [])) for t in self.table_instances_data.values())
                self._log(f"Loaded {len(self.table_instances_data)} tables with {total_instances} total instances")
                if self.table_instances_data:
                    self._log(f"Table OIDs loaded: {list(self.table_instances_data.keys())[:5]}...", "DEBUG")
            except Exception as e:
                self._log(f"Failed to fetch tree bulk data: {e}", "WARNING")
                import traceback
                traceback.print_exc()
                self.table_instances_data = {}
            
            # Enable OID Tree tab when connected
            self.enable_oid_tree_tab()
            
            # Enable Traps tab when connected
            self.enable_traps_tab()

            # Enable Links tab when connected
            self.enable_links_tab()
            
            # Update MIB browser with OID metadata if it exists (browser already created at startup)
            if self.mib_browser:
                self.mib_browser.set_oid_metadata(self.oid_metadata)
            
            # Populate OID tree with OIDs
            self._populate_oid_tree()
            
            self.connected = True
            self.connect_button.configure(text="Disconnect")
            self.status_var.set("Connected")
            self._log(f"Connected successfully. Found {len(configured_mibs_list)} MIBs and {len(oids)} OIDs")
            
            # Load available traps
            self._load_traps()

        except requests.exceptions.ConnectionError:
            error_msg = "Cannot connect to REST API. Is the agent running?"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            if not self.silent_errors:
                messagebox.showerror("Connection Error", error_msg)

        except Exception as e:
            error_msg = f"Error connecting: {str(e)}"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            if not self.silent_errors:
                messagebox.showerror("Error", error_msg)
    
    def _disconnect(self) -> None:
        """Disconnect from the REST API."""
        self.connected = False
        self.connect_button.configure(text="Connect")
        self.status_var.set("Disconnected")
        
        # Clear MIB text display
        self.mibs_text.configure(state="normal")
        self.mibs_text.delete("1.0", "end")
        self.mibs_text.configure(state="disabled")
        self.mibs_data.clear()
        self.current_mermaid_diagram = ""
        
        # Remove OID Tree and Traps tabs when disconnected
        if "OID Tree" in self.tabview._tab_dict:
            self.tabview.delete("OID Tree")
        if "Traps" in self.tabview._tab_dict:
            self.tabview.delete("Traps")
        
        self._log("Disconnected")
    
    def _populate_mibs_tree(self, mibs_dep_data: Dict[str, Any]) -> None:
        """Populate the MIBs display with dependency information.
        
        Args:
            mibs_dep_data: Dictionary containing MIB dependency information from API.
        """
        try:
            self.mibs_data.clear()

            tree = mibs_dep_data.get("tree", {})
            configured_mibs = mibs_dep_data.get("configured_mibs", [])
            transitive_deps = mibs_dep_data.get("transitive_dependencies", [])
            summary = mibs_dep_data.get("summary", {})

            # Build display text
            display_text = "MIB DEPENDENCY SUMMARY\n"
            display_text += "="*60 + "\n\n"
            display_text += f"Configured MIBs ({summary.get('configured_count', 0)}):\n"
            if configured_mibs:
                display_text += f"  {', '.join(configured_mibs)}\n"
            else:
                display_text += "  (none)\n"
            
            display_text += f"\nTransitive Dependencies ({summary.get('transitive_count', 0)}):\n"
            if transitive_deps:
                display_text += f"  {', '.join(transitive_deps)}\n"
            else:
                display_text += "  (none)\n"
            
            display_text += f"\nTotal Unique MIBs: {summary.get('total_count', 0)}\n"
            display_text += "="*60 + "\n\n"
            display_text += "DETAILED DEPENDENCIES\n"
            display_text += "="*60 + "\n"

            # Add detailed dependency information
            for mib_name in configured_mibs:
                if mib_name not in tree:
                    continue
                mib_info = tree[mib_name]
                direct_deps = mib_info.get("direct_deps", [])
                transitive = mib_info.get("transitive_deps", [])

                display_text += f"\n{mib_name} (configured)\n"
                display_text += f"  Direct imports: {', '.join(direct_deps) if direct_deps else '(none)'}\n"
                if transitive:
                    display_text += f"  Transitive: {', '.join(transitive)}\n"
                self.mibs_data[mib_name] = mib_info

            self.mibs_text.configure(state="normal")
            self.mibs_text.delete("1.0", "end")
            self.mibs_text.insert("1.0", display_text)
            self.mibs_text.configure(state="disabled")

            self._log(f"Populated MIB dependency display with {summary.get('total_count', 0)} total MIBs")

        except Exception as e:
            self._log(f"Error populating MIB display: {e}", "ERROR")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Add a message to the log window using the logger."""
        self.logger.log(message, level)

    def _on_close(self) -> None:
        """Save GUI log and configuration then quit."""
        try:
            # Save GUI log using common utility
            save_gui_log(self.log_text)

            # Save trap config to server via API
            cfg = {
                "host": self.host_var.get(), 
                "port": self.port_var.get(),
                "trap_destinations": self.trap_destinations,
                "selected_trap": self.trap_var.get(),
                "trap_index": self.trap_index_var.get(),
                "trap_overrides": self.current_trap_overrides
            }
            try:
                resp = requests.post(f"{self.api_url}/config", json=cfg, timeout=5)
                resp.raise_for_status()
                self._log("Configuration saved to server")
            except requests.exceptions.RequestException as e:
                self._log(f"Failed to save config to server: {e}", "ERROR")
                # Fallback to local file if server save fails
                self._save_config_locally(cfg)
        except Exception as e:
            self._log(f"Error during shutdown: {e}", "ERROR")

        try:
            self.root.destroy()
        except Exception:
            try:
                self.root.quit()
            except Exception:
                pass

    def _save_config_locally(self, cfg: Dict[str, Any]) -> None:
        """Fallback method to save config locally if server save fails."""
        try:
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            try:
                import yaml
                with open(data_dir / "gui_config.yaml", "w", encoding="utf-8") as f:
                    yaml.safe_dump(cfg, f)
            except Exception:
                # Fallback to JSON if PyYAML not available
                with open(data_dir / "gui_config.json", "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
        except Exception as e:
            self._log(f"Failed to save config locally: {e}", "ERROR")

    def _collect_trap_overrides(self) -> Dict[str, str]:
        """Collect override values from the UI table."""
        trap_overrides: Dict[str, str] = {}

        for row in self.oid_rows:
            # Skip sysUpTime (always real-time) and index varbinds
            if row.get("is_sysuptime", False) or row.get("is_index", False):
                continue

            if row["use_override_var"].get():
                oid_name = row["oid_name"]
                override_value = row["override_entry"].get().strip()
                if override_value:
                    trap_overrides[oid_name] = override_value

        return trap_overrides


    def _resolve_oid_str_to_actual_oid(self, oid_str: str) -> Optional[Any]:
        """Resolve a UI OID label like 'IF-MIB::ifOperStatus[2]' to an actual OID instance."""
        # Table OID with [index]
        if "::" in oid_str and "[" in oid_str and "]" in oid_str:
            return self._resolve_table_oid(oid_str)

        # Regular scalar: find an OID in metadata
        for oid, metadata in self.oid_metadata.items():
            if oid_str in oid or oid_str in metadata.get("name", ""):
                return oid

        return None


    def _apply_trap_overrides(self, trap_overrides: Dict[str, str]) -> int:
        """Apply trap override values by POSTing to /value. Returns count of successful updates."""
        applied = 0

        for oid_str, value in trap_overrides.items():
            try:
                actual_oid = self._resolve_oid_str_to_actual_oid(oid_str)
                if not actual_oid:
                    self._log(f"Could not resolve OID: {oid_str}", "WARNING")
                    continue

                update_payload = {"oid": actual_oid, "value": value}
                response = requests.post(f"{self.api_url}/value", json=update_payload, timeout=5)

                if response.status_code == 200:
                    applied += 1
                    self._log(f"Set OID {oid_str} = {value}")
                else:
                    self._log(f"Failed to set OID {oid_str}: {response.text}", "WARNING")

            except Exception as exc:
                self._log(f"Error setting OID {oid_str}: {exc}", "WARNING")

        return applied


    def _build_send_trap_payload(
        self,
        trap_name: str,
        dest_host: str,
        dest_port: int,
        community: str = "public",
        trap_type: TrapType = "trap",
    ) -> SendTrapPayload:
        return {
            "trap_name": trap_name,
            "trap_type": trap_type,
            "dest_host": dest_host,
            "dest_port": dest_port,
            "community": community,
        }


    def _post_send_trap(self, payload: SendTrapPayload) -> Dict[str, Any]:
        response = requests.post(f"{self.api_url}/send-trap", json=payload, timeout=5)
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    def _log_send_result(
        self,
        dest_host: str,
        dest_port: int,
        trap_name: str,
        result: Dict[str, Any],
    ) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        trap_oid = result.get("trap_oid", "")
        oid_str = _oid_list_to_str(trap_oid)

        log_msg = f"[{timestamp}] Sent to {dest_host}:{dest_port}: {trap_name} (OID: {oid_str})"
        self.log_text.insert("end", "\n" + log_msg + "\n")
        self.log_text.see("end")


    def _log_send_failure(
        self,
        dest_host: str,
        dest_port: int,
        trap_name: str,
        error: Exception,
    ) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] Failed to {dest_host}:{dest_port}: {trap_name} - {error}"
        self.log_text.insert("end", "\n" + log_msg + "\n")
        self.log_text.see("end")


    def _send_test_trap(self) -> None:
        """Send the selected trap to localhost on the receiver port."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap to send.")
            return

        try:
            port = int(self.receiver_port_var.get())

            trap_overrides = self._collect_trap_overrides()
            self._apply_trap_overrides(trap_overrides)

            payload = self._build_send_trap_payload(
                trap_name=trap_name,
                dest_host="localhost",
                dest_port=port,
                community="public",
                trap_type="trap",
            )

            result = self._post_send_trap(payload)

            # Log success
            timestamp = datetime.now().strftime("%H:%M:%S")
            trap_oid = result.get("trap_oid", "")
            oid_str = _oid_list_to_str(trap_oid)

            log_msg = f"[{timestamp}] Sent test trap to localhost:{port}: {trap_name} (OID: {oid_str})"
            self.log_text.insert("end", "\n" + log_msg + "\n")
            self.log_text.see("end")

            self._log(f"Test trap sent to localhost:{port}")

            # Wait a moment for the trap to be received, then check
            time.sleep(0.5)

            # Check if trap was received
            try:
                check_response = requests.get(f"{self.api_url}/trap-receiver/traps?limit=1", timeout=2)
                if check_response.status_code == 200:
                    check_result = check_response.json()
                    traps = check_result.get("traps", [])
                    if traps:
                        received_trap = traps[0]
                        recv_timestamp = received_trap.get("timestamp", "")
                        recv_oid = received_trap.get("trap_oid_str", "unknown")
                        varbinds = received_trap.get("varbinds", [])

                        recv_log_msg = f"[{recv_timestamp}] Received trap: {trap_name} (OID: {recv_oid})"
                        self.log_text.insert("end", "\n" + recv_log_msg + "\n")

                        for vb in varbinds:
                            vb_oid = vb.get("oid_str", "unknown")
                            vb_value = vb.get("value", "")
                            self.log_text.insert("end", f"  - {vb_oid} = {vb_value}\n")

                        self.log_text.see("end")
                        self._show_trap_notification(trap_name, recv_oid, recv_timestamp, varbinds)
                    else:
                        messagebox.showwarning(
                            "Trap Sent",
                            f"Test trap '{trap_name}' was sent to localhost:{port}\n\n"
                            "But no trap was received. Make sure the receiver is running.",
                        )
            except Exception:
                messagebox.showinfo("Trap Sent", f"Test trap '{trap_name}' sent to localhost:{port}")

        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except Exception as exc:
            error_msg = f"Failed to send test trap: {exc}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)


    def _send_trap(self) -> None:
        """Send the selected trap to all configured destinations."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap to send.")
            return

        if not self.trap_destinations:
            messagebox.showerror("No Destinations", "Please add at least one trap destination.")
            return

        try:
            trap_overrides = self._collect_trap_overrides()
            applied = self._apply_trap_overrides(trap_overrides)

            if applied:
                self._log(f"Applied {applied} trap-specific OID override(s)")

            success_count = 0

            for dest_host, dest_port in self.trap_destinations:
                payload = self._build_send_trap_payload(
                    trap_name=trap_name,
                    dest_host=dest_host,
                    dest_port=dest_port,
                    community="public",
                    trap_type="trap",
                )

                try:
                    result = self._post_send_trap(payload)
                    self._log_send_result(dest_host, dest_port, trap_name, result)
                    success_count += 1
                except requests.exceptions.RequestException as exc:
                    self._log(f"Failed to send trap to {dest_host}:{dest_port}: {exc}", "ERROR")
                    self._log_send_failure(dest_host, dest_port, trap_name, exc)

            if success_count > 0:
                self._log(
                    f"Successfully sent trap '{trap_name}' to "
                    f"{success_count}/{len(self.trap_destinations)} destination(s)"
                )
                messagebox.showinfo(
                    "Success",
                    f"Trap '{trap_name}' sent to {success_count} destination(s)!",
                )
            else:
                messagebox.showerror("Error", "Failed to send trap to any destination")

        except Exception as exc:
            error_msg = f"Unexpected error sending trap: {exc}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _bake_state(self) -> None:
        """Bake current MIB state into agent-model schema files."""
        try:
            # Confirm action
            response = messagebox.askyesno(
                "Bake State",
                "This will bake the current MIB state into agent-model schema files,\n"
                "then clear the runtime state file (mib_state.json).\n\n"
                "A backup will be created automatically.\n\n"
                "Continue?"
            )

            if not response:
                return

            self._log("Baking state into schemas...")

            # Call API endpoint
            resp = requests.post(f"{self.api_url}/bake-state", timeout=30)
            resp.raise_for_status()
            result = resp.json()

            baked_count = result.get("baked_count", 0)
            backup_dir = result.get("backup_dir", "")

            self._log(f"✓ Baked {baked_count} value(s) into schemas")
            self._log(f"Backup created: {backup_dir}")
            self._log("✓ State file cleared")

            messagebox.showinfo(
                "Success",
                f"Successfully baked {baked_count} value(s) into schemas!\n\n"
                f"Backup: {backup_dir}\n\n"
                "Runtime state file has been cleared."
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to bake state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error baking state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _fresh_state(self) -> None:
        """Regenerate schemas and empty the MIB state file."""
        try:
            response = messagebox.askyesno(
                "Fresh State",
                "This will regenerate schema files and clear mib_state.json.\n\n"
                "You will need to restart the agent for schema changes to take effect.\n\n"
                "Continue?",
            )
            if not response:
                return

            self._log("Regenerating schemas and clearing state...")
            resp = requests.post(f"{self.api_url}/state/fresh", timeout=60)
            resp.raise_for_status()
            result = resp.json()

            backup_dir = result.get("backup_dir", "")
            regenerated = result.get("regenerated", 0)

            self._log(f"✓ Fresh state complete. Regenerated {regenerated} schema(s)")
            messagebox.showinfo(
                "Success",
                "Fresh State complete.\n\n"
                f"Schemas regenerated: {regenerated}\n"
                f"Backup: {backup_dir}\n\n"
                "Please restart the agent for schema changes to take effect.",
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to run Fresh State: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during Fresh State: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _reset_state(self) -> None:
        """Clear mib_state.json without regenerating schemas."""
        try:
            response = messagebox.askyesno(
                "Reset State",
                "This will clear mib_state.json (tables, scalars, deleted instances).\n\n"
                "Continue?",
            )
            if not response:
                return

            self._log("Resetting state...")
            resp = requests.post(f"{self.api_url}/state/reset", timeout=20)
            resp.raise_for_status()

            self._log("✓ State reset")
            messagebox.showinfo("Success", "State reset completed.")
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to reset state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error resetting state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _save_preset_dialog(self) -> None:
        """Show dialog to save current agent-model as a preset."""
        try:
            # Get preset name from user
            from tkinter import simpledialog
            preset_name = simpledialog.askstring(
                "Save Preset",
                "Enter a name for this preset:",
                parent=self.root
            )

            if not preset_name:
                return

            self._log(f"Saving preset '{preset_name}'...")

            # Bake state before saving preset
            bake_resp = requests.post(f"{self.api_url}/bake-state", timeout=30)
            bake_resp.raise_for_status()

            # Call API endpoint
            resp = requests.post(
                f"{self.api_url}/presets/save",
                json={"preset_name": preset_name},
                timeout=30
            )
            resp.raise_for_status()

            self._log(f"✓ Preset '{preset_name}' saved successfully")

            messagebox.showinfo(
                "Success",
                f"Preset '{preset_name}' saved successfully!"
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to save preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error saving preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _load_preset_dialog(self) -> None:
        """Show dialog to load a preset."""
        try:
            # Get list of presets
            resp = requests.get(f"{self.api_url}/presets", timeout=5)
            resp.raise_for_status()
            result = resp.json()

            presets = result.get("presets", [])

            if not presets:
                messagebox.showinfo("No Presets", "No presets available")
                return

            # Create custom dialog for preset selection
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Load Preset")
            dialog.geometry("400x300")
            dialog.transient(self.root)
            dialog.grab_set()

            ctk.CTkLabel(dialog, text="Select a preset to load:", font=("", 14, "bold")).pack(pady=10)

            # Listbox for presets
            from tkinter import ttk
            listbox_frame = ctk.CTkFrame(dialog)
            listbox_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

            scrollbar = ttk.Scrollbar(listbox_frame)
            scrollbar.pack(side="right", fill="y")

            preset_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set,
                                       font=("", 12), bg="#2b2b2b", fg="#ffffff")
            preset_listbox.pack(fill="both", expand=True)
            scrollbar.config(command=preset_listbox.yview)

            for preset in presets:
                preset_listbox.insert("end", preset)

            selected_preset: list[str | None] = [None]

            def on_load() -> None:
                selection = cast(tuple[int, ...], preset_listbox.curselection())  # type: ignore[no-untyped-call]
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a preset")
                    return

                selected_preset[0] = presets[selection[0]]
                dialog.destroy()

            def on_cancel() -> None:
                dialog.destroy()

            # Buttons
            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)

            ctk.CTkButton(btn_frame, text="Load", command=on_load, width=100).pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="Cancel", command=on_cancel, width=100).pack(side="left", padx=5)

            # Wait for dialog to close
            self.root.wait_window(dialog)

            if not selected_preset[0]:
                return

            preset_name = selected_preset[0]

            # Confirm action
            response = messagebox.askyesno(
                "Load Preset",
                f"This will replace the current agent-model with preset '{preset_name}'.\n\n"
                f"A backup will be created automatically.\n\n"
                f"You will need to restart the agent for changes to take effect.\n\n"
                f"Continue?"
            )

            if not response:
                return

            self._log(f"Loading preset '{preset_name}'...")

            # Call API endpoint
            resp = requests.post(
                f"{self.api_url}/presets/load",
                json={"preset_name": preset_name},
                timeout=30
            )
            resp.raise_for_status()
            result = resp.json()

            self._log(f"✓ Preset '{preset_name}' loaded successfully")

            messagebox.showinfo(
                "Success",
                f"Preset '{preset_name}' loaded successfully!\n\n"
                f"Please restart the agent for changes to take effect."
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to load preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error loading preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

def main() -> None:
    """Main entry point for the GUI application."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--autoconnect", action="store_true")
    parser.add_argument("--connect-delay", type=int, default=0, help="Delay in seconds before auto-connecting")
    parser.add_argument("--silent-errors", action="store_true", help="Log connection errors without showing popup dialogs")
    args = parser.parse_args()

    root = ctk.CTk()
    _app = SNMPControllerGUI(root)

    # Load saved config from server, fallback to local files
    try:
        saved = None
        
        # Only try to load from server if --autoconnect is specified
        if args.autoconnect:
            try:
                api_url = f"http://{_app.host_var.get()}:{_app.port_var.get()}"
                resp = requests.get(f"{api_url}/config", timeout=5)
                if resp.status_code == 200:
                    saved = resp.json()
                    _app._log("Configuration loaded from server")
                    _app.connected = True
                    _app.status_var.set(f"Connected: {_app.host_var.get()}:{_app.port_var.get()}")
            except requests.exceptions.RequestException:
                _app._log("Server not available, trying local config files")
        
        # Fallback to local files if server load failed
        if saved is None:
            cfg_path_yaml = Path("data/gui_config.yaml")
            cfg_path_json = Path("data/gui_config.json")
            
            if cfg_path_yaml.exists():
                try:
                    import yaml
                    with open(cfg_path_yaml, "r", encoding="utf-8") as f:
                        saved = yaml.safe_load(f) or {}
                except Exception:
                    saved = None
            elif cfg_path_json.exists():
                # Legacy fallback
                with open(cfg_path_json, "r", encoding="utf-8") as f:
                    saved = json.load(f)

        if saved:
            if args.host is None and "host" in saved:
                host_val = saved.get("host")
                _app.host_var.set("" if host_val is None else str(host_val))
            if args.port is None and "port" in saved:
                port_val = saved.get("port")
                _app.port_var.set("" if port_val is None else str(port_val))
            
            # Load trap configuration
            # Note: trap_destinations are now loaded from app config via API, not GUI config
            if "selected_trap" in saved and saved["selected_trap"] != "No traps available" and hasattr(_app, 'trap_var'):
                _app.trap_var.set(saved["selected_trap"])
            if "trap_index" in saved and hasattr(_app, 'trap_index_var'):
                _app.trap_index_var.set(saved["trap_index"])
            if "trap_overrides" in saved:
                _app.current_trap_overrides = saved["trap_overrides"]
    except Exception as e:
        _app._log(f"Error loading config: {e}")

    # Override with CLI args if provided
    if args.host:
        _app.host_var.set(args.host)
    if args.port:
        _app.port_var.set(str(args.port))

    # Set silent errors mode
    _app.silent_errors = args.silent_errors

    # Auto-connect with optional delay
    if args.autoconnect:
        delay_ms = (args.connect_delay * 1000) + 200  # Add 200ms for UI initialization
        root.after(delay_ms, _app._connect)

    root.mainloop()


if __name__ == "__main__":
    main()
