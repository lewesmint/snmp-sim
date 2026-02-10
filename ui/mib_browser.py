"""Standalone MIB Browser for SNMP testing.

This module can be run independently or embedded in other applications.
"""
from __future__ import annotations

import asyncio
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    # For type checking only - these won't be imported at runtime
    from pysnmp.hlapi.v3arch.asyncio import (
        SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity, get_cmd, next_cmd, set_cmd
    )
    from pysnmp.proto.rfc1902 import OctetString

# Runtime imports with fallbacks
try:
    from pysnmp.hlapi.v3arch.asyncio import (
        SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity, get_cmd, next_cmd, set_cmd, walk_cmd
    )
    from pysnmp.proto.rfc1902 import OctetString
    SNMP_AVAILABLE = True
    SNMP_ERROR = None
except ImportError as e:
    SNMP_AVAILABLE = False
    SNMP_ERROR = str(e)
    # Define dummy classes for runtime when pysnmp is not available
    SnmpEngine = type('SnmpEngine', (), {})
    CommunityData = type('CommunityData', (), {})
    UdpTransportTarget = type('UdpTransportTarget', (), {})
    ContextData = type('ContextData', (), {})
    ObjectType = type('ObjectType', (), {})
    ObjectIdentity = type('ObjectIdentity', (), {})
    OctetString = type('OctetString', (), {})
    def get_cmd(*_: Any, **__: Any) -> Any:  # pyright: ignore
        raise ImportError(f"SNMP not available: {SNMP_ERROR}")
    def next_cmd(*_: Any, **__: Any) -> Any:  # pyright: ignore
        raise ImportError(f"SNMP not available: {SNMP_ERROR}")
    def set_cmd(*_: Any, **__: Any) -> Any:  # pyright: ignore
        raise ImportError(f"SNMP not available: {SNMP_ERROR}")
    def walk_cmd(*_: Any, **__: Any) -> Any:  # pyright: ignore
        raise ImportError(f"SNMP not available: {SNMP_ERROR}")

try:
    from ui.common import Logger, format_snmp_value
except ImportError:
    # Fallback for when running from ui directory
    from common import Logger, format_snmp_value  # type: ignore[no-redef]


