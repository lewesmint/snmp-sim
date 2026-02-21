"""CLI wrapper for compiling MIB files using app compiler."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from app.app_config import AppConfig
from app.compiler import MibCompiler, MibCompilationError


def _print_results(results: dict[str, str]) -> None:
    for mib, status in results.items():
        print(f"{mib}: {status}")


def _has_failures(results: dict[str, str]) -> bool:
    return any(status not in ("compiled", "untouched") for status in results.values())


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile a MIB .txt file to Python using the app compiler.",
    )
    parser.add_argument("mib_file_path", help="Path to the MIB .txt file")
    parser.add_argument(
        "output_dir", nargs="?", default="compiled-mibs", help="Output directory"
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.path.exists(args.mib_file_path):
        print(f"Error: MIB file not found: {args.mib_file_path}", file=sys.stderr)
        return 1

    app_config = None
    try:
        app_config = AppConfig()
    except FileNotFoundError:
        app_config = None

    compiler = MibCompiler(args.output_dir, app_config)

    try:
        compiler.compile(args.mib_file_path)
    except MibCompilationError as exc:
        print(str(exc), file=sys.stderr)
        if compiler.last_compile_results:
            _print_results(compiler.last_compile_results)
        return 1

    if compiler.last_compile_results:
        _print_results(compiler.last_compile_results)

    return 1 if _has_failures(compiler.last_compile_results) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
