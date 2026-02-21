"""MIB dependency resolver for extracting and analyzing MIB imports."""

from __future__ import annotations

import os
import re
from typing import Dict, Set, List, Optional, Any, cast


class MibDependencyResolver:
    """Resolves MIB dependencies by parsing IMPORTS sections."""

    def __init__(self, mib_source_dirs: Optional[List[str]] = None):
        """Initialize the resolver with optional custom MIB directories.

        Args:
            mib_source_dirs: List of directories to search for MIB source files.
                            Defaults to common locations.
        """
        self.mib_source_dirs = mib_source_dirs or [
            "data/mibs_reference",
            "data/mibs",
            "compiled-mibs",  # Fallback to compiled MIBs if source not found
        ]
        self._dependency_cache: Dict[str, Set[str]] = {}
        self._mib_file_cache: Dict[str, Optional[str]] = {}

    def _find_mib_source(self, mib_name: str) -> Optional[str]:
        """Find a MIB source file by name.

        Args:
            mib_name: Name of the MIB (e.g., "IF-MIB")

        Returns:
            Path to the MIB source file, or None if not found.
        """
        if mib_name in self._mib_file_cache:
            return self._mib_file_cache[mib_name]

        # Try to find source file with common extensions
        for search_dir in self.mib_source_dirs:
            if not os.path.exists(search_dir):
                continue

            # Try direct match first
            for ext in [".txt", ".mib", ".my"]:
                mib_path = os.path.join(search_dir, f"{mib_name}{ext}")
                if os.path.exists(mib_path):
                    self._mib_file_cache[mib_name] = mib_path
                    return mib_path

            # Search subdirectories recursively with depth limit
            for root, dirs, files in os.walk(search_dir):
                # Calculate depth and limit recursion to avoid infinite traversal
                depth = root[len(search_dir) :].count(os.sep)
                if depth > 5:  # Limit depth to 5 levels
                    dirs[:] = []  # Don't descend further
                    continue

                for ext in [".txt", ".mib", ".my"]:
                    mib_filename = f"{mib_name}{ext}"
                    if mib_filename in files:
                        mib_path = os.path.join(root, mib_filename)
                        self._mib_file_cache[mib_name] = mib_path
                        return mib_path

        self._mib_file_cache[mib_name] = None
        return None

    def _parse_imports(self, mib_path: str) -> Set[str]:
        """Parse the IMPORTS section of a MIB file.

        Args:
            mib_path: Path to the MIB source file.

        Returns:
            Set of MIB names imported by this MIB.
        """
        if not os.path.exists(mib_path):
            return set()

        try:
            with open(mib_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return set()

        # Extract IMPORTS section using regex
        imports_match = re.search(r"IMPORTS\s+(.*?);\s*(?=\w+|$)", content, re.DOTALL)
        if not imports_match:
            return set()

        imports_text = imports_match.group(1)
        imported_mibs: Set[str] = set()

        # Parse "FROM MIB_NAME" patterns
        from_matches = re.findall(r"FROM\s+(\S+)", imports_text)
        for mib_name in from_matches:
            # Clean up - remove trailing punctuation
            mib_name = mib_name.rstrip(";,")
            if mib_name and mib_name not in ("", " "):
                imported_mibs.add(mib_name)

        return imported_mibs

    def get_direct_dependencies(self, mib_name: str) -> Set[str]:
        """Get the direct dependencies of a MIB.

        Args:
            mib_name: Name of the MIB.

        Returns:
            Set of MIB names directly imported by this MIB.
        """
        if mib_name in self._dependency_cache:
            return self._dependency_cache[mib_name].copy()

        mib_path = self._find_mib_source(mib_name)
        if mib_path:
            dependencies = self._parse_imports(mib_path)
        else:
            dependencies = set()

        self._dependency_cache[mib_name] = dependencies
        return dependencies.copy()

    def get_all_dependencies(self, mib_name: str, visited: Optional[Set[str]] = None) -> Set[str]:
        """Get all dependencies of a MIB (direct and transitive).

        Args:
            mib_name: Name of the MIB.
            visited: Set of already visited MIBs (used for recursion).

        Returns:
            Set of all MIB names (direct and transitive) imported by this MIB.
        """
        if visited is None:
            visited = set()

        if mib_name in visited:
            return set()

        visited.add(mib_name)
        all_deps: Set[str] = set()

        direct_deps = self.get_direct_dependencies(mib_name)
        all_deps.update(direct_deps)

        for dep in direct_deps:
            all_deps.update(self.get_all_dependencies(dep, visited.copy()))

        return all_deps

    def build_dependency_tree(self, mib_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Build a hierarchical dependency tree for a list of MIBs.

        Args:
            mib_names: List of MIB names to analyze.

        Returns:
            Dictionary mapping MIB names to their dependency information:
            {
                "mib_name": {
                    "direct_deps": [...],          # Direct imports
                    "transitive_deps": [...],      # All non-direct imports
                    "all_deps": [...],             # All imports (direct + transitive)
                    "is_configured": True/False    # Whether in the input list
                }
            }
        """
        tree: Dict[str, Dict[str, Any]] = {}

        # Process each configured MIB
        for mib_name in mib_names:
            direct_deps = self.get_direct_dependencies(mib_name)
            all_deps = self.get_all_dependencies(mib_name)
            transitive_deps = all_deps - direct_deps

            tree[mib_name] = {
                "direct_deps": sorted(list(direct_deps)),
                "transitive_deps": sorted(list(transitive_deps)),
                "all_deps": sorted(list(all_deps)),
                "is_configured": True,
            }

            # Add transitive dependencies that aren't configured
            for dep in all_deps:
                if dep not in tree:
                    dep_direct_deps = self.get_direct_dependencies(dep)
                    dep_all_deps = self.get_all_dependencies(dep)
                    dep_transitive_deps = dep_all_deps - dep_direct_deps

                    tree[dep] = {
                        "direct_deps": sorted(list(dep_direct_deps)),
                        "transitive_deps": sorted(list(dep_transitive_deps)),
                        "all_deps": sorted(list(dep_all_deps)),
                        "is_configured": False,
                    }

        return tree

    def get_configured_mibs_with_deps(self, mib_names: List[str]) -> Dict[str, Any]:
        """Get a hierarchical structure of configured MIBs with their dependencies.

        Args:
            mib_names: List of configured MIB names.

        Returns:
            Dictionary structure optimized for UI display:
            {
                "configured": [...],  # Direct list of configured MIBs
                "tree": {...},        # Full dependency tree
                "summary": {...}      # Summary statistics
            }
        """
        tree = self.build_dependency_tree(mib_names)

        configured = sorted(mib_names)
        all_mib_names = set(tree.keys())
        transitive = sorted(list(all_mib_names - set(configured)))

        return {
            "configured_mibs": configured,
            "transitive_dependencies": transitive,
            "tree": tree,
            "summary": {
                "configured_count": len(configured),
                "transitive_count": len(transitive),
                "total_count": len(all_mib_names),
            },
        }

    def generate_mermaid_diagram(self, mib_names: List[str]) -> str:
        """Generate a Mermaid diagram showing MIB dependencies.

        Args:
            mib_names: List of configured MIB names.

        Returns:
            Mermaid diagram syntax as a string.
        """
        dependency_info = self.get_configured_mibs_with_deps(mib_names)
        tree: Dict[str, Any] = cast(Dict[str, Any], dependency_info.get("tree", {}))

        lines: List[str] = ["graph TD"]
        added_nodes: Set[str] = set()
        added_edges: Set[str] = set()

        # Add all nodes first, with styling based on whether they're configured
        for mib_name in tree.keys():
            if mib_name not in added_nodes:
                mib_data: Dict[str, Any] = cast(Dict[str, Any], tree[mib_name])
                is_configured = mib_data.get("is_configured", False)
                if is_configured:
                    # Configured MIBs: normal styling
                    safe_name = mib_name.replace("-", "_")
                    lines.append(
                        f'    {safe_name}["{mib_name}"]\n    style {safe_name} fill:#7dd3fc,stroke:#0369a1,color:#000'
                    )
                else:
                    # Transitive dependencies: shaded/faded styling
                    safe_name = mib_name.replace("-", "_")
                    lines.append(
                        f'    {safe_name}["{mib_name}"]\n    style {safe_name} fill:#e5e7eb,stroke:#9ca3af,color:#666'
                    )
                added_nodes.add(mib_name)

        # Add edges for direct dependencies
        for mib_name, mib_info_val in tree.items():
            mib_info: Dict[str, Any] = cast(Dict[str, Any], mib_info_val)
            direct_deps = mib_info.get("direct_deps", [])
            for dep in direct_deps:
                edge_key = f"{mib_name}->{dep}"
                if edge_key not in added_edges:
                    safe_src = mib_name.replace("-", "_")
                    safe_dst = dep.replace("-", "_")
                    lines.append(f"    {safe_src} -->|imports| {safe_dst}")
                    added_edges.add(edge_key)

        return "\n".join(lines)

    def generate_mermaid_diagram_json(self, mib_names: List[str]) -> Dict[str, Any]:
        """Generate a Mermaid diagram and return with metadata.

        Args:
            mib_names: List of configured MIB names.

        Returns:
            Dictionary with diagram and metadata.
        """
        diagram = self.generate_mermaid_diagram(mib_names)
        dependency_info = self.get_configured_mibs_with_deps(mib_names)

        return {
            "mermaid_code": diagram,
            "configured_mibs": dependency_info.get("configured_mibs", []),
            "transitive_dependencies": dependency_info.get("transitive_dependencies", []),
            "summary": dependency_info.get("summary", {}),
        }