class MIBBrowserWindow:
    """Standalone MIB Browser window for SNMP operations."""
    
    def __init__(
        self,
        parent: Optional[tk.Widget] = None,
        logger: Optional[Logger] = None,
        default_host: str = "127.0.0.1",
        default_port: int = 161,
        default_community: str = "public",
        oid_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """Initialize MIB Browser.
        
        Args:
            parent: Parent widget (None for standalone window)
            logger: Optional logger instance
            default_host: Default SNMP agent host
            default_port: Default SNMP port
            default_community: Default SNMP community string
            oid_metadata: Optional OID metadata for name resolution
        """
        self.parent = parent
        self.logger = logger if logger else Logger()
        self.default_host = default_host
        self.default_port = default_port
        self.default_community = default_community
        self.oid_metadata = oid_metadata or {}
        
        # Create window
        if parent is None:
            # Standalone window
            self.window = ctk.CTk()
            self.window.title("SNMP MIB Browser")
            self.window.geometry("900x700")
            ctk.set_appearance_mode("system")
            ctk.set_default_color_theme("blue")
        else:
            # Embedded in parent
            self.window = parent
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the UI components."""
        # Main container
        if isinstance(self.window, ctk.CTk):
            container = self.window
        else:
            container = ctk.CTkFrame(self.window)
            container.pack(fill="both", expand=True)
        
        # Connection settings panel
        conn_frame = ctk.CTkFrame(container)
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
        control_panel = ctk.CTkFrame(container)
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
        buttons_frame = ctk.CTkFrame(container)
        buttons_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        get_btn = ctk.CTkButton(buttons_frame, text="GET", command=self._snmp_get, width=100)
        get_btn.pack(side="left", padx=5)
        
        getnext_btn = ctk.CTkButton(buttons_frame, text="GET NEXT", command=self._snmp_getnext, width=100)
        getnext_btn.pack(side="left", padx=5)
        
        walk_btn = ctk.CTkButton(buttons_frame, text="WALK", command=self._snmp_walk, width=100)
        walk_btn.pack(side="left", padx=5)
        
        set_btn = ctk.CTkButton(buttons_frame, text="SET", command=self._snmp_set, width=100)
        set_btn.pack(side="left", padx=5)
        
        clear_btn = ctk.CTkButton(buttons_frame, text="Clear Results", command=self._clear_results, width=120)
        clear_btn.pack(side="right", padx=5)
        
        # Results tree
        results_frame = ctk.CTkFrame(container)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Configure style for tree
        style = ttk.Style()
        style.configure("Browser.Treeview", font=('Helvetica', 11), rowheight=30)
        style.configure("Browser.Treeview.Heading", font=('Helvetica', 12, 'bold'))
        
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
            style="Browser.Treeview"
        )
        
        v_scroll.config(command=self.results_tree.yview)
        h_scroll.config(command=self.results_tree.xview)
        
        # Configure columns
        self.results_tree.heading("#0", text="Name")
        self.results_tree.heading("oid", text="OID")
        self.results_tree.heading("type", text="Type")
        self.results_tree.heading("value", text="Value")
        
        self.results_tree.column("#0", width=250, minwidth=150)
        self.results_tree.column("oid", width=300, minwidth=150)
        self.results_tree.column("type", width=150, minwidth=100)
        self.results_tree.column("value", width=250, minwidth=150, stretch=True)
        
        # Pack tree and scrollbars
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        
        # Status label
        self.status_var = ctk.StringVar(value="Ready")
        status_label = ctk.CTkLabel(container, textvariable=self.status_var, anchor="w")
        status_label.pack(fill="x", padx=10, pady=(0, 5))
    
    @staticmethod
    def _normalize_oid(oid: str) -> str:
        """Normalize OID to work with pysnmp.
        
        pysnmp requires OIDs with at least 2 numeric components.
        If a single-component OID is provided (e.g., "1", ".1"),
        append ".0" to make it valid.
        
        Args:
            oid: Original OID string
            
        Returns:
            Normalized OID string with at least 2 components
        """
        # Remove leading/trailing whitespace
        oid = oid.strip()
        
        # Count numeric components (split by dots, filter out empty strings)
        parts = [p for p in oid.split('.') if p]
        
        # If only one component, append .0
        if len(parts) == 1:
            # Return as "X.0" format
            return f"{oid.rstrip('.')}.0"
        
        return oid
    
    def _get_connection_params(self) -> tuple[str, int, str]:
        """Get connection parameters from UI."""
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            port = self.default_port
        community = self.community_var.get().strip()
        return host, port, community
    
    def _clear_results(self) -> None:
        """Clear the results tree."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.status_var.set("Results cleared")
        self.logger.log("MIB Browser: Results cleared")
    
    def _snmp_get(self) -> None:
        """Execute SNMP GET command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID")
            return
        
        # Normalize OID for pysnmp compatibility
        normalized_oid = self._normalize_oid(oid)
        if normalized_oid != oid:
            self.logger.log(f"Normalized OID: {oid} -> {normalized_oid}")
        
        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GET on {oid}...")
        self.logger.log(f"MIB Browser: GET {oid} from {host}:{port}")
        
        try:
            async def async_get() -> tuple[Any, ...]:
                from pysnmp.proto.error import StatusInformation
                
                try:
                    return await get_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(ObjectIdentity(normalized_oid))
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get('errorIndication', str(e))
                    return (error_indication, None, None, [])

            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(async_get())
            _ = errorIndex  # Unused but part of SNMP response tuple
            
            if errorIndication:
                self.status_var.set(f"Error: {errorIndication}")
                self.logger.log(f"MIB Browser GET error: {errorIndication}", "ERROR")
                messagebox.showerror("SNMP GET Error", str(errorIndication))
                return
            elif errorStatus:
                self.status_var.set(f"Error: {errorStatus.prettyPrint()}")
                self.logger.log(f"MIB Browser GET error: {errorStatus.prettyPrint()}", "ERROR")
                messagebox.showerror("SNMP GET Error", errorStatus.prettyPrint())
                return
            
            # Display result
            self._clear_results()
            for varBind in varBinds:
                oid_str = str(varBind[0])
                value = format_snmp_value(varBind[1])
                type_str = type(varBind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                
                self.results_tree.insert(
                    "", "end",
                    text=name,
                    values=(oid_str, type_str, value)
                )
            
            self.status_var.set(f"GET completed: {len(varBinds)} result(s)")
            self.logger.log(f"MIB Browser: GET {oid} returned {len(varBinds)} result(s)")
        
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            self.logger.log(f"MIB Browser GET error: {e}", "ERROR")
            messagebox.showerror("SNMP GET Error", str(e))
    
    def _snmp_getnext(self) -> None:
        """Execute SNMP GETNEXT command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID")
            return
        
        # Normalize OID for pysnmp compatibility
        normalized_oid = self._normalize_oid(oid)
        if normalized_oid != oid:
            self.logger.log(f"Normalized OID: {oid} -> {normalized_oid}")
        
        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GETNEXT on {oid}...")
        self.logger.log(f"MIB Browser: GETNEXT {oid} from {host}:{port}")
        
        try:
            async def async_next() -> tuple[Any, ...]:
                # next_cmd returns a coroutine that yields ONE result
                from pysnmp.proto.error import StatusInformation
                target = await UdpTransportTarget.create((host, port))
                
                try:
                    return await next_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(ObjectIdentity(normalized_oid))
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get('errorIndication', str(e))
                    return (error_indication, None, None, [])

            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(async_next())
            _ = errorIndex  # Unused but part of SNMP response tuple
            
            if errorIndication:
                self.status_var.set(f"Error: {errorIndication}")
                self.logger.log(f"MIB Browser GETNEXT error: {errorIndication}", "ERROR")
                messagebox.showerror("SNMP GETNEXT Error", str(errorIndication))
                return
            elif errorStatus:
                self.status_var.set(f"Error: {errorStatus.prettyPrint()}")
                self.logger.log(f"MIB Browser GETNEXT error: {errorStatus.prettyPrint()}", "ERROR")
                messagebox.showerror("SNMP GETNEXT Error", errorStatus.prettyPrint())
                return
            
            # Display result
            self._clear_results()
            for varBind in varBinds:
                oid_str = str(varBind[0])
                value = format_snmp_value(varBind[1])
                type_str = type(varBind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                
                self.results_tree.insert(
                    "", "end",
                    text=name,
                    values=(oid_str, type_str, value)
                )
            
            self.status_var.set(f"GETNEXT completed: {len(varBinds)} result(s)")
            self.logger.log(f"MIB Browser: GETNEXT {oid} returned {len(varBinds)} result(s)")
        
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            self.logger.log(f"MIB Browser GETNEXT error: {e}", "ERROR")
            messagebox.showerror("SNMP GETNEXT Error", str(e))
    
    def _snmp_walk(self) -> None:
        """Execute SNMP WALK command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID")
            return
        
        # Normalize OID for pysnmp compatibility
        normalized_oid = self._normalize_oid(oid)
        if normalized_oid != oid:
            self.logger.log(f"Normalized OID: {oid} -> {normalized_oid}")
        
        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing WALK on {oid}...")
        self.logger.log(f"MIB Browser: WALK {oid} from {host}:{port}")
        
        try:
            # Clear previous results
            self._clear_results()

            async def async_walk() -> list[tuple[Any, ...]]:
                from pysnmp.proto.error import StatusInformation
                
                walk_results = []
                target = await UdpTransportTarget.create((host, port))
                
                try:
                    # walk_cmd returns async generator directly
                    iterator = walk_cmd(
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(ObjectIdentity(normalized_oid))
                    )
                    async for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                        walk_results.append((errorIndication, errorStatus, errorIndex, varBinds))
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get('errorIndication', str(e))
                    walk_results.append((error_indication, None, None, []))
                
                return walk_results

            walk_results = asyncio.run(async_walk())
            display_results = []
            
            for errorIndication, errorStatus, errorIndex, varBinds in walk_results:
                _ = errorIndex  # Unused but part of SNMP response tuple
                if errorIndication:
                    self.status_var.set(f"Error: {errorIndication}")
                    self.logger.log(f"MIB Browser WALK error: {errorIndication}", "ERROR")
                    messagebox.showerror("SNMP WALK Error", str(errorIndication))
                    return
                elif errorStatus:
                    self.status_var.set(f"Error: {errorStatus}")
                    self.logger.log(f"MIB Browser WALK error: {errorStatus}", "ERROR")
                    messagebox.showerror("SNMP WALK Error", str(errorStatus))
                    return
                
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    value = format_snmp_value(varBind[1])
                    type_str = type(varBind[1]).__name__
                    display_results.append((oid_str, type_str, value))
            
            # Build hierarchical tree
            if display_results:
                self._build_hierarchical_tree(display_results)
                self.status_var.set(f"WALK completed: {len(display_results)} result(s)")
                self.logger.log(f"MIB Browser: WALK {oid} returned {len(display_results)} result(s)")
            else:
                self.status_var.set("WALK completed: No results")
                self.logger.log(f"MIB Browser: WALK {oid} returned no results")
        
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            self.logger.log(f"MIB Browser WALK error: {e}", "ERROR")
            messagebox.showerror("SNMP WALK Error", str(e))
    
    def _snmp_set(self) -> None:
        """Execute SNMP SET command."""
        oid = self.oid_var.get().strip()
        value = self.value_var.get().strip()
        
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID")
            return
        if not value:
            messagebox.showwarning("No Value", "Please enter a value to set")
            return
        
        # Normalize OID for pysnmp compatibility
        normalized_oid = self._normalize_oid(oid)
        if normalized_oid != oid:
            self.logger.log(f"Normalized OID: {oid} -> {normalized_oid}")
        
        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing SET on {oid}...")
        self.logger.log(f"MIB Browser: SET {oid} = {value} on {host}:{port}")
        
        try:
            # SNMP SET - using OctetString by default
            # In a production tool, you'd want type selection UI
            async def async_set() -> tuple[Any, ...]:
                from pysnmp.proto.error import StatusInformation
                
                try:
                    return await set_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(ObjectIdentity(normalized_oid), OctetString(value))
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get('errorIndication', str(e))
                    return (error_indication, None, None, [])

            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(async_set())
            _ = errorIndex  # Unused but part of SNMP response tuple
            _ = varBinds  # Unused but part of SNMP response tuple
            
            if errorIndication:
                self.status_var.set(f"Error: {errorIndication}")
                self.logger.log(f"MIB Browser SET error: {errorIndication}", "ERROR")
                messagebox.showerror("SNMP SET Error", str(errorIndication))
                return
            elif errorStatus:
                self.status_var.set(f"Error: {errorStatus.prettyPrint()}")
                self.logger.log(f"MIB Browser SET error: {errorStatus.prettyPrint()}", "ERROR")
                messagebox.showerror("SNMP SET Error", errorStatus.prettyPrint())
                return
            
            self.status_var.set("SET completed successfully")
            self.logger.log(f"MIB Browser: SET {oid} = {value} successful")
            messagebox.showinfo("Success", f"Value set successfully on {oid}")
            
            # Optionally, refresh with GET to show new value
            self._snmp_get()
        
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            self.logger.log(f"MIB Browser SET error: {e}", "ERROR")
            messagebox.showerror("SNMP SET Error", str(e))
    
    def _get_name_from_oid(self, oid_str: str) -> str:
        """Get human-readable name from OID using metadata."""
        # Try to find exact match
        if oid_str in self.oid_metadata:
            return str(self.oid_metadata[oid_str].get("name", oid_str))
        
        # Try to find base OID (without instance)
        parts = oid_str.split('.')
        for i in range(len(parts), 0, -1):
            base_oid = '.'.join(parts[:i])
            if base_oid in self.oid_metadata:
                instance = '.'.join(parts[i:])
                name = str(self.oid_metadata[base_oid].get("name", base_oid))
                return f"{name}.{instance}" if instance else name
        
        return oid_str
    
    def _build_hierarchical_tree(self, results: list[tuple[str, str, str]]) -> None:
        """Build a hierarchical tree from WALK results."""
        # Create a mapping of OID -> item
        oid_to_item: Dict[str, str] = {}
        
        for oid_str, type_str, value in results:
            parts = oid_str.split('.')
            parent_oid = '.'.join(parts[:-1]) if len(parts) > 1 else ""
            
            # Find parent item
            parent_item = ""
            if parent_oid and parent_oid in oid_to_item:
                parent_item = oid_to_item[parent_oid]
            
            # Get name for this OID
            name = self._get_name_from_oid(oid_str)
            
            # Insert into tree
            item = self.results_tree.insert(
                parent_item, "end",
                text=name,
                values=(oid_str, type_str, value)
            )
            
            oid_to_item[oid_str] = item
        
        # Open top-level items
        for item in self.results_tree.get_children():
            self.results_tree.item(item, open=True)
    
    def run(self) -> None:
        """Run the standalone browser window."""
        if isinstance(self.window, ctk.CTk):
            self.window.mainloop()
    
    def set_oid_metadata(self, metadata: Dict[str, Dict[str, Any]]) -> None:
        """Update OID metadata for name resolution."""
        self.oid_metadata = metadata


def main() -> None:
    """Run standalone MIB Browser."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SNMP MIB Browser")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=161, help="SNMP port")
    parser.add_argument("--community", default="public", help="SNMP community string")
    
    args = parser.parse_args()
    
    browser = MIBBrowserWindow(
        default_host=args.host,
        default_port=args.port,
        default_community=args.community
    )
    browser.run()


if __name__ == "__main__":
    main()
