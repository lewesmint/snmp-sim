"""CLI wrapper for building and exporting the SNMP type registry."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from app import build_type_registry
from app.base_type_handler import BaseTypeHandler

logger = logging.getLogger(__name__)

_SHORT_STRING_LIMIT = 10
_MAX_DEFAULT_WIDTH = 15
_TRUNCATED_DEFAULT_WIDTH = 12
_TRUNCATED_STRING_PREFIX = 7


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and export SNMP type registry from compiled MIBs"
    )
    parser.add_argument(
        "--compiled-mibs-dir",
        default="compiled-mibs",
        help="Directory containing compiled MIB .py files (default: compiled-mibs)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="config/types.json",
        help="Output path for the type registry JSON file (default: config/types.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information about discovered types",
    )
    return parser


def _format_default_value(default_value: object, enums: object) -> str:
    if isinstance(enums, list) and enums and isinstance(default_value, int):
        enum_name = next(
            (
                enum.get("name")
                for enum in enums
                if isinstance(enum, dict) and enum.get("value") == default_value
            ),
            None,
        )
        default_str = f"{default_value}({enum_name})" if enum_name else str(default_value)
    elif isinstance(default_value, str):
        default_str = (
            f'"{default_value}"'
            if len(default_value) < _SHORT_STRING_LIMIT
            else f'"{default_value[:_TRUNCATED_STRING_PREFIX]}..."'
        )
    elif isinstance(default_value, bytes):
        decoded = default_value.decode("utf-8", errors="ignore")
        default_str = f'b"{decoded[:_TRUNCATED_STRING_PREFIX]}..."'
    else:
        default_str = str(default_value)

    if len(default_str) > _MAX_DEFAULT_WIDTH:
        return default_str[:_TRUNCATED_DEFAULT_WIDTH] + "..."
    return default_str


def _resolve_mib_name(type_info: dict[str, object], used_by_list: list[str]) -> str:
    defined_in = type_info.get("defined_in")
    if isinstance(defined_in, str) and defined_in:
        return defined_in
    if used_by_list:
        first_usage = used_by_list[0]
        return first_usage.split("::")[0] if "::" in first_usage else "unknown"
    return "SNMPv2-SMI"


def _log_verbose_registry(registry: dict[str, dict[str, object]]) -> None:
    handler = BaseTypeHandler(type_registry=registry)

    logger.info("")
    logger.info("Discovered types:")
    logger.info(
        "  %-30s %-20s %-15s %-20s %s",
        "Type Name",
        "Base Type",
        "Default",
        "MIB",
        "Used By",
    )
    logger.info("  %s %s %s %s %s", "-" * 30, "-" * 20, "-" * 15, "-" * 20, "-" * 8)

    for type_name in sorted(registry.keys()):
        type_info = registry[type_name]
        base_type = type_info.get("base_type") or "unknown"
        used_by_raw = type_info.get("used_by", [])
        used_by_list = used_by_raw if isinstance(used_by_raw, list) else []
        used_by_count = len(used_by_list)

        if base_type == "unknown" and used_by_count == 0:
            continue

        try:
            default_value = handler.get_default_value(type_name)
            default_str = _format_default_value(default_value, type_info.get("enums", []))
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            default_str = "N/A"

        mib_name = _resolve_mib_name(type_info, used_by_list)
        logger.info(
            "  %-30s %-20s %-15s %-20s %s",
            type_name,
            base_type,
            default_str,
            mib_name,
            used_by_count,
        )


def _run(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    compiled_dir = Path(args.compiled_mibs_dir)
    if not compiled_dir.exists():
        logger.error("Error: Compiled MIBs directory not found: %s", compiled_dir)
        logger.error("Please compile MIBs first using: python -m app.cli_compile_mib")
        return 1

    logger.info("Building type registry from: %s", compiled_dir)
    logger.info("")

    def show_progress(mib_name: str) -> None:
        logger.info("  Parsing MIB: %s", mib_name)

    registry = build_type_registry(
        compiled_mibs_dir=args.compiled_mibs_dir,
        output_path=args.output,
        progress_callback=show_progress,
    )

    logger.info("")
    logger.info("✓ Successfully built type registry with %s types", len(registry))
    logger.info("✓ Exported to: %s", args.output)

    if args.verbose:
        _log_verbose_registry(registry)

    return 0


def main(argv: Iterable[str] | None = None) -> int:
    """Build the SNMP type registry from compiled MIBs and export to JSON.

    This CLI tool provides a convenient way to register types discovered from
    compiled MIB files. It dynamically discovers SNMP types from SNMPv2-SMI
    and builds a comprehensive type registry with constraints, enums, and metadata.

    Example:
        python -m app.cli_register_types
        python -m app.cli_register_types --compiled-mibs-dir custom-mibs --output types.json

    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return _run(argv)
    except FileNotFoundError:
        logger.exception("Type registry input file not found")
        return 1
    except Exception:
        logger.exception("Error building type registry")
        return 1


if __name__ == "__main__":
    sys.exit(main())
