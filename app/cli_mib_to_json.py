"""CLI wrapper for generating behaviour JSON from compiled MIBs."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from app.generator import BehaviourGenerator


def check_imported_mibs(mib_txt_path: str, compiled_dir: str) -> None:
    """Parse IMPORTS in a MIB text file and warn about missing compiled MIBs."""
    if not os.path.exists(mib_txt_path):
        print(f"WARNING: MIB source file {mib_txt_path} not found for import check.")
        return

    with open(mib_txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    in_imports = False
    imported_mibs: set[str] = set()
    for line in lines:
        l = line.strip()
        if l.startswith("IMPORTS"):
            in_imports = True
            continue
        if in_imports:
            if ";" in l:
                in_imports = False
                l = l.split(";")[0]
            parts = l.split("FROM")
            if len(parts) == 2:
                mib_name = parts[1].strip().rstrip(";")
                mib_name = mib_name.split()[0]
                imported_mibs.add(mib_name)

    for mib in imported_mibs:
        py_path = os.path.join(compiled_dir, f"{mib}.py")
        if not os.path.exists(py_path):
            print(
                f"WARNING: MIB imports {mib}, but {py_path} is missing. "
                "Compile this MIB to avoid runtime errors."
            )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate schema.json from a compiled MIB Python file. "
                    "Creates {output-dir}/{MIB_NAME}/schema.json with structure and initial values."
    )
    parser.add_argument("compiled_mib_py", help="Path to the compiled MIB .py file")
    parser.add_argument("mib_name", nargs="?", default=None, help="MIB module name")
    parser.add_argument("mib_txt_path", nargs="?", default=None, help="Path to MIB source .txt file")
    parser.add_argument(
        "--output-dir",
        default="mock-behaviour",
        help="Base directory for MIB schemas (default: mock-behaviour)",
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Disable loading default value plugins",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.path.exists(args.compiled_mib_py):
        print(f"Error: compiled MIB not found: {args.compiled_mib_py}", file=sys.stderr)
        return 1

    if args.mib_txt_path:
        compiled_dir = os.path.dirname(args.compiled_mib_py)
        check_imported_mibs(args.mib_txt_path, compiled_dir)

    generator = BehaviourGenerator(
        output_dir=args.output_dir,
        load_default_plugins=not args.no_plugins,
    )

    json_path = generator.generate(
        args.compiled_mib_py,
        mib_name=args.mib_name,
        force_regenerate=True,
    )

    print(f"Schema JSON written to {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
