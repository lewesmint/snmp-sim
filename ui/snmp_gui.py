import customtkinter as ctk
from tkinter import messagebox, ttk
from typing import Any, Dict, Tuple
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
        # Executor for background value fetching
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self._setup_ui()
        self._log("Application started")

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

        # Tab 1: OID Tree View
        self.tabview.add("OID Tree")
        self._setup_oid_tab()

        # Tab 2: Configuration
        self.tabview.add("Configuration")
        self._setup_config_tab()

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

        # Treeview for OIDs (add columns for instance, value, type, access)
        self.oid_tree = ttk.Treeview(tree_frame, columns=("oid", "instance", "value", "type", "access"),
                                     show="tree headings", style="OID.Treeview")
        self.oid_tree.heading("#0", text="📋 MIB/Object")
        self.oid_tree.heading("oid", text="🔢 OID")
        self.oid_tree.heading("instance", text="Instance")
        self.oid_tree.heading("value", text="💾 Value")
        self.oid_tree.heading("type", text="Type")
        self.oid_tree.heading("access", text="Access")

        # Configure columns with borders for better separation
        self.oid_tree.column("#0", width=250, minwidth=150, stretch=True)
        self.oid_tree.column("oid", width=200, minwidth=150, stretch=True, anchor="w")
        self.oid_tree.column("instance", width=80, minwidth=60, stretch=False, anchor="center")
        self.oid_tree.column("value", width=200, minwidth=100, stretch=True, anchor="w")
        self.oid_tree.column("type", width=120, minwidth=80, stretch=False, anchor="w")
        self.oid_tree.column("access", width=100, minwidth=80, stretch=False, anchor="center")

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
        # Placeholder data
        self._populate_oid_tree()
    
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

        if self.oids_data:
            # Build hierarchical tree
            root = self.oid_tree.insert("", "end", text="MIB Tree", values=("", "", "", "", ""))
            self.oid_tree.item(root, open=True)  # Expand root by default
            self._build_tree_from_oids(root, self.oids_data)
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

        # Now build the Treeview from the tree dict
        self._insert_tree_nodes(parent, tree, ())
    
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

                # Add icon based on type
                if has_instance:
                    icon = "📊"  # Scalar with instance
                    instance_str = "0"
                    instance_oid_str = oid_str + ".0"
                    val = self.oid_values.get(instance_oid_str, "")
                else:
                    icon = "📄"  # Regular leaf
                    instance_str = ""
                    val = self.oid_values.get(oid_str, "")

                display_text = f"{icon} {stored_name}" if stored_name else f"{icon} {key}"
                node = self.oid_tree.insert(parent, "end", text=display_text,
                                           values=(oid_str, instance_str, val, "", ""),
                                           tags=(row_tag,))
            else:
                # Folder/container node
                icon = "📁"  # Folder icon
                display_text = f"{icon} {stored_name}" if stored_name else f"{icon} {key}"

                node = self.oid_tree.insert(parent, "end", text=display_text,
                                           values=(oid_str, "", "", "", ""),
                                           tags=(row_tag,))
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

                # For scalars (instance = "0"), fetch value from instance OID
                if instance_str == "0":
                    fetch_oid = oid_str + ".0"
                else:
                    fetch_oid = oid_str

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
            
            # Populate OID tree with OIDs
            self._populate_oid_tree()
            
            self.connected = True
            self.connect_button.configure(text="Disconnect")
            self.status_var.set("Connected")
            self._log(f"Connected successfully. Found {len(mibs)} MIBs and {len(oids)} OIDs")

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
        # Clear OID tree
        for item in self.oid_tree.get_children():
            self.oid_tree.delete(item)
        self.oids_data = {}
        self._populate_oid_tree()  # Back to placeholder
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

            # Save last used host/port to data/gui_config.yaml (fallback to JSON)
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            cfg = {"host": self.host_var.get(), "port": self.port_var.get()}
            try:
                import yaml

                with open(data_dir / "gui_config.yaml", "w", encoding="utf-8") as f:
                    yaml.safe_dump(cfg, f)
            except Exception:
                # Fallback to JSON if PyYAML not available
                with open(data_dir / "gui_config.json", "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            try:
                self.root.quit()
            except Exception:
                pass


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

    # Load saved config if available
    try:
        cfg_path_yaml = Path("data/gui_config.yaml")
        cfg_path_json = Path("data/gui_config.json")
        saved = None
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
    except Exception:
        pass

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

