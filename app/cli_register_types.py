"""CLI wrapper for building and exporting the SNMP type registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from app import build_type_registry
from app.base_type_handler import BaseTypeHandler


def main(argv: Iterable[str] | None = None) -> int:
    """
    Build the SNMP type registry from compiled MIBs and export to JSON.

    This CLI tool provides a convenient way to register types discovered from
    compiled MIB files. It dynamically discovers SNMP types from SNMPv2-SMI
    and builds a comprehensive type registry with constraints, enums, and metadata.

    Example:
        python -m app.cli_register_types
        python -m app.cli_register_types --compiled-mibs-dir custom-mibs --output types.json
    """
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
        default="data/types.json",
        help="Output path for the type registry JSON file (default: data/types.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information about discovered types",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # Check if compiled MIBs directory exists
    compiled_dir = Path(args.compiled_mibs_dir)
    if not compiled_dir.exists():
        print(
            f"Error: Compiled MIBs directory not found: {compiled_dir}", file=sys.stderr
        )
        print(
            "Please compile MIBs first using: python -m app.cli_compile_mib",
            file=sys.stderr,
        )
        return 1

    try:
        print(f"Building type registry from: {compiled_dir}")
        print()

        # Progress callback to show which MIB is being parsed
        def show_progress(mib_name: str) -> None:
            print(f"  Parsing MIB: {mib_name}")

        # Build the type registry
        registry = build_type_registry(
            compiled_mibs_dir=args.compiled_mibs_dir,
            output_path=args.output,
            progress_callback=show_progress,
        )

        print()
        print(f"✓ Successfully built type registry with {len(registry)} types")
        print(f"✓ Exported to: {args.output}")

        if args.verbose:
            # Create a BaseTypeHandler to get default values
            handler = BaseTypeHandler(type_registry=registry)

            print()
            print("Discovered types:")
            print(
                f"  {'Type Name':<30s} {'Base Type':<20s} {'Default':<15s} {'MIB':<20s} {'Used By'}"
            )
            print(f"  {'-' * 30} {'-' * 20} {'-' * 15} {'-' * 20} {'-' * 8}")

            for type_name in sorted(registry.keys()):
                base_type = registry[type_name].get("base_type") or "unknown"
                used_by_list = registry[type_name].get("used_by", [])
                used_by_count = len(used_by_list)

                # Skip types with no base_type and no usages (incomplete TC definitions)
                if base_type == "unknown" and used_by_count == 0:
                    continue

                # Get default value
                try:
                    default_value = handler.get_default_value(type_name)

                    # Check if this is an enum type and format with enum name
                    enums = registry[type_name].get("enums", [])
                    if enums and isinstance(default_value, int):
                        # Find the enum name for this value
                        enum_name = None
                        for enum in enums:
                            if enum.get("value") == default_value:
                                enum_name = enum.get("name")
                                break
                        if enum_name:
                            default_str = f"{default_value}({enum_name})"
                        else:
                            default_str = str(default_value)
                    # Format default value for display
                    elif isinstance(default_value, str):
                        default_str = (
                            f'"{default_value}"'
                            if len(default_value) < 10
                            else f'"{default_value[:7]}..."'
                        )
                    elif isinstance(default_value, bytes):
                        default_str = f'b"{default_value.decode("utf-8", errors="ignore")[:7]}..."'
                    else:
                        default_str = str(default_value)

                    if len(default_str) > 15:
                        default_str = default_str[:12] + "..."
                except Exception:
                    default_str = "N/A"

                # Get MIB where this type is defined (for TCs) or first used
                defined_in = registry[type_name].get("defined_in")
                if defined_in:
                    mib_name = defined_in
                elif used_by_list:
                    first_usage = used_by_list[0]
                    mib_name = (
                        first_usage.split("::")[0] if "::" in first_usage else "unknown"
                    )
                else:
                    mib_name = "SNMPv2-SMI"

                print(
                    f"  {type_name:<30s} {base_type:<20s} {default_str:<15s} {mib_name:<20s} {used_by_count}"
                )

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error building type registry: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
