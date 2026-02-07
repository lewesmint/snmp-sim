import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Any
import requests
from datetime import datetime


class SNMPControllerGUI:
    """GUI application for controlling SNMP agent with modern tabbed interface."""
    
    def __init__(self, root: tk.Tk, api_url: str = "http://127.0.0.1:8800"):
        self.root = root
        self.api_url = api_url
        self.root.title("SNMP Simulator GUI")
        self.root.geometry("800x600")
        
        # Set modern style
        style = ttk.Style()
        style.theme_use('clam')  # Modern theme
        
        self.connected = False
        self.oids_data: dict[str, tuple[int, ...]] = {}  # Store OIDs for rebuilding (name -> OID tuple)
        self.oid_values: dict[str, str] = {}  # oid_str -> value
        self._setup_ui()
        self._log("Application started")
    
    def _setup_ui(self) -> None:
        """Setup the user interface components."""
        # Main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: OID Tree View
        self._setup_oid_tab()
        
        # Tab 2: Configuration
        self._setup_config_tab()
        
        # Log window below notebook
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, side=tk.BOTTOM, padx=10, pady=(0, 5))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, font=('Courier', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

        # Status bar
        self.status_var = tk.StringVar(value="Disconnected")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def _setup_oid_tab(self) -> None:
        """Setup the OID tree view tab."""
        oid_frame = ttk.Frame(self.notebook)
        self.notebook.add(oid_frame, text="OID Tree")
        # Toolbar with expand/collapse
        toolbar = ttk.Frame(oid_frame)
        toolbar.pack(fill=tk.X, padx=6, pady=(4, 6))

        expand_btn = ttk.Button(toolbar, text="Expand All", command=self._expand_all)
        collapse_btn = ttk.Button(toolbar, text="Collapse All", command=self._collapse_all)
        expand_btn.pack(side=tk.LEFT, padx=(0, 6))
        collapse_btn.pack(side=tk.LEFT)
        
        # Treeview for OIDs
        self.oid_tree = ttk.Treeview(oid_frame, columns=("oid", "value"), show="tree headings")
        self.oid_tree.heading("#0", text="MIB/Object")
        self.oid_tree.heading("oid", text="OID")
        self.oid_tree.heading("value", text="Value")
        self.oid_tree.column("oid", width=200)
        self.oid_tree.column("value", width=200)
        
        # Scrollbars
        v_scroll = ttk.Scrollbar(oid_frame, orient=tk.VERTICAL, command=self.oid_tree.yview)
        h_scroll = ttk.Scrollbar(oid_frame, orient=tk.HORIZONTAL, command=self.oid_tree.xview)
        self.oid_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        self.oid_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Placeholder data
        self._populate_oid_tree()
    
    def _setup_config_tab(self) -> None:
        """Setup the configuration tab."""
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")
        
        # Connection frame
        conn_frame = ttk.LabelFrame(config_frame, text="Connection", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Host
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.host_var = tk.StringVar(value="127.0.0.1")
        host_entry = ttk.Entry(conn_frame, textvariable=self.host_var)
        host_entry.grid(row=0, column=1, sticky=tk.W + tk.E, padx=(5, 0), pady=2)
        
        # Port
        ttk.Label(conn_frame, text="Port:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.port_var = tk.StringVar(value="8800")
        port_entry = ttk.Entry(conn_frame, textvariable=self.port_var)
        port_entry.grid(row=1, column=1, sticky=tk.W + tk.E, padx=(5, 0), pady=2)
        
        # Connect/Disconnect button
        self.connect_button = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_button.grid(row=2, column=0, columnspan=2, pady=10)
        
        conn_frame.columnconfigure(1, weight=1)
        
        # MIBs frame
        mibs_frame = ttk.LabelFrame(config_frame, text="Implemented MIBs", padding=10)
        mibs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Listbox for MIBs
        self.mibs_listbox = tk.Listbox(mibs_frame, height=10)
        mibs_scroll = ttk.Scrollbar(mibs_frame, orient=tk.VERTICAL, command=self.mibs_listbox.yview)
        self.mibs_listbox.configure(yscrollcommand=mibs_scroll.set)
        
        self.mibs_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mibs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
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
            root = self.oid_tree.insert("", "end", text="MIB Tree", values=("", ""))
            self.oid_tree.item(root, open=True)  # Expand root by default
            self._build_tree_from_oids(root, self.oids_data)
        # If not connected or no data, leave empty
    
    def _build_tree_from_oids(self, parent: str, oids: dict[str, tuple[int, ...]]) -> None:
        """Recursively build the tree from OID dict."""
        # Create a tree structure
        tree: dict[int | str, Any] = {}
        for name, oid_tuple in oids.items():
            current = tree
            for num in oid_tuple:
                if num not in current:
                    current[num] = {}
                current = current[num]
            # At the leaf, store the name
            current['__name__'] = name
        
        # Now build the Treeview from the tree dict
        self._insert_tree_nodes(parent, tree, ())
    
    def _insert_tree_nodes(self, parent: str, tree: dict[int | str, Any], current_oid: tuple[int, ...]) -> None:
        """Insert nodes into Treeview recursively."""
        # Sort keys without comparing ints to strings (avoid TypeError)
        for key, value in sorted(tree.items(), key=lambda kv: (isinstance(kv[0], str), str(kv[0]))):
            if key == '__name__':
                continue
            # Ensure key is an int before extending current_oid so typing stays as tuple[int, ...]
            if not isinstance(key, int):
                continue

            new_oid = current_oid + (key,)
            oid_str = ".".join(str(x) for x in new_oid)

            # Determine if this node is a leaf (only a name) or a folder (has children)
            child_keys = [k for k in value.keys() if k != '__name__']
            is_leaf = len(child_keys) == 0

            # Prefer stored name for leaves, otherwise try name on this node
            stored_name = value.get('__name__')
            if is_leaf:
                display_text = stored_name if stored_name else str(key)
            else:
                # Folder: show a friendly name if available, otherwise the numeric key
                display_text = stored_name if stored_name else str(key)
                # Mark folders visually by trailing slash
                display_text = f"{display_text}/"

            # Fill value column for leaves
            if is_leaf:
                val = self.oid_values.get(oid_str, "")
                node = self.oid_tree.insert(parent, "end", text=display_text, values=(oid_str, val))
            else:
                node = self.oid_tree.insert(parent, "end", text=display_text, values=(oid_str, ""))
                # Recurse into children
                self._insert_tree_nodes(node, value, new_oid)
    
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
            
            self.mibs_listbox.delete(0, tk.END)
            for mib in mibs:
                self.mibs_listbox.insert(tk.END, mib)
            
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
            # Fetch scalar values for each leaf OID (may be slow for many OIDs)
            self.oid_values = {}
            for name, oid_tuple in self.oids_data.items():
                try:
                    oid_str = ".".join(str(x) for x in oid_tuple)
                    resp = requests.get(f"{self.api_url}/value", params={"oid": oid_str}, timeout=3)
                    resp.raise_for_status()
                    val = resp.json().get("value", "")
                    self.oid_values[oid_str] = str(val)
                except Exception as e:
                    # Don't fail the whole connect for value fetch errors
                    self._log(f"Failed to fetch value for {name} ({oid_tuple}): {e}", "WARNING")
            
            # Populate OID tree with OIDs
            self._populate_oid_tree()
            
            self.connected = True
            self.connect_button.config(text="Disconnect")
            self.status_var.set("Connected")
            self._log(f"Connected successfully. Found {len(mibs)} MIBs and {len(oids)} OIDs")
            
        except requests.exceptions.ConnectionError:
            error_msg = "Cannot connect to REST API. Is the agent running?"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            messagebox.showerror("Connection Error", error_msg)
            
        except Exception as e:
            error_msg = f"Error connecting: {str(e)}"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            messagebox.showerror("Error", error_msg)
    
    def _disconnect(self) -> None:
        """Disconnect from the REST API."""
        self.connected = False
        self.connect_button.config(text="Connect")
        self.status_var.set("Disconnected")
        self.mibs_listbox.delete(0, tk.END)
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
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            # If log area not created yet, ignore
            pass


def main() -> None:
    """Main entry point for the GUI application."""
    root = tk.Tk()
    _app = SNMPControllerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

