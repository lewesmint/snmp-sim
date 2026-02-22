"""Standalone MIB Browser for SNMP testing.

This module can be run independently or embedded in other applications.
"""

# pylint: disable=broad-exception-caught,attribute-defined-outside-init,no-else-return
# pylint: disable=too-many-lines,too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-locals,too-many-statements
# pylint: disable=too-many-nested-blocks,too-many-branches

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

import customtkinter as ctk
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    next_cmd,
    set_cmd,
    walk_cmd,
)
from pysnmp.proto.error import StatusInformation
from pysnmp.proto.rfc1902 import OctetString
from pysnmp.smi import builder, view

from ui.common import Logger, format_snmp_value


def _ensure_default_tk_root() -> None:
    """Ensure tkinter has a default root for variable creation in headless contexts."""
    if tk._default_root is not None:  # type: ignore[attr-defined]
        return
    is_test_context = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not is_test_context:
        return
    try:
        tk._default_root = tk.Tcl()  # type: ignore[attr-defined]
    except Exception:
        return


_ensure_default_tk_root()


class MIBBrowserWindow:
    """Standalone MIB Browser window for SNMP operations."""

    def __init__(
        self,
        parent: Optional[tk.Widget] = None,
        logger: Optional[Logger] = None,
        default_host: str = "127.0.0.1",
        default_port: int = 161,
        default_community: str = "public",
        oid_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """Initialize MIB Browser.

        Args:
            parent: Parent widget (None for standalone window)
            logger: Optional logger instance
            default_host: Default SNMP agent host
            default_port: Default SNMP port
            default_community: Default SNMP community string
            oid_metadata: Optional OID metadata for name resolution (DEPRECATED - use MIB loading)
        """
        self.parent = parent
        self.logger = logger if logger else Logger()
        self.default_host = default_host
        self.default_port = default_port
        self.default_community = default_community
        # oid_metadata is deprecated - kept for backward compatibility but not used
        self.oid_metadata = oid_metadata or {}

        # Initialize pysnmp MIB system
        self.mib_builder = builder.MibBuilder()
        self.mib_view = view.MibViewController(self.mib_builder)
        self.loaded_mibs: list[str] = []
        self.mib_dependencies: dict[str, list[str]] = {}  # mib_name -> list of required imports
        self.unsatisfied_mibs: dict[str, list[str]] = {}  # mib_name -> list of missing dependencies
        self.cached_mib_checkbuttons: dict[str, ctk.BooleanVar] = {}

        # Load MIBs from standard locations and compiled-mibs directory
        self._setup_mib_paths()

        # Icons for tree display (matching OID tree)
        self.icons: Dict[str, Any] = {}
        self._load_icons()

        # Track agent results separately
        self.agent_results: Dict[str, Dict[str, Any]] = {}  # host:port -> {operations, etc.}
        self.agent_tree_items: Dict[str, str] = {}  # host:port -> tree_item_id

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

    def _setup_mib_paths(self) -> None:
        """Setup MIB search paths for pysnmp."""
        # Create and add cache directory for user-loaded MIBs
        self.mib_cache_dir = Path.home() / ".mib-browser-cache"
        self.mib_cache_dir.mkdir(parents=True, exist_ok=True)
        self.mib_builder.addMibSources(builder.DirMibSource(str(self.mib_cache_dir)))
        self.logger.log(f"Added MIB cache: {self.mib_cache_dir}", "DEBUG")

        # Add compiled-mibs directory if it exists
        compiled_mibs = Path("compiled-mibs")
        if compiled_mibs.exists():
            self.mib_builder.addMibSources(builder.DirMibSource(str(compiled_mibs.absolute())))
            self.logger.log(f"Added MIB source: {compiled_mibs.absolute()}", "DEBUG")

        # Add system MIB directories
        system_mib_paths = [
            Path.home() / ".pysnmp" / "mibs",
            Path("/usr/share/snmp/mibs"),
            Path("/usr/share/mibs"),
        ]

        for mib_path in system_mib_paths:
            if mib_path.exists():
                self.mib_builder.addMibSources(builder.DirMibSource(str(mib_path)))
                self.logger.log(f"Added MIB source: {mib_path}", "DEBUG")

    def _load_icons(self) -> None:
        """Load icons for the results tree (same as OID tree)."""
        icons_dir = Path(__file__).parent / "icons"

        def make_generated(color: str, inner: Optional[str]) -> tk.PhotoImage:
            """Create a simple colored square icon."""
            # Create a 16x16 colored square
            img = tk.PhotoImage(width=16, height=16)
            # PhotoImage.put expects string color, not tuple for coordinates
            for x in range(16):
                for y in range(16):
                    img.put(color, (x, y))
            if inner:
                for x in range(4, 12):
                    for y in range(4, 12):
                        img.put(inner, (x, y))
            return img

        icon_specs = {
            "folder": ("#fbbf24", None),
            "table": ("#3b82f6", None),
            "lock": ("#9ca3af", None),
            "edit": ("#10b981", None),
            "doc": ("#ffffff", "#e5e7eb"),
            "chart": ("#a78bfa", None),
            "key": ("#f97316", None),
        }

        for name, (color, inner) in icon_specs.items():
            try:
                png_path = icons_dir / f"{name}.png"
                if png_path.exists():
                    self.icons[name] = tk.PhotoImage(file=str(png_path))
                else:
                    self.icons[name] = make_generated(color, inner)
            except Exception:
                # On any error fall back to generated icon
                self.icons[name] = make_generated(color, inner)

    def _setup_ui(self) -> None:
        """Setup the UI components."""
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

    def _setup_browser_tab(self) -> None:
        """Setup the SNMP browser tab."""
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
            buttons_frame, text="GET NEXT", command=self._snmp_getnext, width=100
        )
        getnext_btn.pack(side="left", padx=5)

        walk_btn = ctk.CTkButton(buttons_frame, text="WALK", command=self._snmp_walk, width=100)
        walk_btn.pack(side="left", padx=5)

        set_btn = ctk.CTkButton(buttons_frame, text="SET", command=self._snmp_set, width=100)
        set_btn.pack(side="left", padx=5)

        clear_btn = ctk.CTkButton(
            buttons_frame, text="Clear Results", command=self._clear_results, width=120
        )
        clear_btn.pack(side="right", padx=5)

        # Toolbar with expand/collapse controls
        toolbar_frame = ctk.CTkFrame(browser_tab)
        toolbar_frame.pack(fill="x", padx=10, pady=(0, 10))

        expand_btn = ctk.CTkButton(
            toolbar_frame, text="Expand All", command=self._expand_all, width=100
        )
        expand_btn.pack(side="left", padx=(0, 6))

        collapse_btn = ctk.CTkButton(
            toolbar_frame, text="Collapse All", command=self._collapse_all, width=100
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
        """Setup the MIB Manager tab for browsing and caching MIBs."""
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

    def _extract_mib_imports(self, mib_file_path: Path) -> list[str]:
        """Extract IMPORTS from a MIB file.

        Args:
            mib_file_path: Path to .mib or .py MIB file

        Returns:
            List of imported MIB names
        """
        imports = []
        try:
            content = mib_file_path.read_text(encoding="utf-8", errors="ignore")

            # For .py files (compiled), look for FROM statements
            if mib_file_path.suffix == ".py":
                for line in content.split("\n"):
                    # Look for patterns like: FROM SNMPv2-MIB import ...
                    if " FROM " in line and "import" in line:
                        parts = line.split()
                        idx = parts.index("FROM") if "FROM" in parts else -1
                        if idx >= 0 and idx + 1 < len(parts):
                            mib_name = parts[idx + 1]
                            if mib_name and mib_name not in imports:
                                imports.append(mib_name)
            else:
                # For .mib text files, look for IMPORTS section
                in_imports = False
                import_block = ""

                for line in content.split("\n"):
                    if "IMPORTS" in line:
                        in_imports = True
                    elif in_imports:
                        if ";" in line:
                            import_block += line.split(";")[0]
                            break
                        import_block += line

                # Parse imports: look for FROM clauses
                if import_block:
                    for part in import_block.split("FROM"):
                        if part.strip():
                            mib_name = part.strip().split()[0]
                            if mib_name and mib_name.replace("-", "").replace("_", "").isalnum():
                                if mib_name not in imports:
                                    imports.append(mib_name)

        except Exception as e:
            self.logger.log(f"Error extracting imports from {mib_file_path.name}: {e}", "WARNING")

        return imports

    def _find_mib_file_in_cache(self, mib_name: str) -> Optional[Path]:
        """Find a MIB file by name in cache ONLY.

        Args:
            mib_name: Name of MIB to find

        Returns:
            Path to MIB file in cache or None if not found
        """
        # Check cache only for original MIB source files
        for ext in [".mib", ".txt", ".my", ".asn", ".asn1"]:
            cache_file = self.mib_cache_dir / f"{mib_name}{ext}"
            if cache_file.exists():
                return cache_file
        return None

    def _find_mib_file(self, mib_name: str) -> Optional[Path]:
        """Find a MIB file by name in cache and system paths.

        Args:
            mib_name: Name of MIB to find

        Returns:
            Path to MIB file or None if not found
        """
        # Check cache first
        cache_py = self.mib_cache_dir / f"{mib_name}.py"
        cache_mib = self.mib_cache_dir / f"{mib_name}.mib"
        if cache_py.exists():
            return cache_py
        if cache_mib.exists():
            return cache_mib

        # Check compiled-mibs
        compiled_py = Path(__file__).parent.parent / "compiled-mibs" / f"{mib_name}.py"
        if compiled_py.exists():
            return compiled_py

        # Check system paths
        system_paths = [
            Path.home() / ".pysnmp" / "mibs",
            Path("/usr/share/snmp/mibs"),
            Path("/usr/share/mibs"),
        ]
        for sys_path in system_paths:
            for ext in [".py", ".mib"]:
                mib_file = sys_path / f"{mib_name}{ext}"
                if mib_file.exists():
                    return mib_file

        return None

    def _is_mib_loaded_in_pysnmp(self, mib_name: str) -> bool:
        """Verify if a MIB is actually loaded.

        Only trust our internal tracking - a MIB is loaded if we explicitly
        loaded it and didn't mark it as unsatisfied.

        Also verify the file exists IN CACHE - only cache files count as available.
        """
        # File must exist in CACHE (not just system)
        if not self._find_mib_file_in_cache(mib_name):
            return False

        # And it must be in our loaded list and not marked as unsatisfied
        return mib_name in self.loaded_mibs and mib_name not in self.unsatisfied_mibs

    def _resolve_mib_dependencies(self, mib_name: str) -> tuple[list[str], list[str]]:
        """Resolve all dependencies for a MIB.

        Args:
            mib_name: Name of MIB to resolve

        Returns:
            Tuple of (resolved_deps, missing_deps)
        """
        resolved = []
        missing = []
        visited = set()

        def _recurse(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            # Find the MIB file
            mib_file = self._find_mib_file(name)
            if not mib_file:
                if name not in missing:
                    missing.append(name)
                return

            # Extract imports
            imports = self._extract_mib_imports(mib_file)
            for imp in imports:
                _recurse(imp)

            if name not in resolved and name != mib_name:  # Don't add the main MIB itself
                resolved.append(name)

        _recurse(mib_name)
        return resolved, missing

    def load_mib(self, mib_names: list[str] | str) -> tuple[list[str], list[str]]:
        """Load MIB module(s) into the MIB browser.

        Args:
            mib_names: Single MIB name or list of MIB names to load

        Returns:
            Tuple of (successfully_loaded, failed)
        """
        if isinstance(mib_names, str):
            mib_names = [mib_names]

        loaded = []
        failed = []

        for mib_name in mib_names:
            try:
                # Check dependencies first
                resolved_deps, missing_deps = self._resolve_mib_dependencies(mib_name)

                if missing_deps:
                    # Mark as having unsatisfied dependencies
                    self.unsatisfied_mibs[mib_name] = missing_deps
                    error_msg = (
                        f"Cannot load {mib_name}: missing dependencies: {', '.join(missing_deps)}"
                    )
                    failed.append(mib_name)
                    self.logger.log(error_msg, "WARNING")
                else:
                    # Load dependencies in order - track which ones actually succeed
                    failed_deps = []
                    for dep in resolved_deps:
                        try:
                            self.mib_builder.loadModules(dep)
                            if dep not in self.loaded_mibs:
                                self.loaded_mibs.append(dep)
                            self.logger.log(f"Loaded dependency: {dep}", "DEBUG")
                        except Exception as e:
                            failed_deps.append(dep)
                            self.logger.log(f"Failed to load dependency {dep}: {e}", "ERROR")

                    # Check if all dependencies loaded successfully
                    if failed_deps:
                        # Mark main MIB as having unsatisfied dependencies
                        self.unsatisfied_mibs[mib_name] = failed_deps
                        error_msg = (
                            f"Cannot load {mib_name}: {len(failed_deps)} dependencies "
                            f"failed to load: {', '.join(failed_deps)}"
                        )
                        failed.append(mib_name)
                        self.logger.log(error_msg, "ERROR")
                    else:
                        # All dependencies loaded, now load main MIB
                        try:
                            self.mib_builder.loadModules(mib_name)
                            if mib_name not in self.loaded_mibs:
                                self.loaded_mibs.append(mib_name)

                            # Store dependencies and mark as satisfied
                            self.mib_dependencies[mib_name] = resolved_deps
                            if mib_name in self.unsatisfied_mibs:
                                del self.unsatisfied_mibs[mib_name]

                            loaded.append(mib_name)
                            self.logger.log(
                                f"Loaded MIB: {mib_name} (with {len(resolved_deps)} dependencies)",
                                "INFO",
                            )
                        except Exception as e:
                            # Main MIB failed to load
                            self.unsatisfied_mibs[mib_name] = [f"Failed to load: {e}"]
                            failed.append(mib_name)
                            self.logger.log(f"Failed to load main MIB {mib_name}: {e}", "ERROR")
            except Exception as e:
                failed.append(mib_name)
                self.logger.log(f"Failed to load MIB {mib_name}: {e}", "WARNING")

        return loaded, failed

    def unload_mib(self, mib_name: str) -> bool:
        """Unload a MIB module from the browser.

        Args:
            mib_name: Name of MIB to unload

        Returns:
            True if successfully unloaded
        """
        if mib_name in self.loaded_mibs:
            self.loaded_mibs.remove(mib_name)
            # Note: pysnmp doesn't provide unload, so we just track it
            self.logger.log(f"Unloaded MIB: {mib_name}", "INFO")
            return True
        return False

    def get_loaded_mibs(self) -> list[str]:
        """Get list of currently loaded MIBs."""
        return self.loaded_mibs.copy()

    def _get_oid_metadata_from_mib(self, oid_str: str) -> Dict[str, Any]:
        """Extract metadata for an OID from loaded MIBs.

        Args:
            oid_str: OID in dotted notation (e.g., "1.3.6.1.2.1.1.1")

        Returns:
            Dictionary with keys: name, mib, type, access, description
        """
        metadata: Dict[str, Any] = {}

        try:
            # Try to resolve OID to MIB symbol
            oid_tuple = tuple(int(x) for x in oid_str.split(".") if x)

            # Search through loaded MIBs for this OID
            for mod_name in self.loaded_mibs:
                try:
                    mib_symbols = self.mib_builder.mibSymbols.get(mod_name, {})
                    for symbol_name, symbol_obj in mib_symbols.items():
                        # Check if this symbol has an OID that matches
                        if hasattr(symbol_obj, "getName"):
                            symbol_oid = symbol_obj.getName()
                            if symbol_oid == oid_tuple:
                                metadata["name"] = symbol_name
                                metadata["mib"] = mod_name

                                # Extract access and type info
                                if hasattr(symbol_obj, "getMaxAccess"):
                                    metadata["access"] = str(symbol_obj.getMaxAccess())
                                if hasattr(symbol_obj, "getSyntax"):
                                    metadata["type"] = type(symbol_obj.getSyntax()).__name__
                                if hasattr(symbol_obj, "getDescription"):
                                    metadata["description"] = str(symbol_obj.getDescription())

                                return metadata
                except Exception:
                    continue
        except Exception as e:
            self.logger.log(f"Error extracting metadata for {oid_str}: {e}", "DEBUG")

        return metadata

    def _get_icon_for_oid(self, oid_str: str) -> Optional[Any]:
        """Get appropriate icon for an OID based on its metadata.

        Args:
            oid_str: OID in dotted notation

        Returns:
            PhotoImage icon or None
        """
        metadata = self._get_oid_metadata_from_mib(oid_str)
        access = metadata.get("access", "").lower()

        if "write" in access:
            return self.icons.get("edit")
        elif "read" in access:
            return self.icons.get("lock")
        elif metadata.get("name", "").endswith("Table"):
            return self.icons.get("table")
        else:
            return self.icons.get("doc")

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
        parts = [p for p in oid.split(".") if p]

        # If only one component, append .0
        if len(parts) == 1:
            # Return as "X.0" format
            return f"{oid.rstrip('.')}.0"

        return oid

    def _resolve_oid_name_to_tuple(self, oid_input: str) -> tuple[int, ...] | None:
        """Resolve an OID name to a tuple using pysnmp's MIB system.

        This method works like command-line SNMP tools: it requires MIBs to be
        loaded for name resolution. If MIBs aren't loaded, only numerical OIDs work.

        Supports:
        - Numerical OIDs: "1.3.6.1.2.1.1.1.0"
        - MIB names with module: "SNMPv2-MIB::sysDescr"
        - Short names (if MIB loaded): "sysDescr"

        Args:
            oid_input: OID in any supported format

        Returns:
            Tuple of OID components or None if name cannot be resolved
        """
        oid_input = oid_input.strip()

        # Check if it's already a numerical OID
        if oid_input and oid_input[0].isdigit():
            try:
                parts = oid_input.split(".")
                return tuple(int(p) for p in parts if p)
            except (ValueError, AttributeError):
                return None

        # Try to resolve name using pysnmp's MIB system
        # This requires MIBs to be loaded, just like snmpget/snmpwalk
        try:
            # Create ObjectIdentity with the name
            # pysnmp will use loaded MIBs to resolve it
            if "::" in oid_input:
                # Format: "MIB::name"
                _mib_name, _obj_name = oid_input.split("::", 1)
                # We can't pre-resolve here - return None and let ObjectIdentity handle it
                # This signals caller to use ObjectIdentity(mib_name, obj_name) directly
                return None
            else:
                # Try resolving as short name from loaded MIBs
                for mod_name in self.loaded_mibs:
                    try:
                        mib_symbols = self.mib_builder.mibSymbols.get(mod_name, {})
                        if oid_input in mib_symbols:
                            symbol_obj = mib_symbols[oid_input]
                            if hasattr(symbol_obj, "getName"):
                                oid_tuple = symbol_obj.getName()
                                return tuple(oid_tuple)  # Ensure it's a tuple of ints
                    except Exception:
                        continue
        except Exception as e:
            self.logger.log(f"Failed to resolve {oid_input}: {e}", "DEBUG")

        return None

    def _get_connection_params(self) -> tuple[str, int, str]:
        """Get connection parameters from UI."""
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            port = self.default_port
        community = self.community_var.get().strip()
        return host, port, community

    def _format_mib_error(self, error: Exception) -> str:
        """Format MIB-related errors with helpful suggestions."""
        error_str = str(error)

        # Check for common MIB resolution errors
        if "MibNotFoundError" in error_str or "compilation error" in error_str:
            # Extract the object name if possible
            match = re.search(r"'(\w+)'|\"(\w+)\"", error_str)
            obj_name = match.group(1) or match.group(2) if match else "object"

            return (
                f"Cannot resolve '{obj_name}' - MIB not loaded.\n\n"
                f"Currently loaded MIBs: "
                f"{', '.join(self.loaded_mibs) if self.loaded_mibs else 'None'}\n\n"
                f"To fix:\n"
                f"  1. Load the MIB containing '{obj_name}' (e.g., SNMPv2-MIB)\n"
                f"  2. Use numerical OID instead (e.g., 1.3.6.1.2.1.1.1.0)\n"
                f"  3. Use full format: MIB::objectName"
            )

        return error_str

    def _create_object_identity(self, oid_input: str) -> tuple[ObjectIdentity, str]:
        """Create ObjectIdentity for an OID input and return display OID.

        Args:
            oid_input: OID as string (numerical or name)

        Returns:
            Tuple of (ObjectIdentity instance, display OID string)

        Raises:
            ValueError: If OID cannot be parsed or resolved
        """
        oid_input = oid_input.strip()

        # Check if it's already numerical
        if oid_input and oid_input[0].isdigit():
            normalized = self._normalize_oid(oid_input)
            try:
                oid_tuple = tuple(int(p) for p in normalized.split(".") if p)
                return ObjectIdentity(oid_tuple), normalized
            except (ValueError, AttributeError) as e:
                raise ValueError(f"Invalid numerical OID: {oid_input}") from e

        # Handle MIB::name format
        if "::" in oid_input:
            mib_name, obj_name = oid_input.split("::", 1)
            # Let pysnmp resolve it (requires MIB to be loaded)
            return ObjectIdentity(mib_name, obj_name), oid_input

        # Try as short name - resolve from loaded MIBs
        resolved = self._resolve_oid_name_to_tuple(oid_input)
        if resolved:
            # Successfully resolved - use numerical form
            display_oid = ".".join(str(x) for x in resolved)
            return ObjectIdentity(resolved), display_oid

        # Last attempt: let pysnmp try to resolve it using loaded MIBs
        # This will fail at runtime if MIB isn't loaded (as it should)
        # Provide helpful error message
        if not self.loaded_mibs:
            raise ValueError(
                f"Cannot resolve '{oid_input}' - no MIBs loaded.\n\n"
                f"Load a MIB first (e.g., SNMPv2-MIB) or use numerical OID."
            )

        raise ValueError(
            f"Cannot resolve '{oid_input}' in loaded MIBs: {', '.join(self.loaded_mibs)}\n\n"
            f"Try:\n"
            f"  • Load the MIB containing this object\n"
            f"  • Use full format: MIB::objectName\n"
            f"  • Use numerical OID instead"
        )

    def _clear_results(self) -> None:
        """Clear the results tree."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.agent_results.clear()
        self.agent_tree_items.clear()
        self.status_var.set("Results cleared")
        self.logger.log("MIB Browser: Results cleared")

    def _show_loaded_mibs(self) -> None:
        """Show list of loaded MIBs."""
        if not self.loaded_mibs:
            messagebox.showinfo("Loaded MIBs", "No MIBs currently loaded", parent=self.window)
        else:
            mib_list = "\n".join(f"• {mib}" for mib in sorted(self.loaded_mibs))
            messagebox.showinfo(
                "Loaded MIBs",
                f"Currently loaded MIBs:\n\n{mib_list}",
                parent=self.window,
            )

    def _browse_mib_files(self) -> None:
        """Browse for MIB files and copy them to cache directory."""
        filetypes = [
            ("MIB Files", "*.mib *.txt *.my *.asn *.asn1"),
            ("MIB Text Files", "*.mib"),
            ("Text Files", "*.txt"),
            ("MY Files", "*.my"),
            ("ASN.1 Files", "*.asn *.asn1"),
            ("All Files", "*.*"),
        ]

        files = filedialog.askopenfilenames(
            parent=self.window, title="Select MIB Files to Cache", filetypes=filetypes
        )

        if not files:
            return

        copied_count = 0
        for file_path in files:
            source = None
            try:
                source = Path(file_path)
                dest = self.mib_cache_dir / source.name
                shutil.copy2(source, dest)
                copied_count += 1
                self.logger.log(f"Copied MIB file to cache: {source.name}", "INFO")
            except Exception as e:
                source_name = source.name if source else file_path
                self.logger.log(f"Failed to copy {source_name}: {e}", "ERROR")
                messagebox.showerror(
                    "Copy Error",
                    f"Failed to copy {source_name}:\n{e}",
                    parent=self.window,
                )

        if copied_count > 0:
            messagebox.showinfo(
                "Success",
                f"Copied {copied_count} file(s) to MIB cache",
                parent=self.window,
            )
            self._refresh_cached_mibs()

    def _refresh_cached_mibs(self) -> None:
        """Refresh the list of cached MIBs with dependency status."""
        # Clear existing listbox items
        for widget in self.mib_listbox_frame.winfo_children():
            widget.destroy()

        # Clear stored references to checkbuttons
        self.cached_mib_checkbuttons = {}

        # Scan cache directory
        if not self.mib_cache_dir.exists():
            self.mib_cache_dir.mkdir(parents=True, exist_ok=True)

        mib_files = (
            sorted(self.mib_cache_dir.glob("*.mib"))
            + sorted(self.mib_cache_dir.glob("*.txt"))
            + sorted(self.mib_cache_dir.glob("*.my"))
            + sorted(self.mib_cache_dir.glob("*.asn"))
            + sorted(self.mib_cache_dir.glob("*.asn1"))
        )

        if not mib_files:
            label = ctk.CTkLabel(
                self.mib_listbox_frame,
                text="No cached MIBs found. Use 'Browse MIB Files' to add some.",
                text_color="gray",
            )
            label.pack(pady=20)
            return

        # Create detailed view for each MIB with dependencies
        for mib_file in mib_files:
            # Extract MIB name (without extension)
            mib_name = mib_file.stem

            # Get dependency info
            resolved_deps, missing_deps = self._resolve_mib_dependencies(mib_name)
            is_loaded = mib_name in self.loaded_mibs

            # Build status indicator
            if is_loaded:
                status = " ✓ (loaded)"
                status_color = "#00ff00"
            elif missing_deps:
                status = " ✗ (unsatisfied)"
                status_color = "#ff6b6b"
            else:
                status = " ◦ (ready)"
                status_color = "#cccccc"

            # MIB header with checkbox
            header_frame = ctk.CTkFrame(self.mib_listbox_frame, fg_color="transparent")
            header_frame.pack(anchor="w", fill="x", padx=5, pady=(8, 2))

            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                header_frame,
                text=f"{mib_name}{status}",
                variable=var,
                text_color=status_color,
            )
            cb.pack(side="left")

            # Store reference with filename
            self.cached_mib_checkbuttons[str(mib_file)] = var

            # Dependency details frame
            if resolved_deps or missing_deps:
                deps_frame = ctk.CTkFrame(self.mib_listbox_frame, fg_color="transparent")
                deps_frame.pack(anchor="w", fill="x", padx=20, pady=(0, 6))

                # Status line
                if is_loaded:
                    status_text = "Status: LOADED"
                    status_text_color = "#00ff00"
                elif missing_deps:
                    status_text = f"Status: UNSATISFIED DEPENDENCIES ({len(missing_deps)} missing)"
                    status_text_color = "#ff6b6b"
                else:
                    status_text = "Status: READY TO LOAD"
                    status_text_color = "#cccccc"

                status_label = ctk.CTkLabel(
                    deps_frame,
                    text=status_text,
                    text_color=status_text_color,
                    font=("", 10),
                )
                status_label.pack(anchor="w")

                # Show resolved dependencies
                if resolved_deps:
                    if missing_deps:
                        dep_label = ctk.CTkLabel(
                            deps_frame,
                            text=f"Resolved ({len(resolved_deps)}):",
                            text_color="#0088ff",
                            font=("", 9),
                        )
                        dep_label.pack(anchor="w", padx=(10, 0), pady=(2, 0))
                        for dep in sorted(resolved_deps):
                            # Check if actually loaded in pysnmp (verifies file exists)
                            is_dep_loaded = self._is_mib_loaded_in_pysnmp(dep)
                            dep_status = "✓" if is_dep_loaded else "?"
                            dep_color = "#00ff00" if is_dep_loaded else "#ffaa00"
                            dep_text = ctk.CTkLabel(
                                deps_frame,
                                text=f"  {dep_status} {dep}",
                                text_color=dep_color,
                                font=("", 9),
                            )
                            dep_text.pack(anchor="w", padx=(20, 0))
                    else:
                        dep_label = ctk.CTkLabel(
                            deps_frame,
                            text=f"Dependencies ({len(resolved_deps)}):",
                            text_color="#0088ff",
                            font=("", 9),
                        )
                        dep_label.pack(anchor="w", padx=(10, 0), pady=(2, 0))
                        for dep in sorted(resolved_deps):
                            # Check if actually loaded in pysnmp (verifies file exists)
                            is_dep_loaded = self._is_mib_loaded_in_pysnmp(dep)
                            dep_status = "✓" if is_dep_loaded else "?"
                            dep_color = "#00ff00" if is_dep_loaded else "#ffaa00"
                            dep_text = ctk.CTkLabel(
                                deps_frame,
                                text=f"  {dep_status} {dep}",
                                text_color=dep_color,
                                font=("", 9),
                            )
                            dep_text.pack(anchor="w", padx=(20, 0))

                # Show missing dependencies
                if missing_deps:
                    missing_label = ctk.CTkLabel(
                        deps_frame,
                        text=f"Missing ({len(missing_deps)}):",
                        text_color="#ff6b6b",
                        font=("", 9),
                    )
                    missing_label.pack(anchor="w", padx=(10, 0), pady=(2, 0))
                    for missing in sorted(missing_deps):
                        missing_text = ctk.CTkLabel(
                            deps_frame,
                            text=f"  ✗ {missing}",
                            text_color="#ff6b6b",
                            font=("", 9),
                        )
                        missing_text.pack(anchor="w", padx=(20, 0))

        self.logger.log(f"Refreshed cached MIBs: {len(mib_files)} files found", "INFO")

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
            except Exception as e:
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

    def _on_node_open(self, event: Any) -> None:
        """Handle node open events (for future lazy loading if needed)."""
        _ = event

    def _expand_all(self) -> None:
        """Expand all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.results_tree.item(item, open=True)
            for c in self.results_tree.get_children(item):
                _recurse(c)

        for root in self.results_tree.get_children(""):
            _recurse(root)

    def _collapse_all(self) -> None:
        """Collapse all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.results_tree.item(item, open=False)
            for c in self.results_tree.get_children(item):
                _recurse(c)

        for root in self.results_tree.get_children(""):
            _recurse(root)

    def _get_or_create_agent_node(self, host: str, port: int) -> str:
        """Get or create the tree node for an agent."""
        agent_key = f"{host}:{port}"

        if agent_key not in self.agent_tree_items:
            # Create new agent node
            agent_label = f"🖥️ {agent_key}"
            item = self.results_tree.insert("", "end", text=agent_label, values=("", "", ""))
            self.results_tree.item(item, open=True)
            self.agent_tree_items[agent_key] = item
            self.agent_results[agent_key] = {"operations": {}, "last_updated": ""}

        return self.agent_tree_items[agent_key]

    def _get_or_create_operation_node(self, agent_item: str, operation: str, oid: str) -> str:
        """Get or create the tree node for an operation under an agent."""
        agent_key = None
        for key, item in self.agent_tree_items.items():
            if item == agent_item:
                agent_key = key
                break

        if not agent_key:
            return ""

        op_key = f"{operation}:{oid}"
        op_children = self.results_tree.get_children(agent_item)

        for child in op_children:
            if self.results_tree.item(child, "text").startswith(f"→ {operation}"):
                if op_key not in self.agent_results[agent_key]["operations"]:
                    self.agent_results[agent_key]["operations"][op_key] = {"results": []}
                return child

        # Create new operation node
        timestamp = datetime.now().strftime("%H:%M:%S")
        op_label = f"→ {operation} {oid} [{timestamp}]"
        op_item = self.results_tree.insert(agent_item, "end", text=op_label, values=("", "", ""))
        self.results_tree.item(op_item, open=True)
        self.agent_results[agent_key]["operations"][op_key] = {"results": []}
        self.agent_results[agent_key]["last_updated"] = timestamp

        return op_item

    def _snmp_get(self) -> None:
        """Execute SNMP GET command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        # Create ObjectIdentity from OID input
        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GET on {display_oid}...")
        self.logger.log(f"MIB Browser: GET {display_oid} from {host}:{port}")

        try:

            async def async_get() -> tuple[Any, ...]:
                try:
                    return await get_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, var_binds = asyncio.run(async_get())
            _ = error_index  # Unused but part of SNMP response tuple

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser GET error: {error_indication}", "ERROR")
                messagebox.showerror("SNMP GET Error", str(error_indication), parent=self.window)
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser GET error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP GET Error", error_status.prettyPrint(), parent=self.window
                )
                return

            # Get or create agent node
            agent_item = self._get_or_create_agent_node(host, port)

            # Get or create operation node
            op_item = self._get_or_create_operation_node(agent_item, "GET", display_oid)

            # Add results
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = format_snmp_value(var_bind[1])
                type_str = type(var_bind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                icon = self._get_icon_for_oid(oid_str)

                self.results_tree.insert(
                    op_item,
                    "end",
                    text=name,
                    image=icon if icon else "",
                    values=(oid_str, type_str, value),
                )

            self.status_var.set(f"GET completed: {len(var_binds)} result(s)")
            self.logger.log(f"MIB Browser: GET {display_oid} returned {len(var_binds)} result(s)")

        except Exception as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser GET error: {e}", "ERROR")
            messagebox.showerror("SNMP GET Error", error_msg, parent=self.window)

    def _snmp_getnext(self) -> None:
        """Execute SNMP GETNEXT command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        # Create ObjectIdentity from OID input
        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GETNEXT on {display_oid}...")
        self.logger.log(f"MIB Browser: GETNEXT {display_oid} from {host}:{port}")

        try:

            async def async_next() -> tuple[Any, ...]:
                # next_cmd returns a coroutine that yields ONE result
                target = await UdpTransportTarget.create((host, port))

                try:
                    return await next_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, var_binds = asyncio.run(async_next())
            _ = error_index  # Unused but part of SNMP response tuple

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser GETNEXT error: {error_indication}", "ERROR")
                messagebox.showerror(
                    "SNMP GETNEXT Error", str(error_indication), parent=self.window
                )
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser GETNEXT error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP GETNEXT Error", error_status.prettyPrint(), parent=self.window
                )
                return

            # Get or create agent node
            agent_item = self._get_or_create_agent_node(host, port)

            # Get or create operation node
            op_item = self._get_or_create_operation_node(agent_item, "GETNEXT", display_oid)

            # Add results
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = format_snmp_value(var_bind[1])
                type_str = type(var_bind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                icon = self._get_icon_for_oid(oid_str)

                self.results_tree.insert(
                    op_item,
                    "end",
                    text=name,
                    image=icon if icon else "",
                    values=(oid_str, type_str, value),
                )

            # Update OID field with returned OID for easy iteration
            if var_binds:
                next_oid = str(var_binds[0][0])
                self.oid_var.set(next_oid)
                self.logger.log(f"Updated OID field to {next_oid} for next iteration", "DEBUG")

            self.status_var.set(f"GETNEXT completed: {len(var_binds)} result(s)")
            self.logger.log(
                f"MIB Browser: GETNEXT {display_oid} returned {len(var_binds)} result(s)"
            )

        except Exception as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser GETNEXT error: {e}", "ERROR")
            messagebox.showerror("SNMP GETNEXT Error", error_msg, parent=self.window)

    def _snmp_walk(self) -> None:
        """Execute SNMP WALK command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        # Create ObjectIdentity from OID input
        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing WALK on {display_oid}...")
        self.logger.log(f"MIB Browser: WALK {display_oid} from {host}:{port}")

        try:

            async def async_walk() -> list[tuple[Any, ...]]:
                walk_results = []
                target = await UdpTransportTarget.create((host, port))

                try:
                    # walk_cmd returns async generator directly
                    iterator = walk_cmd(
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                    async for (
                        error_indication,
                        error_status,
                        error_index,
                        var_binds,
                    ) in iterator:
                        walk_results.append(
                            (error_indication, error_status, error_index, var_binds)
                        )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get("errorIndication", str(e))
                    walk_results.append((error_indication, None, None, []))

                return walk_results

            walk_results = asyncio.run(async_walk())

            # Get or create agent node
            agent_item = self._get_or_create_agent_node(host, port)

            # Get or create operation node
            op_item = self._get_or_create_operation_node(agent_item, "WALK", display_oid)

            result_count = 0
            for error_indication, error_status, error_index, var_binds in walk_results:
                _ = error_index  # Unused but part of SNMP response tuple
                if error_indication:
                    self.status_var.set(f"Error: {error_indication}")
                    self.logger.log(f"MIB Browser WALK error: {error_indication}", "ERROR")
                    messagebox.showerror(
                        "SNMP WALK Error", str(error_indication), parent=self.window
                    )
                    return
                if error_status:
                    self.status_var.set(f"Error: {error_status}")
                    self.logger.log(f"MIB Browser WALK error: {error_status}", "ERROR")
                    messagebox.showerror("SNMP WALK Error", str(error_status), parent=self.window)
                    return

                # Process results
                for var_bind in var_binds:
                    oid_str = str(var_bind[0])
                    value = format_snmp_value(var_bind[1])
                    type_str = type(var_bind[1]).__name__
                    name = self._get_name_from_oid(oid_str)
                    icon = self._get_icon_for_oid(oid_str)

                    self.results_tree.insert(
                        op_item,
                        "end",
                        text=name,
                        image=icon if icon else "",
                        values=(oid_str, type_str, value),
                    )
                    result_count += 1

            self.status_var.set(f"WALK completed: {result_count} result(s)")
            self.logger.log(f"MIB Browser: WALK {display_oid} returned {result_count} result(s)")

        except Exception as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser WALK error: {e}", "ERROR")
            messagebox.showerror("SNMP WALK Error", error_msg, parent=self.window)

    def _snmp_set(self) -> None:
        """Execute SNMP SET command."""
        oid = self.oid_var.get().strip()
        value = self.value_var.get().strip()

        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return
        if not value:
            messagebox.showwarning("No Value", "Please enter a value to set", parent=self.window)
            return

        # Create ObjectIdentity from OID input
        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing SET on {display_oid}...")
        self.logger.log(f"MIB Browser: SET {display_oid} = {value} on {host}:{port}")

        try:
            # SNMP SET - using OctetString by default
            # In a production tool, you'd want type selection UI
            async def async_set() -> tuple[Any, ...]:
                try:
                    return await set_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(obj_identity, OctetString(value)),
                    )
                except StatusInformation as e:
                    # Handle any serialization errors
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, _var_binds = asyncio.run(async_set())
            _ = error_index  # Unused but part of SNMP response tuple

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser SET error: {error_indication}", "ERROR")
                messagebox.showerror("SNMP SET Error", str(error_indication), parent=self.window)
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser SET error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP SET Error", error_status.prettyPrint(), parent=self.window
                )
                return

            # Get or create agent node
            agent_item = self._get_or_create_agent_node(host, port)

            # Get or create operation node
            op_item = self._get_or_create_operation_node(agent_item, "SET", display_oid)

            # Add result showing the set operation
            result_text = f"SET {display_oid} = {value}"
            icon = self._get_icon_for_oid(display_oid)
            self.results_tree.insert(
                op_item,
                "end",
                text=result_text,
                image=icon if icon else "",
                values=(display_oid, "OctetString", value),
            )

            self.status_var.set("SET completed successfully")
            self.logger.log(f"MIB Browser: SET {display_oid} = {value} successful")

        except Exception as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser SET error: {e}", "ERROR")
            messagebox.showerror("SNMP SET Error", error_msg, parent=self.window)

    def _get_name_from_oid(self, oid_str: str) -> str:
        """Get human-readable name from OID using loaded MIBs."""
        # Try to resolve from loaded MIBs
        metadata = self._get_oid_metadata_from_mib(oid_str)
        if metadata.get("name"):
            return str(metadata["name"])

        # Try to find base OID (without instance) for table entries
        parts = oid_str.split(".")
        for i in range(len(parts), 0, -1):
            base_oid = ".".join(parts[:i])
            base_metadata = self._get_oid_metadata_from_mib(base_oid)
            if base_metadata.get("name"):
                instance = ".".join(parts[i:])
                return f"{base_metadata['name']}.{instance}" if instance else base_metadata["name"]

        # Fallback to OID string if no MIB info
        return oid_str

    def _build_hierarchical_tree(self, results: list[tuple[str, str, str]]) -> None:
        """Build a hierarchical tree from WALK results."""
        # Create a mapping of OID -> item
        oid_to_item: Dict[str, str] = {}

        for oid_str, type_str, value in results:
            parts = oid_str.split(".")
            parent_oid = ".".join(parts[:-1]) if len(parts) > 1 else ""

            # Find parent item
            parent_item = ""
            if parent_oid and parent_oid in oid_to_item:
                parent_item = oid_to_item[parent_oid]

            # Get name for this OID
            name = self._get_name_from_oid(oid_str)

            # Insert into tree
            item = self.results_tree.insert(
                parent_item, "end", text=name, values=(oid_str, type_str, value)
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
    parser = argparse.ArgumentParser(description="SNMP MIB Browser")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=161, help="SNMP port")
    parser.add_argument("--community", default="public", help="SNMP community string")

    args = parser.parse_args()

    browser = MIBBrowserWindow(
        default_host=args.host, default_port=args.port, default_community=args.community
    )
    browser.run()


if __name__ == "__main__":
    main()
