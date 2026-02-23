"""MIB dependency resolver for extracting and analyzing MIB imports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast


class MibDependencyResolver:
    """Resolves MIB dependencies by parsing IMPORTS sections."""

    _MAX_MIB_SEARCH_DEPTH = 5

    def __init__(self, mib_source_dirs: list[str] | None = None) -> None:
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
        self._dependency_cache: dict[str, set[str]] = {}
        self._mib_file_cache: dict[str, str | None] = {}

    def _find_mib_source(self, mib_name: str) -> str | None:
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
            search_path = Path(search_dir)
            if not search_path.exists():
                continue

            # Try direct match first
            for ext in [".txt", ".mib", ".my"]:
                mib_path = search_path / f"{mib_name}{ext}"
                if mib_path.exists():
                    self._mib_file_cache[mib_name] = str(mib_path)
                    return str(mib_path)

            # Search subdirectories recursively with depth limit
            for candidate in search_path.rglob("*"):
                if not candidate.is_file():
                    continue
                rel_parts = candidate.relative_to(search_path).parts
                depth = max(len(rel_parts) - 1, 0)
                if depth > self._MAX_MIB_SEARCH_DEPTH:
                    continue
                if candidate.stem != mib_name:
                    continue
                if candidate.suffix not in (".txt", ".mib", ".my"):
                    continue
                self._mib_file_cache[mib_name] = str(candidate)
                return str(candidate)

        self._mib_file_cache[mib_name] = None
        return None

    def _parse_imports(self, mib_path: str) -> set[str]:
        """Parse the IMPORTS section of a MIB file.

        Args:
            mib_path: Path to the MIB source file.

        Returns:
            Set of MIB names imported by this MIB.

        """
        if not Path(mib_path).exists():
            return set()

        try:
            with Path(mib_path).open(encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return set()

        # Extract IMPORTS section using regex
        imports_match = re.search(r"IMPORTS\s+(.*?);\s*(?=\w+|$)", content, re.DOTALL)
        if not imports_match:
            return set()

        imports_text = imports_match.group(1)
        imported_mibs: set[str] = set()

        # Parse "FROM MIB_NAME" patterns
        from_matches = re.findall(r"FROM\s+(\S+)", imports_text)
        for imported_name in from_matches:
            # Clean up - remove trailing punctuation
            cleaned_name = imported_name.rstrip(";,")
            if cleaned_name and cleaned_name not in ("", " "):
                imported_mibs.add(cleaned_name)

        return imported_mibs

    def get_direct_dependencies(self, mib_name: str) -> set[str]:
        """Get the direct dependencies of a MIB.

        Args:
            mib_name: Name of the MIB.

        Returns:
            Set of MIB names directly imported by this MIB.

        """
        if mib_name in self._dependency_cache:
            return self._dependency_cache[mib_name].copy()

        mib_path = self._find_mib_source(mib_name)
        dependencies = self._parse_imports(mib_path) if mib_path else set()

        self._dependency_cache[mib_name] = dependencies
        return dependencies.copy()

    def get_all_dependencies(self, mib_name: str, visited: set[str] | None = None) -> set[str]:
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
        all_deps: set[str] = set()

        direct_deps = self.get_direct_dependencies(mib_name)
        all_deps.update(direct_deps)

        for dep in direct_deps:
            all_deps.update(self.get_all_dependencies(dep, visited.copy()))

        return all_deps

    def build_dependency_tree(self, mib_names: list[str]) -> dict[str, dict[str, Any]]:
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
        tree: dict[str, dict[str, Any]] = {}

        # Process each configured MIB
        for mib_name in mib_names:
            direct_deps = self.get_direct_dependencies(mib_name)
            all_deps = self.get_all_dependencies(mib_name)
            transitive_deps = all_deps - direct_deps

            tree[mib_name] = {
                "direct_deps": sorted(direct_deps),
                "transitive_deps": sorted(transitive_deps),
                "all_deps": sorted(all_deps),
                "is_configured": True,
            }

            # Add transitive dependencies that aren't configured
            for dep in all_deps:
                if dep not in tree:
                    dep_direct_deps = self.get_direct_dependencies(dep)
                    dep_all_deps = self.get_all_dependencies(dep)
                    dep_transitive_deps = dep_all_deps - dep_direct_deps

                    tree[dep] = {
                        "direct_deps": sorted(dep_direct_deps),
                        "transitive_deps": sorted(dep_transitive_deps),
                        "all_deps": sorted(dep_all_deps),
                        "is_configured": False,
                    }

        return tree

    def get_configured_mibs_with_deps(self, mib_names: list[str]) -> dict[str, Any]:
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
        transitive = sorted(all_mib_names - set(configured))

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

    def generate_mermaid_diagram(self, mib_names: list[str]) -> str:
        """Generate a Mermaid diagram showing MIB dependencies.

        Args:
            mib_names: List of configured MIB names.

        Returns:
            Mermaid diagram syntax as a string.

        """
        dependency_info = self.get_configured_mibs_with_deps(mib_names)
        tree = cast("dict[str, dict[str, Any]]", dependency_info.get("tree", {}))

        lines: list[str] = ["graph TD"]
        added_nodes: set[str] = set()
        added_edges: set[str] = set()

        # Add all nodes first, with styling based on whether they're configured
        for mib_name in tree:
            if mib_name not in added_nodes:
                mib_data = tree[mib_name]
                is_configured = mib_data.get("is_configured", False)
                if is_configured:
                    # Configured MIBs: normal styling
                    safe_name = mib_name.replace("-", "_")
                    lines.append(
                        f'    {safe_name}["{mib_name}"]\n'
                        f"    style {safe_name} fill:#7dd3fc,stroke:#0369a1,color:#000"
                    )
                else:
                    # Transitive dependencies: shaded/faded styling
                    safe_name = mib_name.replace("-", "_")
                    lines.append(
                        f'    {safe_name}["{mib_name}"]\n'
                        f"    style {safe_name} fill:#e5e7eb,stroke:#9ca3af,color:#666"
                    )
                added_nodes.add(mib_name)

        # Add edges for direct dependencies
        for mib_name, mib_info in tree.items():
            direct_deps = cast("list[str]", mib_info.get("direct_deps", []))
            for dep in direct_deps:
                edge_key = f"{mib_name}->{dep}"
                if edge_key not in added_edges:
                    safe_src = mib_name.replace("-", "_")
                    safe_dst = dep.replace("-", "_")
                    lines.append(f"    {safe_src} -->|imports| {safe_dst}")
                    added_edges.add(edge_key)

        return "\n".join(lines)

    def generate_mermaid_diagram_json(self, mib_names: list[str]) -> dict[str, Any]:
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
