#!/usr/bin/env python3
from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover (older Pythons)
    import importlib_metadata  # type: ignore[no-redef]


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}


@dataclass(frozen=True)
class Config:
    project_root: Path
    exclude_dirs: set[str]
    write_freeze: bool
    freeze_path: Path
    output_path: Path


def _is_excluded(path: Path, exclude_dirs: set[str]) -> bool:
    parts = set(path.parts)
    return bool(parts.intersection(exclude_dirs))


def find_imported_top_level_modules(
    project_root: Path, exclude_dirs: set[str]
) -> set[str]:
    modules: set[str] = set()

    for py_file in project_root.rglob("*.py"):
        if _is_excluded(py_file, exclude_dirs):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            # Skip files we cannot parse (generated, partial, etc.)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    modules.add(name.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".", 1)[0])

    return modules


def build_module_to_distribution_map() -> dict[str, set[str]]:
    """
    Returns mapping: top-level module name -> set of distribution names
    using the currently installed environment.
    """
    mapping: dict[str, set[str]] = {}
    try:
        pkgs = importlib_metadata.packages_distributions()
    except Exception:
        # Very old/odd environments: fall back to empty mapping
        return mapping

    for module_name, dists in pkgs.items():
        mapping[module_name] = set(dists)

    return mapping


def get_distribution_versions(dist_names: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for dist in dist_names:
        try:
            versions[dist] = importlib_metadata.version(dist)
        except importlib_metadata.PackageNotFoundError:
            continue
    return versions


def write_freeze(freeze_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        check=True,
        capture_output=True,
        text=True,
    )
    freeze_path.write_text(result.stdout, encoding="utf-8")


def main() -> int:
    cfg = Config(
        project_root=Path(".").resolve(),
        exclude_dirs=set(DEFAULT_EXCLUDE_DIRS),
        write_freeze=True,
        freeze_path=Path("requirements.full.txt"),
        output_path=Path("requirements.txt"),
    )

    if cfg.write_freeze:
        try:
            write_freeze(cfg.freeze_path)
        except subprocess.CalledProcessError as exc:
            print("Failed to run pip freeze.", file=sys.stderr)
            print(exc.stderr or str(exc), file=sys.stderr)
            return 1

    imported_modules = find_imported_top_level_modules(
        cfg.project_root, cfg.exclude_dirs
    )
    module_to_dist = build_module_to_distribution_map()

    required_dists: set[str] = set()
    unresolved_modules: set[str] = set()

    for module in sorted(imported_modules):
        dists = module_to_dist.get(module)
        if not dists:
            unresolved_modules.add(module)
            continue

        # Many modules map cleanly to one dist, but some map to multiple.
        # Keep them all (safe/minimal enough, avoids missing deps).
        required_dists.update(dists)

    versions = get_distribution_versions(required_dists)

    # Build requirements lines pinned with ==, sorted case-insensitively.
    req_lines: list[str] = []
    for dist_name in sorted(versions.keys(), key=str.lower):
        req_lines.append(f"{dist_name}=={versions[dist_name]}")

    cfg.output_path.write_text("\n".join(req_lines) + "\n", encoding="utf-8")

    print(f"Wrote: {cfg.output_path} ({len(req_lines)} packages)")
    if cfg.write_freeze:
        print(f"Wrote: {cfg.freeze_path}")

    if unresolved_modules:
        # Many of these will be stdlib (json, pathlib, typing, etc.) or local packages.
        # We print them so you can spot any third-party misses or odd imports.
        print(
            "\nImports not mapped to installed distributions (often stdlib or local code):"
        )
        for mod in sorted(unresolved_modules):
            print(f"  {mod}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
