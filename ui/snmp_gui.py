import customtkinter as ctk
from tkinter import messagebox, ttk
import tkinter as tk
from typing import Any, Dict, Tuple, List
import concurrent.futures
import requests
from datetime import datetime
import argparse
import json
from pathlib import Path

# Set appearance mode and color theme
ctk.set_appearance_mode("system")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"


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
        self.oid_to_item: Dict[str, str] = {}  # oid_str -> tree item id
        # Executor for background value fetching
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self._setup_ui()
        self._log("Application started")

        # Initialize trap-related variables
        self.current_trap_overrides: Dict[str, str] = {}
        self.oid_rows: List[Dict[str, Any]] = []

        # Bind close handler to save GUI log and config
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
    
    def _setup_ui(self) -> None:
        """Setup the user interface components."""
        # Main tabview for tabs
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab 1: Configuration (always visible)
        self.tabview.add("Configuration")
        self._setup_config_tab()

        # Tab 2: Scripts
        self.tabview.add("Scripts")
        self._setup_scripts_tab()

        # OID Tree and Table View will be added dynamically when connected
        # Traps tab will also be added dynamically when connected

        # Log window below tabview
        log_frame = ctk.CTkFrame(self.root)
        log_frame.pack(fill="both", side="bottom", padx=10, pady=(0, 5))

        log_label = ctk.CTkLabel(log_frame, text="Log Output:", anchor="w")
        log_label.pack(fill="x", padx=5, pady=(5, 0))

        self.log_text = ctk.CTkTextbox(log_frame, height=150, font=("Courier", 11))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text.configure(state="disabled")

        # Status bar
        self.status_var = ctk.StringVar(value="Disconnected")
        status_bar = ctk.CTkLabel(self.root, textvariable=self.status_var, anchor="w",
                                   fg_color=("gray85", "gray25"), corner_radius=0, height=25)
        status_bar.pack(fill="x", side="bottom")
    
    def _setup_oid_tab(self) -> None:
        """Setup the OID tree view tab."""
        oid_frame = self.tabview.tab("OID Tree")

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
        search_entry.bind("<Return>", self._on_search)
        search_btn = ctk.CTkButton(toolbar, text="Go", command=self._on_search, width=50)
        search_btn.pack(side="left")

        # Frame for treeview (ttk.Treeview is used as customtkinter doesn't have a tree widget)
        tree_frame = ctk.CTkFrame(oid_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Configure Treeview style for better column distinction
        style = ttk.Style()
        style.theme_use("default")

        # Configure colors based on appearance mode
        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff"
        fg_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        selected_bg = "#1f538d" if ctk.get_appearance_mode() == "Dark" else "#0078d7"

        # Alternating row colors for better readability
        alt_bg = "#333333" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0"

        style.configure("OID.Treeview",
                       background=bg_color,
                       foreground=fg_color,
                       fieldbackground=bg_color,
                       borderwidth=2,
                       relief="solid",
                       rowheight=25)
        style.configure("OID.Treeview.Heading",
                       background="#1f1f1f" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0",
                       foreground=fg_color,
                       borderwidth=2,
                       relief="groove",  # groove gives a 3D inset effect
                       padding=5)
        style.map("OID.Treeview",
                 background=[("selected", selected_bg)])

        # Treeview for OIDs (add columns for instance, value, type, access, mib)
        self.oid_tree = ttk.Treeview(tree_frame, columns=("oid", "instance", "value", "type", "access", "mib"),
                                     show="tree headings", style="OID.Treeview")
        self.oid_tree.heading("#0", text="📋 MIB/Object")
        self.oid_tree.heading("oid", text="🔢 OID")
        self.oid_tree.heading("instance", text="Instance")
        self.oid_tree.heading("value", text="💾 Value")
        self.oid_tree.heading("type", text="Type")
        self.oid_tree.heading("access", text="Access")
        self.oid_tree.heading("mib", text="📚 MIB")

        # Configure columns with borders for better separation
        self.oid_tree.column("#0", width=250, minwidth=150, stretch=False)
        self.oid_tree.column("oid", width=200, minwidth=150, stretch=True, anchor="w")
        self.oid_tree.column("instance", width=80, minwidth=60, stretch=False, anchor="center")
        self.oid_tree.column("value", width=200, minwidth=100, stretch=True, anchor="w")
        self.oid_tree.column("type", width=120, minwidth=80, stretch=False, anchor="w")
        self.oid_tree.column("access", width=100, minwidth=80, stretch=False, anchor="center")
        self.oid_tree.column("mib", width=120, minwidth=80, stretch=False, anchor="w")

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
        # Bind selection change
        self.oid_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
    
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
        self.remove_instance_btn.pack(side="left")

        # Initially disable buttons
        self.add_instance_btn.configure(state="disabled")
        self.remove_instance_btn.configure(state="disabled")

        # Table view treeview
        self.table_tree = ttk.Treeview(table_frame, columns=("index",), show="headings", style="OID.Treeview")
        self.table_tree.heading("index", text="Index")
        self.table_tree.column("index", width=100, minwidth=50, stretch=False, anchor="center")

        # Bind selection change
        self.table_tree.bind("<<TreeviewSelect>>", self._on_table_row_select)
        # Bind double-click for cell editing
        self.table_tree.bind("<Double-1>", self._on_table_double_click)

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
        self.edit_overlay_entry = tk.Entry(self.edit_overlay_frame, font=("Courier", 12), width=40)
        self.edit_overlay_entry.pack(padx=2, pady=2, fill="both", expand=True)
        
        # Store editing state
        self.editing_item: str | None = None
        self.editing_column: str | None = None
        self.editing_oid: str | None = None

        # Message label for when no table is selected
        self.table_message_label = ctk.CTkLabel(table_frame, text="Select a table in the OID tree to view its data", font=("", 12))
        self.table_message_label.pack(pady=20)
        self.table_message_label.pack_forget()  # Hide initially

    def enable_table_tab(self) -> None:
        """Enable the 'Table View' tab dynamically."""
        if "Table View" not in self.tabview._tab_dict:
            # Insert after OID Tree if it exists, otherwise after Configuration
            self.tabview.add("Table View")
            self._setup_table_tab()
    
    def enable_oid_tree_tab(self) -> None:
        """Enable the 'OID Tree' tab after connecting."""
        if "OID Tree" not in self.tabview._tab_dict:
            # Insert after Configuration
            self.tabview.add("OID Tree")
            self._setup_oid_tab()
            # Populate the tree with data
            self._populate_oid_tree()
    
    def enable_traps_tab(self) -> None:
        """Enable the 'Traps' tab after connecting."""
        if "Traps" not in self.tabview._tab_dict:
            # Add Traps tab
            self.tabview.add("Traps")
            self._setup_traps_tab()
            
            # Reposition Scripts tab to come after Traps
            if "Scripts" in self.tabview._tab_dict:
                # Remove and re-add Scripts tab to place it after Traps
                self.tabview.delete("Scripts")
                self.tabview.add("Scripts")
                self._setup_scripts_tab()
    
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

        # MIBs frame
        mibs_frame = ctk.CTkFrame(config_frame)
        mibs_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        mibs_label = ctk.CTkLabel(mibs_frame, text="Implemented MIBs", font=("", 14, "bold"))
        mibs_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Textbox for MIBs (customtkinter doesn't have Listbox, using CTkTextbox instead)
        self.mibs_textbox = ctk.CTkTextbox(mibs_frame, height=200, font=("", 12))
        self.mibs_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.mibs_textbox.configure(state="disabled")
    
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
        
        # Create Treeview for destinations - compact height
        self.dest_tree = ttk.Treeview(dest_list_frame, columns=("host", "port"), show="headings", height=3, style="OID.Treeview", selectmode="extended")
        self.dest_tree.heading("host", text="Host")
        self.dest_tree.heading("port", text="Port")
        self.dest_tree.column("host", width=150, minwidth=100)
        self.dest_tree.column("port", width=80, minwidth=60, anchor="center")
        
        self.dest_tree.pack(padx=10, pady=(0, 5), fill="x")

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
        self.trap_dropdown.pack(side="left", padx=(0, 10))

        # Index selector (initially hidden)
        index_label = ctk.CTkLabel(select_frame, text="Index:", font=("", 10))
        self.index_label = index_label
        
        self.trap_index_var = ctk.StringVar(value="1")
        self.trap_index_combo = ctk.CTkComboBox(
            select_frame,
            variable=self.trap_index_var,
            values=["1"],
            width=60,
            font=("", 10),
            state="readonly"
        )
        # Add trace to update override labels when index changes
        self.trap_index_var.trace_add("write", lambda *args: self._update_override_labels())
        self.index_label.pack_forget()  # Hide initially
        self.trap_index_combo.pack_forget()  # Hide initially

        # Trap info
        info_label = ctk.CTkLabel(left_frame, text="Trap Details", font=("", 12, "bold"))
        info_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.trap_info_text = ctk.CTkTextbox(left_frame, height=150, font=("Courier", 10))
        self.trap_info_text.pack(fill="x", padx=10, pady=(0, 10))
        self.trap_info_text.configure(state="disabled")

        # Send button
        self.send_trap_btn = ctk.CTkButton(
            left_frame,
            text="Send Trap",
            command=self._send_trap,
            width=120,
            state="disabled",
            height=35
        )
        self.send_trap_btn.pack(pady=(0, 10))

        # Right column: OID overrides table
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # OID overrides section
        overrides_label = ctk.CTkLabel(right_frame, text="OID Overrides for Selected Trap", font=("", 12, "bold"))
        overrides_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Table header
        header_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(header_frame, text="OID", font=("", 10, "bold"), width=200).grid(row=0, column=0, padx=(0, 5))
        ctk.CTkLabel(header_frame, text="Current Value", font=("", 10, "bold"), width=100).grid(row=0, column=1, padx=(0, 5))
        ctk.CTkLabel(header_frame, text="Use Override", font=("", 10, "bold")).grid(row=0, column=2, padx=(0, 5))
        ctk.CTkLabel(header_frame, text="Override Value", font=("", 10, "bold"), width=120).grid(row=0, column=3)

        # Scrollable table for OID overrides
        table_frame = ctk.CTkScrollableFrame(right_frame, height=200)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.oid_table_frame = table_frame

        # Controls below table
        controls_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        controls_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.save_overrides_btn = ctk.CTkButton(
            controls_frame, 
            text="Save", 
            command=self._save_trap_config,
            width=120
        )
        self.save_overrides_btn.pack(side="left")

        # Bottom section: Trap log
        log_frame = ctk.CTkFrame(self.traps_scrollable)
        log_frame.pack(fill="both", expand=True, pady=(0, 10))

        log_label = ctk.CTkLabel(log_frame, text="Trap Log", font=("", 14, "bold"))
        log_label.pack(pady=(10, 5), padx=10, anchor="w")

        # Textbox for displaying trap log
        self.traps_textbox = ctk.CTkTextbox(log_frame, height=150, font=("Courier", 11))
        self.traps_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.traps_textbox.configure(state="disabled")

        # Button to clear trap log
        clear_button = ctk.CTkButton(log_frame, text="Clear Log", command=self._clear_traps)
        clear_button.pack(pady=(5, 10))

        # Bind trap selection change
        def on_trap_select(*args: Any) -> None:
            self._update_trap_info()
        self.trap_var.trace_add("write", on_trap_select)
        
        # Store trap metadata
        self.traps_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Update destination display with initial destinations
        self._update_dest_display()

    def _create_oid_table_row(self, oid_name: str, current_value: str = "") -> Dict[str, Any]:
        """Create a row in the OID overrides table."""
        row_frame = ctk.CTkFrame(self.oid_table_frame)
        row_frame.pack(fill="x", pady=2)

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

        # OID name label (display the full name including .index)
        oid_label = ctk.CTkLabel(row_frame, text=oid_name, width=200, anchor="w", font=("", 10))
        oid_label.grid(row=0, column=0, padx=(5, 5), sticky="w")

        # Current value label (updated by _refresh_current_values)
        current_label = ctk.CTkLabel(row_frame, text=current_value if current_value else "Loading...", width=100, anchor="w", font=("", 10))
        current_label.grid(row=0, column=1, padx=(0, 5), sticky="w")

        # Use override checkbox
        use_override_var = ctk.BooleanVar(value=False)
        override_check = ctk.CTkCheckBox(row_frame, text="", variable=use_override_var, width=20)
        override_check.grid(row=0, column=2, padx=(0, 5))

        # Override value entry
        override_entry = ctk.CTkEntry(row_frame, width=150, font=("", 10))
        override_entry.grid(row=0, column=3, padx=(0, 5), sticky="ew")

        return {
            "frame": row_frame,
            "oid_label": oid_label,
            "current_label": current_label,
            "use_override_var": use_override_var,
            "override_check": override_check,
            "override_entry": override_entry,
            "oid_name": oid_name,
            "is_table_oid": is_table_oid,
            "base_oid_name": base_oid_name,
            "index_part": index_part
        }

    def _update_override_labels(self) -> None:
        """Update OID labels in the overrides table with index suffixes when trap index changes."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return
        
        trap_data = self.traps_metadata.get(trap_name)
        if not trap_data:
            return
        
        # Get current trap index
        current_index = self.trap_index_var.get()
        
        # Update labels for each row in the overrides table
        for row in self.oid_rows:
            base_oid_name = row.get("base_oid_name", row["oid_name"])
            
            # Check if this is a table OID that should have index updated
            if row["is_table_oid"]:
                # Update the index part with dot notation and rebuild the display name
                new_display_name = f"{base_oid_name}.{current_index}"
                row["oid_label"].configure(text=new_display_name)
                # Update the stored oid_name
                row["oid_name"] = new_display_name

    def _clear_oid_table(self) -> None:
        """Clear all rows from the OID overrides table."""
        for row in self.oid_rows:
            row["frame"].destroy()
        self.oid_rows.clear()

    def _update_available_oids(self, trap_name: str, trap_data: Dict[str, Any]) -> None:
        """Update the available OIDs dropdown and create table for the selected trap."""
        objects = trap_data.get("objects", [])
        
        # Build OID list with index appended
        oid_list = []
        current_index = self.trap_index_var.get()
        for obj in objects:
            obj_mib = obj.get("mib", "")
            obj_name = obj.get("name", "")
            if obj_mib and obj_name:
                # For table-based traps, append the index with dot notation (not brackets)
                if trap_name.lower() in ["linkdown", "linkup"]:
                    oid_list.append(f"{obj_mib}::{obj_name}.{current_index}")
                else:
                    oid_list.append(f"{obj_mib}::{obj_name}")
        
        print(f"DEBUG _update_available_oids: trap_name={trap_name}, objects count={len(objects)}, oid_list={oid_list}")
        
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
        try:
            response = requests.get(f"{self.api_url}/trap-overrides/{trap_name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.current_trap_overrides = data.get("overrides", {})
                
                # Update table rows with override values
                for row in self.oid_rows:
                    oid_name = row["oid_name"]
                    if oid_name in self.current_trap_overrides:
                        row["use_override_var"].set(True)
                        row["override_entry"].delete(0, "end")
                        row["override_entry"].insert(0, self.current_trap_overrides[oid_name])
                    else:
                        row["use_override_var"].set(False)
                        row["override_entry"].delete(0, "end")
            else:
                self.current_trap_overrides = {}
                # Clear all checkboxes and entries
                for row in self.oid_rows:
                    row["use_override_var"].set(False)
                    row["override_entry"].delete(0, "end")
        except Exception as e:
            self._log(f"Failed to load trap overrides: {e}", "WARNING")
            self.current_trap_overrides = {}
            # Clear all checkboxes and entries
            for row in self.oid_rows:
                row["use_override_var"].set(False)
                row["override_entry"].delete(0, "end")

    def _refresh_current_values(self) -> None:
        """Refresh the current values displayed in the OID table."""
        if not self.connected:
            return
            
        for row in self.oid_rows:
            oid_name = row["oid_name"]
            try:
                # Resolve OID to actual dotted notation
                actual_oid = self._resolve_table_oid(oid_name, row)
                if actual_oid:
                    response = requests.get(f"{self.api_url}/value?oid={actual_oid}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        current_value = str(data.get("value", "N/A"))
                        row["current_label"].configure(text=current_value)
                    else:
                        row["current_label"].configure(text="Error")
                else:
                    row["current_label"].configure(text="N/A")
            except Exception as e:
                row["current_label"].configure(text="Error")
                self._log(f"Failed to get current value for {oid_name}: {e}", "WARNING")

    def _save_trap_config(self) -> None:
        """Save trap configuration including host/port and overrides."""
        # Save host/port and trap settings to server
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
            messagebox.showinfo("Success", "Configuration saved successfully")
        except requests.exceptions.RequestException as e:
            self._log(f"Failed to save config to server: {e}", "ERROR")
            # Fallback to local file if server save fails
            self._save_config_locally(cfg)
            messagebox.showwarning("Warning", "Saved locally - server not available")
        
        # Also save overrides for current trap
        self._save_all_overrides_silent()

    def _save_all_overrides_silent(self) -> None:
        """Save all overrides from the table to the API without showing messages."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            return
        
        # Collect overrides from table
        overrides = {}
        for row in self.oid_rows:
            if row["use_override_var"].get():
                oid_name = row["oid_name"]
                override_value = row["override_entry"].get().strip()
                if override_value:
                    overrides[oid_name] = override_value
        
        # Save to API
        try:
            response = requests.post(f"{self.api_url}/trap-overrides/{trap_name}", 
                                   json=overrides, timeout=5)
            if response.status_code == 200:
                self.current_trap_overrides = overrides
                self._log(f"Saved {len(overrides)} overrides for trap: {trap_name}")
        except Exception as e:
            self._log(f"Failed to save overrides: {e}", "ERROR")

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
        """Add a new trap destination."""
        try:
            host = self.dest_host_var.get().strip()
            port = int(self.dest_port_var.get().strip())
            if not host:
                messagebox.showerror("Error", "Host cannot be empty")
                return
            if port < 1 or port > 65535:
                messagebox.showerror("Error", "Port must be between 1 and 65535")
                return
            
            self.trap_destinations.append((host, port))
            self._update_dest_display()
            self._log(f"Added trap destination: {host}:{port}")
        except ValueError:
            messagebox.showerror("Error", "Invalid port number")

    def _remove_destination(self) -> None:
        """Remove the selected destinations from the Treeview."""
        selected_items = self.dest_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select destinations to remove.")
            return
        
        # Get the values of selected items
        to_remove = []
        for item in selected_items:
            values = self.dest_tree.item(item, "values")
            print(f"DEBUG _remove_destination: item={item}, values={values}, len={len(values)}")
            if len(values) >= 2:
                host, port = values[0], values[1]
                try:
                    port_int = int(port)
                    to_remove.append((host, port_int))
                    print(f"DEBUG: Will remove ({host}, {port_int})")
                except ValueError:
                    print(f"DEBUG: Error converting port '{port}' to int")
        
        print(f"DEBUG: Current destinations before removal: {self.trap_destinations}")
        print(f"DEBUG: To remove: {to_remove}")
        
        # Remove from the trap_destinations list
        removed_hosts = []
        for host, port in to_remove:
            print(f"DEBUG: Looking for ({host}, {port}) in {self.trap_destinations}")
            if (host, port) in self.trap_destinations:
                self.trap_destinations.remove((host, port))
                removed_hosts.append(f"{host}:{port}")
                print(f"DEBUG: Successfully removed ({host}, {port})")
            else:
                print(f"DEBUG: ({host}, {port}) not found in destinations")
        
        print(f"DEBUG: Destinations after removal: {self.trap_destinations}")
        
        if len(self.trap_destinations) == 0:
            # Ensure at least one destination remains
            self.trap_destinations.append(("localhost", 162))
            messagebox.showwarning("Warning", "Cannot remove all destinations. At least one must remain.")
        
        self._update_dest_display()
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
                    row["use_override_var"].set(False)
                    row["override_entry"].delete(0, "end")
                self._log(f"Cleared all overrides for trap: {trap_name}")
            else:
                messagebox.showerror("Error", f"Failed to clear overrides: {response.text}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear overrides: {e}")

    def _clear_traps(self) -> None:
        """Clear the traps displayed in the textbox."""
        self.traps_textbox.configure(state="normal")
        self.traps_textbox.delete("1.0", "end")
        self.traps_textbox.configure(state="disabled")
    
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
                return
            
            # Store trap metadata
            self.traps_metadata = traps
            
            # Update dropdown
            trap_names = sorted(traps.keys())
            self.trap_dropdown.configure(values=trap_names, state="readonly")
            self.send_trap_btn.configure(state="normal")
            
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
        
        # Check if trap contains Index-type varbinds and show/hide index selector
        has_index_objects = self._trap_has_index_objects(trap_data)
        if has_index_objects:
            self.index_label.pack(side="left", padx=(10, 2))
            self.trap_index_combo.pack(side="left", padx=(0, 10))
            # Populate with available indices
            indices = self._get_trap_indices(trap_data)
            self.trap_index_combo.configure(values=indices)
            if indices and self.trap_index_var.get() not in indices:
                self.trap_index_var.set(indices[0])
        else:
            self.index_label.pack_forget()
            self.trap_index_combo.pack_forget()
        
        # Update available OIDs for this trap
        self._update_available_oids(trap_name, trap_data)
        
        # Update override labels with current index
        self._update_override_labels()
    
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
            # Try to get ifNumber first to know how many interfaces
            resp = requests.get(f"{self.api_url}/value", params={"oid": "1.3.6.1.2.1.2.1.0"}, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                if_number = int(data.get("value", 1))
                # Return indices from 1 to ifNumber
                return [str(i) for i in range(1, if_number + 1)]
        except Exception:
            pass
        
        # Fallback: try to discover by testing ifIndex values
        indices = []
        for i in range(1, 11):  # Try first 10
            try:
                resp = requests.get(f"{self.api_url}/value", params={"oid": f"1.3.6.1.2.1.2.2.1.1.{i}"}, timeout=1)
                if resp.status_code == 200:
                    indices.append(str(i))
                else:
                    break
            except Exception:
                break
        
        return indices if indices else ["1"]
    
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
        
        # For regular OIDs, try to find them in metadata
        for oid, metadata in self.oid_metadata.items():
            if oid_str in oid:
                return oid
        
        return None

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
            # Collect overrides from table
            trap_overrides = {}
            for row in self.oid_rows:
                if row["use_override_var"].get():
                    oid_name = row["oid_name"]
                    override_value = row["override_entry"].get().strip()
                    if override_value:
                        trap_overrides[oid_name] = override_value
            
            # First, apply any trap-specific forced OID values
            force_updates = []
            for oid_str, value in trap_overrides.items():
                try:
                    # Handle table OIDs with [index] suffix
                    if "::" in oid_str and "[" in oid_str and "]" in oid_str:
                        # Resolve table OID to actual instance
                        actual_oid = self._resolve_table_oid(oid_str)
                        if actual_oid:
                            update_payload = {"oid": actual_oid, "value": value}
                        else:
                            self._log(f"Could not resolve table OID: {oid_str}", "WARNING")
                            continue
                    else:
                        # Regular scalar OID - try to find the actual OID
                        actual_oid = None
                        for oid, metadata in self.oid_metadata.items():
                            if oid_str in oid or oid_str in metadata.get("name", ""):
                                actual_oid = oid
                                break
                        if actual_oid:
                            update_payload = {"oid": actual_oid, "value": value}
                        else:
                            self._log(f"Could not find OID for: {oid_str}", "WARNING")
                            continue
                    
                    response = requests.post(f"{self.api_url}/value", json=update_payload, timeout=5)
                    if response.status_code == 200:
                        force_updates.append(oid_str)
                        self._log(f"Set OID {oid_str} = {value}")
                    else:
                        self._log(f"Failed to set OID {oid_str}: {response.text}", "WARNING")
                except Exception as e:
                    self._log(f"Error setting OID {oid_str}: {e}", "WARNING")
                    continue
            
            if force_updates:
                self._log(f"Applied {len(force_updates)} trap-specific OID override(s)")

            # Send trap to each destination
            success_count = 0
            for dest_host, dest_port in self.trap_destinations:
                payload = {
                    "trap_name": trap_name,
                    "trap_type": "trap",  # Send actual trap packets
                    "dest_host": dest_host,
                    "dest_port": dest_port,
                    "community": "public"
                }
                
                try:
                    response = requests.post(f"{self.api_url}/send-trap", json=payload, timeout=5)
                    response.raise_for_status()
                    result = response.json()
                    
                    # Log success for this destination
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    trap_oid = result.get("trap_oid", "")
                    oid_str = ".".join(str(x) for x in trap_oid) if isinstance(trap_oid, (list, tuple)) else str(trap_oid)
                    
                    log_msg = f"[{timestamp}] Sent to {dest_host}:{dest_port}: {trap_name} (OID: {oid_str})"
                    
                    self.traps_textbox.configure(state="normal")
                    self.traps_textbox.insert("end", log_msg + "\n")
                    self.traps_textbox.see("end")
                    self.traps_textbox.configure(state="disabled")
                    
                    success_count += 1
                    
                except requests.exceptions.RequestException as e:
                    error_msg = f"Failed to send trap to {dest_host}:{dest_port}: {e}"
                    self._log(error_msg, "ERROR")
                    # Still log the attempt
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    log_msg = f"[{timestamp}] Failed to {dest_host}:{dest_port}: {trap_name} - {str(e)}"
                    self.traps_textbox.configure(state="normal")
                    self.traps_textbox.insert("end", log_msg + "\n")
                    self.traps_textbox.see("end")
                    self.traps_textbox.configure(state="disabled")
            
            if success_count > 0:
                self._log(f"Successfully sent trap '{trap_name}' to {success_count}/{len(self.trap_destinations)} destination(s)")
                messagebox.showinfo("Success", f"Trap '{trap_name}' sent to {success_count} destination(s)!")
            else:
                messagebox.showerror("Error", "Failed to send trap to any destination")
            
        except Exception as e:
            error_msg = f"Unexpected error sending trap: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
    
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
                        icon = "✏️"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon = "🔒"
                    else:
                        icon = "📊"
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
                        icon = "✏️"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon = "🔒"
                    else:
                        icon = "📄"
                    instance_str = ""
                    val = self.oid_values.get(oid_str, "")
                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "Unknown"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or "N/A"
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"

                display_text = f"{icon} {stored_name}" if stored_name else f"{icon} {key}"
                
                # Add INDEX indicator to type column for known index columns
                if stored_name in ["ifIndex", "ifStackHigherLayer", "ifStackLowerLayer", "ifRcvAddressAddress"]:
                    type_val += " [INDEX]"
                    
                node = self.oid_tree.insert(parent, "end", text=display_text,
                                           values=(oid_str, instance_str, val, type_val, access_val, mib_val),
                                           tags=(row_tag,))
                self.oid_to_item[oid_str] = node
            else:
                # Folder/container node
                if value.get('__is_table__'):
                    icon = "📋"  # Table icon
                    display_text = f"{icon} {stored_name}" if stored_name else f"{icon} {key}"

                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "branch"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or ""
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"
                    node = self.oid_tree.insert(parent, "end", text=display_text,
                                               values=(oid_str, "", "", type_val, access_val, mib_val),
                                               tags=(row_tag, 'table'))
                    self.oid_to_item[oid_str] = node
                    # Insert placeholder to make it expandable
                    self.oid_tree.insert(node, "end", text="Loading...", values=("", "", "", "", "", ""), tags=('placeholder',))
                else:
                    icon = "📁"  # Folder icon
                    display_text = f"{icon} {stored_name}" if stored_name else f"{icon} {key}"

                    type_val = self.oid_metadata.get(oid_str, {}).get("type") or "branch"
                    access_val = self.oid_metadata.get(oid_str, {}).get("access") or "N/A"
                    mib_val = self.oid_metadata.get(oid_str, {}).get("mib") or "N/A"
                    node = self.oid_tree.insert(parent, "end", text=display_text,
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

        # Schedule background fetch for this node's children
        self.executor.submit(self._fetch_values_for_node, item)

        if 'table' in self.oid_tree.item(item, 'tags'):
            oid_str = self.oid_tree.set(item, "oid")
            self.executor.submit(self._discover_table_instances, item, oid_str)

    def _on_double_click(self, event: Any) -> None:
        """Handler called when a tree item is double-clicked; allows editing values for writable items."""
        try:
            item = self.oid_tree.identify_row(event.y)
        except Exception:
            return

        if not item:
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
        selected_items = self.oid_tree.selection()
        if not selected_items:
            # Hide table tab if no selection
            if "Table View" in self.tabview._tab_dict:
                self.tabview.delete("Table View")
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
                
                self._populate_table_view(table_item, selected_instance)
                # Enable add button
                self.add_instance_btn.configure(state="normal")
        else:
            # Hide table tab if not on table-related item
            if "Table View" in self.tabview._tab_dict:
                self.tabview.delete("Table View")

    def _on_table_row_select(self, event: Any) -> None:
        """Handler called when table row selection changes."""
        selected_rows = self.table_tree.selection()
        if selected_rows:
            self.remove_instance_btn.configure(state="normal")
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
        
        # Don't allow editing the index column (column 0)
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
        
        # Clear and populate the entry field
        self.edit_overlay_entry.delete(0, "end")
        self.edit_overlay_entry.insert(0, current_value)
        self.edit_overlay_entry.focus()
        self.edit_overlay_entry.selection_range(0, "end")
        
        # Bind keys for save/cancel
        self.edit_overlay_entry.bind("<Return>", lambda e: self._save_cell_edit())
        self.edit_overlay_entry.bind("<Escape>", lambda e: self._hide_edit_overlay())
        self.edit_overlay_entry.bind("<FocusOut>", lambda e: self._hide_edit_overlay())
    
    def _hide_edit_overlay(self) -> None:
        """Hide the edit overlay and cancel editing."""
        self.edit_overlay_frame.place_forget()
        self.editing_item = None
        self.editing_column = None
        self.editing_oid = None
        # Unbind the keys
        self.edit_overlay_entry.unbind("<Return>")
        self.edit_overlay_entry.unbind("<Escape>")
        self.edit_overlay_entry.unbind("<FocusOut>")
    
    def _save_cell_edit(self) -> None:
        """Save the edited cell value."""
        if not self.editing_item or not self.editing_column:
            self._hide_edit_overlay()
            return
        
        new_value = self.edit_overlay_entry.get()
        
        # Get the item's values to construct the OID
        item_values = self.table_tree.item(self.editing_item, "values")
        col_num = int(self.editing_column[1:]) - 1  # Convert #1, #2, etc to 0, 1, etc
        
        # Try to get table info and construct OID
        # We need to find the column name and table OID from context
        try:
            # Get the current table being shown
            if not hasattr(self, '_current_table_columns'):
                self._hide_edit_overlay()
                return
            
            columns = self._current_table_columns  # (name, col_oid, col_num)
            if col_num - 1 < 0 or col_num - 1 >= len(columns):
                self._hide_edit_overlay()
                return
            
            col_name, col_oid, _ = columns[col_num - 1]
            instance_index = item_values[0]  # First value is the instance index
            full_oid = f"{col_oid}.{instance_index}"
            
            # Update via API
            resp = requests.post(f"{self.api_url}/value", 
                               json={"oid": full_oid, "value": new_value}, 
                               timeout=5)
            
            if resp.status_code == 200:
                # Update the cell display
                updated_values = list(item_values)
                updated_values[col_num] = new_value
                self.table_tree.item(self.editing_item, values=updated_values)
                self._log(f"Updated {col_name} to: {new_value}")
            else:
                messagebox.showerror("Error", f"Failed to update value: {resp.text}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save cell: {e}")
        finally:
            self._hide_edit_overlay()

    def _populate_table_view(self, table_item: str, selected_instance: str | None = None) -> None:
        """Populate the table view with data from the selected table."""
        try:
            oid_str = self.oid_tree.set(table_item, "oid")
            if not oid_str:
                self._log("No OID found for table item", "WARNING")
                return
        except Exception as e:
            self._log(f"Error getting table OID: {e}", "ERROR")
            return

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

        # Find instances with timeout mechanism
        first_col_oid = columns[0][1]
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

        self._log(f"Loaded {len(instances)} instances from {first_col_oid}")
        if len(instances) == max_attempts:
            messagebox.showwarning("Warning", "Reached maximum attempts while loading instances.")

        # Set columns
        col_names = [col[0] for col in columns]
        self.table_tree["columns"] = ("index",) + tuple(col_names)
        self.table_tree.heading("index", text="Index")
        self.table_tree.column("index", width=100, minwidth=50, stretch=False, anchor="center")
        for col_name in col_names:
            self.table_tree.heading(col_name, text=col_name)
            self.table_tree.column(col_name, width=150, minwidth=100, stretch=True, anchor="w")
        
        # Store columns for later use in cell editing
        self._current_table_columns = columns

        # Populate rows
        row_items = []
        for inst in instances:
            values = [inst]
            for name, col_oid, col_num in columns:
                full_oid = f"{col_oid}.{inst}"
                try:
                    resp = requests.get(f"{self.api_url}/value", params={"oid": full_oid}, timeout=1)
                    if resp.status_code == 200:
                        val = resp.json().get("value", "")
                    else:
                        val = ""
                except Exception:
                    val = ""
                values.append(val)
            item = self.table_tree.insert("", "end", values=values)
            row_items.append((inst, item))

        # Select the row corresponding to selected_instance if provided
        if selected_instance:
            for inst, item in row_items:
                if inst == selected_instance:
                    self.table_tree.selection_set(item)
                    self.table_tree.see(item)
                    # Enable remove button since we have a selection
                    self.remove_instance_btn.configure(state="normal")
                    break

    def _add_instance(self) -> None:
        """Add a new instance to the current table."""
        try:
            # Get current table OID from the selected item in oid_tree
            selected_items = self.oid_tree.selection()
        except Exception as e:
            messagebox.showerror("Error", f"Error getting selected item: {e}")
            return
        if not selected_items:
            return
        table_item = None
        for item in selected_items:
            if 'table' in self.oid_tree.item(item, 'tags'):
                table_item = item
                break
        if not table_item:
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

        # Find index columns
        index_columns = []
        for col_name in schema.get("index_columns", []):
            if col_name in schema.get("columns", {}):
                col_info = schema["columns"][col_name]
                index_columns.append((col_name, col_info))

        if not index_columns:
            messagebox.showerror("Error", "No index columns found")
            return

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

        # Create entry fields for each index column
        entries = {}
        row = 0
        for col_name, col_info in index_columns:
            ctk.CTkLabel(input_frame, text=f"{col_name}:").grid(row=row, column=0, sticky="w", pady=5, padx=10)
            default_val = str(col_info.get("default", ""))
            entry = ctk.CTkEntry(input_frame)
            entry.insert(0, default_val)
            entry.grid(row=row, column=1, sticky="ew", pady=5, padx=(0, 10))
            entries[col_name] = entry
            row += 1

        input_frame.columnconfigure(1, weight=1)

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_cancel() -> None:
            dialog.destroy()

        def on_add() -> None:
            # Collect index values
            index_values = {}
            for col_name in entries:
                val = entries[col_name].get().strip()
                if not val:
                    messagebox.showerror("Error", f"{col_name} cannot be empty")
                    return
                index_values[col_name] = val

            # Create the table row using the new endpoint
            try:
                payload = {
                    "table_oid": table_oid,
                    "index_values": index_values,
                    "column_values": {}  # Can be extended for additional columns
                }
                resp = requests.post(f"{self.api_url}/table-row", json=payload, timeout=5)
                if resp.status_code == 200:
                    result = resp.json()
                    messagebox.showinfo("Success", f"Instance added successfully: {result.get('instance_oid')}")
                    # Refresh table view
                    self._populate_table_view(table_item)
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", f"Failed to add instance: {resp.text}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add instance: {e}")

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = ctk.CTkButton(button_frame, text="Add", command=on_add)
        add_btn.pack(side="right")

    def _remove_instance(self) -> None:
        """Remove the selected instance from the table."""
        try:
            selected_rows = self.table_tree.selection()
            if not selected_rows:
                messagebox.showwarning("No Selection", "Please select an instance to remove.")
                return
            
            # For now, just show info - actual deletion would require API support
            messagebox.showinfo("Remove Instance", "Table instance removal functionality coming soon")
            self._log(f"Remove instance requested for {len(selected_rows)} row(s)", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Error removing instance: {e}")
            self._log(f"Error in _remove_instance: {e}", "ERROR")
        else:
            messagebox.showerror("Error", "No columns found")

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
        
        print(f"DEBUG: Looking up metadata for base_oid={base_oid_str}, found metadata={metadata}")

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

        value_var = ctk.StringVar(value=current_value)
        value_entry = ctk.CTkEntry(main_frame, textvariable=value_var, width=400)
        value_entry.pack(pady=(5, 10), fill="x")

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

        print(f"DEBUG: is_writable={is_writable}, creating checkbox: {not is_writable}")

        if not is_writable:
            print("DEBUG: Creating unlock checkbox")
            def on_checkbox_toggle() -> None:
                """Handle checkbox toggle - reset value when unchecked."""
                unlocked = unlock_var.get()
                if not unlocked:
                    # Reset to original value when unchecked
                    value_var.set(original_value)
                self._toggle_entry_state(value_entry, unlocked)

            unlock_checkbox = ctk.CTkCheckBox(bottom_frame, text="Unlock for editing",
                                            variable=unlock_var,
                                            command=on_checkbox_toggle)
            unlock_checkbox.pack(side="left", anchor="w")
            value_entry.configure(state="disabled")  # Start disabled
            print("DEBUG: Checkbox created and packed, entry disabled")
        else:
            print("DEBUG: No checkbox needed for writable OID")

        # Buttons - right side
        def on_ok() -> None:
            new_value = value_var.get()
            if new_value is not None:
                # For read-only items, only allow if unlocked
                if not is_writable and not unlock_var.get():
                    messagebox.showwarning("Read-Only", "Please check 'Unlock for editing' to modify this read-only object.")
                    return
                # Only proceed if value has actually changed
                if not value_changed.get():
                    messagebox.showinfo("No Change", "Value has not been modified.")
                    return
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
        if is_writable:
            value_entry.focus()
            value_entry.select_range(0, 'end')
        elif unlock_checkbox:
            unlock_checkbox.focus()

        # Bind keys
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())

    def _toggle_entry_state(self, entry: Any, unlocked: bool) -> None:
        """Toggle the entry field state based on unlock checkbox."""
        entry.configure(state="normal" if unlocked else "disabled")

    def _set_oid_value(self, oid: str, new_value: str, item: str) -> None:
        """Set the value for an OID via the API."""
        try:
            self._log(f"Setting value for OID {oid} to: {new_value}")
            resp = requests.post(f"{self.api_url}/value",
                               json={"oid": oid, "value": new_value},
                               timeout=5)
            resp.raise_for_status()
            result = resp.json()

            # Log the API response for debugging
            self._log(f"API response: {result}")

            # Update the local value cache
            self.oid_values[oid] = new_value

            # Update the UI
            self.oid_tree.set(item, "value", new_value)

            self._log(f"Successfully set value for OID {oid}")
            messagebox.showinfo("Success", f"Value updated successfully for {oid}")

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

    def _on_search(self, event: Any = None) -> None:
        """Handle search in the OID tree."""
        search_term = self.search_var.get().strip()
        if not search_term:
            return

        # First, search in already loaded items
        for oid, item_id in self.oid_to_item.items():
            if search_term in oid or search_term.lower() in self.oid_tree.item(item_id, "text").lower():
                self.oid_tree.see(item_id)
                self.oid_tree.selection_set(item_id)
                return

        # If not found, search in oids_data and expand path if needed
        for name, oid_tuple in self.oids_data.items():
            oid_str = ".".join(str(x) for x in oid_tuple)
            if search_term in oid_str or search_term.lower() in name.lower():
                # Found it, expand the path to make it visible
                self._expand_path_to_oid(oid_tuple)
                # Now it should be in oid_to_item
                if oid_str in self.oid_to_item:
                    item_id = self.oid_to_item[oid_str]
                    self.oid_tree.see(item_id)
                    self.oid_tree.selection_set(item_id)
                return

        messagebox.showinfo("Search", f"No match found for '{search_term}'")

    def _expand_path_to_oid(self, target_oid: Tuple[int, ...]) -> None:
        """Expand the tree path to make the given OID visible."""
        if not self.oids_data:
            return

        # Start from root
        current_item = ""
        for i, num in enumerate(target_oid):
            # Find the child with this number
            found = False
            for child in self.oid_tree.get_children(current_item):
                # Get the OID from the item
                oid_str = self.oid_tree.set(child, "oid")
                if oid_str:
                    oid_parts = tuple(int(x) for x in oid_str.split("."))
                    if oid_parts == target_oid[:i+1]:
                        # This is the correct child
                        self.oid_tree.item(child, open=True)
                        current_item = child
                        found = True
                        break
            if not found:
                # The path doesn't exist yet, need to expand parent
                if current_item:
                    self.oid_tree.item(current_item, open=True)
                    # Trigger lazy loading if needed
                    self.executor.submit(self._fetch_values_for_node, current_item)
                break

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

    def _discover_table_instances(self, item: str, entry_oid: str) -> None:
        """Discover table instances and populate the tree."""
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
            except Exception:
                break

        if len(instances) == max_attempts:
            messagebox.showwarning("Warning", "Reached maximum attempts while loading instances.")

        # Get columns
        columns = []
        for name, oid_t in self.oids_data.items():
            if oid_t[:len(entry_tuple)] == entry_tuple and len(oid_t) == len(entry_tuple) + 1:
                col_num = oid_t[-1]
                col_oid = ".".join(str(x) for x in oid_t)
                columns.append((name, col_oid, col_num))
        columns.sort(key=lambda x: x[2])

        # Update UI
        def update_ui() -> None:
            # Remove existing children
            for child in self.oid_tree.get_children(item):
                self.oid_tree.delete(child)
            
            # Group columns by instance
            grouped: Dict[str, List[Tuple[str, str, str]]] = {}
            for inst in instances:
                grouped[inst] = []
                for name, col_oid, col_num in columns:
                    full_col_oid = f"{col_oid}.{inst}"
                    grouped[inst].append((name, col_oid, full_col_oid))

            # Add entry nodes under the table
            for inst, cols in grouped.items():
                entry_display = f"{entry_name}.{inst}"
                entry_full_oid = f"{entry_oid}.1.{inst}"
                mib_val = self.oid_metadata.get(entry_full_oid, {}).get("mib") or "N/A"
                entry_item = self.oid_tree.insert(item, "end", text=entry_display, values=(entry_full_oid, "", "", "Unknown", "N/A", mib_val), tags=('table-entry',))

                # Add columns under the entry
                for name, col_oid, full_col_oid in cols:
                    access = str(self.oid_metadata.get(col_oid, {}).get("access", "")).lower()
                    type_str = self.oid_metadata.get(col_oid, {}).get("type") or "Unknown"
                    access_str = self.oid_metadata.get(col_oid, {}).get("access") or "N/A"
                    if "index" in name.lower():
                        icon = "🔑"
                    elif "write" in access:
                        icon = "✏️"
                    elif "read" in access or "not-accessible" in access or "none" in access:
                        icon = "🔒"
                    else:
                        icon = "📊"

                    display_text = f"{icon} {name}"
                    mib_val = self.oid_metadata.get(col_oid, {}).get("mib") or "N/A"
                    value_here = self.oid_values.get(full_col_oid, "")
                    self.oid_tree.insert(entry_item, "end", text=display_text, values=(col_oid, inst, value_here, type_str, access_str, mib_val), tags=('evenrow', 'table-column'))

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
                if not oid_str:
                    continue

                # Fetch values for scalars (instance = "0") or table columns (instance is digit)
                if instance_str == "0":
                    fetch_oid = oid_str + ".0"
                elif instance_str and instance_str.isdigit():
                    fetch_oid = oid_str + "." + instance_str
                else:
                    continue

                if fetch_oid in self.oid_values and self.oid_values[fetch_oid] != "":
                    continue  # already fetched

                try:
                    self._log(f"Fetching value for OID {fetch_oid} (instance={instance_str})")
                    resp = requests.get(f"{self.api_url}/value", params={"oid": fetch_oid}, timeout=3)
                    resp.raise_for_status()
                    val = resp.json().get("value", "")
                    val_str = "" if val is None else str(val)
                    self.oid_values[fetch_oid] = val_str

                    # Update the UI on the main thread
                    def update_ui(c: str = child, v: str = val_str) -> None:
                        self.oid_tree.set(c, "value", v)
                    self.root.after(0, update_ui)
                    self._log(f"Fetched value for OID {fetch_oid}: {val_str}")
                except Exception as e:
                    self._log(f"Failed to fetch value for OID {fetch_oid}: {e}", "WARNING")
            else:
                # Non-leaf: optionally prefetch its leaf children; skip to avoid deep recursion
                continue
    
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
            
            # Test connection by fetching MIBs
            response = requests.get(f"{self.api_url}/mibs", timeout=5)
            response.raise_for_status()
            
            mibs_data = response.json()
            mibs = mibs_data.get("mibs", [])

            self.mibs_textbox.configure(state="normal")
            self.mibs_textbox.delete("1.0", "end")
            for mib in mibs:
                self.mibs_textbox.insert("end", f"{mib}\n")
            self.mibs_textbox.configure(state="disabled")
            
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
            # Do not fetch values eagerly; use lazy background loading on expand
            self.oid_values = {}
            
            # Fetch OID metadata
            try:
                response = requests.get(f"{self.api_url}/oid-metadata", timeout=5)
                response.raise_for_status()
                metadata_data = response.json()
                self.oid_metadata = metadata_data.get("metadata", {})
            except Exception as e:
                self._log(f"Failed to fetch OID metadata: {e}", "WARNING")
                self.oid_metadata = {}
            
            # Enable OID Tree tab when connected
            self.enable_oid_tree_tab()
            
            # Enable Traps tab when connected
            self.enable_traps_tab()
            
            # Populate OID tree with OIDs
            self._populate_oid_tree()
            
            self.connected = True
            self.connect_button.configure(text="Disconnect")
            self.status_var.set("Connected")
            self._log(f"Connected successfully. Found {len(mibs)} MIBs and {len(oids)} OIDs")
            
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
        self.mibs_textbox.configure(state="normal")
        self.mibs_textbox.delete("1.0", "end")
        self.mibs_textbox.configure(state="disabled")
        
        # Remove OID Tree and Traps tabs when disconnected
        if "OID Tree" in self.tabview._tab_dict:
            self.tabview.delete("OID Tree")
        if "Traps" in self.tabview._tab_dict:
            self.tabview.delete("Traps")
        
        self._log("Disconnected")
    
    def _log(self, message: str, level: str = "INFO") -> None:
        """Add a message to the log window. For now, just print or use status."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}\n"
        # Print to stdout for developer convenience
        print(log_entry, end="")

        # Append to GUI log area if available
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", log_entry)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            # If log area not created yet, ignore
            pass

    def _on_close(self) -> None:
        """Save GUI log and configuration then quit."""
        try:
            # Save GUI log to logs/gui.log
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            gui_log_path = logs_dir / "gui.log"
            with open(gui_log_path, "w", encoding="utf-8") as f:
                try:
                    text = self.log_text.get("1.0", "end")
                except Exception:
                    text = ""
                f.write(text)

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
            if "trap_destinations" in saved:
                # Ensure ports are integers when loading from config
                trap_dests = saved["trap_destinations"]
                if isinstance(trap_dests, list):
                    _app.trap_destinations = [(host, int(port) if isinstance(port, str) else port) for host, port in trap_dests]
                else:
                    _app.trap_destinations = trap_dests
                # Refresh destinations display if traps tab exists
                if hasattr(_app, 'dest_tree') and _app.dest_tree:
                    _app._update_dest_display()
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

