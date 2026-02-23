"""CLI wrapper for compiling MIB files using app compiler."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from app.app_config import AppConfig
from app.compiler import MibCompilationError, MibCompiler

logger = logging.getLogger(__name__)


def _print_results(results: dict[str, str]) -> None:
    for mib, status in results.items():
        logger.info("%s: %s", mib, status)


def _has_failures(results: dict[str, str]) -> bool:
    return any(status not in ("compiled", "untouched") for status in results.values())


def main(argv: Iterable[str] | None = None) -> int:
    """Compile a MIB .txt file to Python using the app compiler."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Compile a MIB .txt file to Python using the app compiler.",
    )
    parser.add_argument("mib_file_path", help="Path to the MIB .txt file")
    parser.add_argument("output_dir", nargs="?", default="compiled-mibs", help="Output directory")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if not Path(args.mib_file_path).exists():
        logger.error("Error: MIB file not found: %s", args.mib_file_path)
        return 1

    app_config = None
    try:
        app_config = AppConfig()
    except FileNotFoundError:
        app_config = None

    compiler = MibCompiler(args.output_dir, app_config)

    try:
        compiler.compile(args.mib_file_path)
    except MibCompilationError:
        logger.exception("MIB compilation failed")
        if compiler.last_compile_results:
            _print_results(compiler.last_compile_results)
        return 1

    if compiler.last_compile_results:
        _print_results(compiler.last_compile_results)

    return 1 if _has_failures(compiler.last_compile_results) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
