"""Standalone MIB Browser for SNMP testing.

This module can be run independently or embedded in other applications.
"""

# pylint: disable=broad-exception-caught,attribute-defined-outside-init,no-else-return
# pylint: disable=too-many-lines,too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-locals,too-many-statements
# pylint: disable=too-many-nested-blocks,too-many-branches

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from pysnmp.hlapi.v3arch.asyncio import (
    ObjectIdentity,
)
from pysnmp.smi import builder, view

from app.mib_builder_adapters import extract_optional_metadata, extract_symbol_oid
from ui.common import Logger
from ui.icon_utils import load_icons_with_fallback
from ui.mib_browser_snmp_ops_mixin import MIBBrowserSnmpOpsMixin
from ui.mib_browser_ui_mixin import MIBBrowserUIMixin


def _ensure_default_tk_root() -> None:
    """Ensure tkinter has a default root for variable creation in headless contexts."""
    if getattr(tk, "_default_root", None) is not None:
        return
    is_test_context = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not is_test_context:
        return
    try:
        tk._default_root = tk.Tcl()  # type: ignore[attr-defined]  # noqa: SLF001
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        return


_ensure_default_tk_root()


class MIBBrowserWindow(MIBBrowserUIMixin, MIBBrowserSnmpOpsMixin):
    """Standalone MIB Browser window for SNMP operations."""

    def __init__(
        self,
        parent: tk.Widget | None = None,
        logger: Logger | None = None,
        default_host: str = "127.0.0.1",
        default_port: int = 161,
        default_community: str = "public",
        oid_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
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
        self.logger = logger or Logger()
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
        self.icons: dict[str, tk.PhotoImage] = {}
        self._load_icons()

        # Track agent results separately
        self.agent_results: dict[str, dict[str, Any]] = {}  # host:port -> {operations, etc.}
        self.agent_tree_items: dict[str, str] = {}  # host:port -> tree_item_id

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
        """Set up MIB search paths for pysnmp."""
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

        icon_specs = {
            "folder": ("#fbbf24", None),
            "table": ("#3b82f6", None),
            "lock": ("#9ca3af", None),
            "edit": ("#10b981", None),
            "doc": ("#ffffff", "#e5e7eb"),
            "chart": ("#a78bfa", None),
            "key": ("#f97316", None),
        }
        self.icons.update(
            load_icons_with_fallback(
                icons_dir=icons_dir,
                icon_specs=icon_specs,
                size=16,
                inner_padding=4,
            )
        )


    def _extract_mib_imports(self, mib_file_path: Path) -> list[str]:
        """Extract IMPORTS from a MIB file.

        Args:
            mib_file_path: Path to .mib or .py MIB file

        Returns:
            List of imported MIB names

        """
        imports: list[str] = []
        try:
            content = mib_file_path.read_text(encoding="utf-8", errors="ignore")
            if mib_file_path.suffix == ".py":
                self._collect_imports_from_compiled_mib(content, imports)
            else:
                import_block = self._extract_text_mib_import_block(content)
                self._collect_imports_from_text_mib_block(import_block, imports)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.log(f"Error extracting imports from {mib_file_path.name}: {e}", "WARNING")

        return imports

    @staticmethod
    def _is_valid_mib_import_name(mib_name: str) -> bool:
        return bool(mib_name and mib_name.replace("-", "").replace("_", "").isalnum())

    def _collect_imports_from_compiled_mib(self, content: str, imports: list[str]) -> None:
        for line in content.split("\n"):
            if " FROM " not in line or "import" not in line:
                continue
            parts = line.split()
            idx = parts.index("FROM") if "FROM" in parts else -1
            if idx < 0 or idx + 1 >= len(parts):
                continue
            mib_name = parts[idx + 1]
            if mib_name and mib_name not in imports:
                imports.append(mib_name)

    def _extract_text_mib_import_block(self, content: str) -> str:
        in_imports = False
        import_block = ""
        for line in content.split("\n"):
            if "IMPORTS" in line:
                in_imports = True
                continue
            if not in_imports:
                continue
            if ";" in line:
                import_block += line.split(";")[0]
                break
            import_block += line
        return import_block

    def _collect_imports_from_text_mib_block(self, import_block: str, imports: list[str]) -> None:
        if not import_block:
            return
        for part in import_block.split("FROM"):
            if not part.strip():
                continue
            mib_name = part.strip().split()[0]
            if self._is_valid_mib_import_name(mib_name) and mib_name not in imports:
                imports.append(mib_name)

    def _find_mib_file_in_cache(self, mib_name: str) -> Path | None:
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

    def _find_mib_file(self, mib_name: str) -> Path | None:
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
                        except (
                            AttributeError,
                            LookupError,
                            OSError,
                            TypeError,
                            ValueError,
                        ) as e:
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
                        except (
                            AttributeError,
                            LookupError,
                            OSError,
                            TypeError,
                            ValueError,
                        ) as e:
                            # Main MIB failed to load
                            self.unsatisfied_mibs[mib_name] = [f"Failed to load: {e}"]
                            failed.append(mib_name)
                            self.logger.log(
                                f"Failed to load main MIB {mib_name}: {e}",
                                "ERROR",
                            )
            except (
                AttributeError,
                LookupError,
                OSError,
                TypeError,
                ValueError,
            ) as e:
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

    def _get_oid_metadata_from_mib(self, oid_str: str) -> dict[str, Any]:
        """Extract metadata for an OID from loaded MIBs.

        Args:
            oid_str: OID in dotted notation (e.g., "1.3.6.1.2.1.1.1")

        Returns:
            Dictionary with keys: name, mib, type, access, description

        """
        metadata: dict[str, Any] = {}

        try:
            # Try to resolve OID to MIB symbol
            oid_tuple = tuple(int(x) for x in oid_str.split(".") if x)

            # Search through loaded MIBs for this OID
            for mod_name in self.loaded_mibs:
                try:
                    mib_symbols = self.mib_builder.mibSymbols.get(mod_name, {})
                    for symbol_name, symbol_obj in mib_symbols.items():
                        symbol_meta = extract_optional_metadata(symbol_obj)
                        if symbol_meta and symbol_meta.oid == oid_tuple:
                            metadata["name"] = symbol_name
                            metadata["mib"] = mod_name
                            if symbol_meta.access is not None:
                                metadata["access"] = symbol_meta.access
                            if symbol_meta.type_name is not None:
                                metadata["type"] = symbol_meta.type_name
                            if symbol_meta.description is not None:
                                metadata["description"] = symbol_meta.description
                            return metadata
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                ):
                    continue
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.log(
                f"Error extracting metadata for {oid_str}: {e}",
                "DEBUG",
            )

        return metadata

    def _get_icon_for_oid(self, oid_str: str) -> tk.PhotoImage | None:
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
        if "read" in access:
            return self.icons.get("lock")
        if metadata.get("name", "").endswith("Table"):
            return self.icons.get("table")
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
            if "::" in oid_input:
                _mib_name, _obj_name = oid_input.split("::", 1)
                return None
            # Try resolving as short name from loaded MIBs
            for mod_name in self.loaded_mibs:
                try:
                    mib_symbols = self.mib_builder.mibSymbols.get(mod_name, {})
                    if oid_input in mib_symbols:
                        symbol_obj = mib_symbols[oid_input]
                        symbol_oid = extract_symbol_oid(symbol_obj)
                        if symbol_oid is not None:
                            return symbol_oid
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                ):
                    continue
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.log(
                f"Failed to resolve {oid_input}: {e}",
                "DEBUG",
            )

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
                msg = f"Invalid numerical OID: {oid_input}"
                raise ValueError(msg) from e

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
            msg = (
                f"Cannot resolve '{oid_input}' - no MIBs loaded.\n\n"
                f"Load a MIB first (e.g., SNMPv2-MIB) or use numerical OID."
            )
            raise ValueError(
                msg,
            )

        msg = (
            f"Cannot resolve '{oid_input}' in loaded MIBs: {', '.join(self.loaded_mibs)}\n\n"
            f"Try:\n"
            f"  • Load the MIB containing this object\n"
            f"  • Use full format: MIB::objectName\n"
            f"  • Use numerical OID instead"
        )
        raise ValueError(
            msg,
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
            parent=self.window,
            title="Select MIB Files to Cache",
            filetypes=filetypes,
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
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
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
        self._clear_cached_mib_list_ui()
        mib_files = self._list_cached_mib_files()

        if not mib_files:
            self._render_no_cached_mibs_message()
            return

        for mib_file in mib_files:
            self._render_cached_mib_entry(mib_file)

        self.logger.log(f"Refreshed cached MIBs: {len(mib_files)} files found", "INFO")

    def _clear_cached_mib_list_ui(self) -> None:
        for widget in self.mib_listbox_frame.winfo_children():
            widget.destroy()
        self.cached_mib_checkbuttons = {}

    def _list_cached_mib_files(self) -> list[Path]:
        if not self.mib_cache_dir.exists():
            self.mib_cache_dir.mkdir(parents=True, exist_ok=True)
        return (
            sorted(self.mib_cache_dir.glob("*.mib"))
            + sorted(self.mib_cache_dir.glob("*.txt"))
            + sorted(self.mib_cache_dir.glob("*.my"))
            + sorted(self.mib_cache_dir.glob("*.asn"))
            + sorted(self.mib_cache_dir.glob("*.asn1"))
        )

    def _render_no_cached_mibs_message(self) -> None:
        label = ctk.CTkLabel(
            self.mib_listbox_frame,
            text="No cached MIBs found. Use 'Browse MIB Files' to add some.",
            text_color="gray",
        )
        label.pack(pady=20)

    def _cached_mib_status(
        self,
        mib_name: str,
        missing_deps: list[str],
    ) -> tuple[str, str]:
        if mib_name in self.loaded_mibs:
            return " ✓ (loaded)", "#00ff00"
        if missing_deps:
            return " ✗ (unsatisfied)", "#ff6b6b"
        return " ◦ (ready)", "#cccccc"

    def _render_dependency_lines(
        self,
        deps_frame: ctk.CTkFrame,
        resolved_deps: list[str],
        missing_deps: list[str],
    ) -> None:
        if resolved_deps:
            label_prefix = "Resolved" if missing_deps else "Dependencies"
            dep_label = ctk.CTkLabel(
                deps_frame,
                text=f"{label_prefix} ({len(resolved_deps)}):",
                text_color="#0088ff",
                font=("", 9),
            )
            dep_label.pack(anchor="w", padx=(10, 0), pady=(2, 0))
            for dep in sorted(resolved_deps):
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

    def _render_cached_mib_entry(self, mib_file: Path) -> None:
        mib_name = mib_file.stem
        resolved_deps, missing_deps = self._resolve_mib_dependencies(mib_name)
        is_loaded = mib_name in self.loaded_mibs
        status, status_color = self._cached_mib_status(mib_name, missing_deps)

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
        self.cached_mib_checkbuttons[str(mib_file)] = var

        if not (resolved_deps or missing_deps):
            return

        deps_frame = ctk.CTkFrame(self.mib_listbox_frame, fg_color="transparent")
        deps_frame.pack(anchor="w", fill="x", padx=20, pady=(0, 6))

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
        self._render_dependency_lines(deps_frame, resolved_deps, missing_deps)

    def run(self) -> None:
        """Run the standalone browser window."""
        if isinstance(self.window, ctk.CTk):
            self.window.mainloop()

    def set_oid_metadata(self, metadata: dict[str, dict[str, Any]]) -> None:
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
        default_host=args.host,
        default_port=args.port,
        default_community=args.community,
    )
    browser.run()


if __name__ == "__main__":
    main()
