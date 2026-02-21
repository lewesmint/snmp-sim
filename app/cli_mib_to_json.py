"""CLI wrapper for generating behaviour JSON from compiled MIBs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

from app.generator import BehaviourGenerator
from app.app_config import AppConfig


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
        stripped_line = line.strip()
        if stripped_line.startswith("IMPORTS"):
            in_imports = True
            continue
        if in_imports:
            if ";" in stripped_line:
                in_imports = False
                line_part = stripped_line.split(";")[0]
            else:
                line_part = stripped_line
            parts = line_part.split("FROM")
            if len(parts) == 2:
                mib_name = parts[1].strip().rstrip(";")
                mib_name = mib_name.split()[0]
                imported_mibs.add(mib_name)

    for mib in imported_mibs:
        from pathlib import Path

        py_path = Path(compiled_dir) / f"{mib}.py"
        if not py_path.exists():
            print(
                f"WARNING: MIB imports {mib}, but {py_path} is missing. "
                "Compile this MIB to avoid runtime errors."
            )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate schema.json from compiled MIB Python files. "
        "If no MIB is specified, processes all MIBs configured in agent_config.yaml. "
        "Creates {output-dir}/{MIB_NAME}/schema.json with structure and initial values."
    )
    parser.add_argument(
        "compiled_mib_py",
        nargs="?",
        default=None,
        help="Path to the compiled MIB .py file (optional, if omitted processes all configured MIBs)",
    )
    parser.add_argument("mib_name", nargs="?", default=None, help="MIB module name")
    parser.add_argument(
        "mib_txt_path", nargs="?", default=None, help="Path to MIB source .txt file"
    )
    parser.add_argument(
        "--output-dir",
        default="agent-model",
        help="Base directory for MIB schemas (default: agent-model)",
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Disable loading default value plugins",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    generator = BehaviourGenerator(
        output_dir=args.output_dir,
        load_default_plugins=not args.no_plugins,
    )

    if args.compiled_mib_py is None:
        # Process all configured MIBs
        try:
            config = AppConfig()
        except FileNotFoundError:
            print("Error: Config file not found, and no MIB specified", file=sys.stderr)
            return 1
        mibs = config.get("mibs", [])
        if not mibs:
            print("No MIBs configured", file=sys.stderr)
            return 1
        for mib in mibs:
            compiled_path = Path("compiled-mibs") / f"{mib}.py"
            if not compiled_path.exists():
                print(
                    f"Warning: Compiled MIB not found: {compiled_path}", file=sys.stderr
                )
                continue
            json_path = generator.generate(
                str(compiled_path), mib_name=mib, force_regenerate=True
            )
            print(f"Schema JSON written to {json_path}")
    else:
        # Process single MIB
        if not os.path.exists(args.compiled_mib_py):
            print(
                f"Error: compiled MIB not found: {args.compiled_mib_py}",
                file=sys.stderr,
            )
            return 1

        if args.mib_txt_path:
            compiled_dir = os.path.dirname(args.compiled_mib_py)
            check_imported_mibs(args.mib_txt_path, compiled_dir)

        json_path = generator.generate(
            args.compiled_mib_py,
            mib_name=args.mib_name,
            force_regenerate=True,
        )

        print(f"Schema JSON written to {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
