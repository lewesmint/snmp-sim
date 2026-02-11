#!/usr/bin/env python3
"""
CLI tool to bake current MIB state into agent-model schema files.

This tool:
1. Backs up existing agent-model directory to agent-model-backups/{timestamp}/
2. Reads current state from data/mib_state.json
3. Merges state values into schema files as initial_value
4. Updates schema files in-place
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def backup_schemas(schema_dir: Path, backup_base: Path) -> Path:
    """Backup existing schema directory with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / timestamp
    
    if schema_dir.exists():
        print(f"Backing up {schema_dir} to {backup_dir}...")
        shutil.copytree(schema_dir, backup_dir)
        print(f"✓ Backup created: {backup_dir}")
    else:
        print(f"Warning: Schema directory {schema_dir} does not exist, skipping backup")
    
    return backup_dir


def load_mib_state(state_file: Path) -> Dict[str, Any]:
    """Load current MIB state from mib_state.json."""
    if not state_file.exists():
        print(f"Warning: State file {state_file} does not exist")
        return {"scalars": {}, "tables": {}, "deleted_instances": []}
    
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def bake_state_into_schemas(schema_dir: Path, state: Dict[str, Any]) -> int:
    """
    Bake state values into schema files as initial_value.
    
    Returns the number of values baked.
    """
    baked_count = 0
    scalars = state.get("scalars", {})
    tables = state.get("tables", {})
    
    # Process all schema files
    for schema_file in schema_dir.rglob("schema.json"):
        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
            
            modified = False
            objects = schema.get("objects", {})
            
            # Bake scalar values
            for oid, value in scalars.items():
                if oid in objects:
                    objects[oid]["initial"] = value
                    modified = True
                    baked_count += 1
                    print(f"  Baked scalar {oid} = {value}")
            
            # Bake table instances
            for table_oid, table_data in tables.items():
                if table_oid in objects:
                    # Store table rows in the schema
                    # Merge instances from state into rows
                    objects[table_oid]["rows"] = table_data.get("instances", [])
                    modified = True
                    row_count = len(objects[table_oid]["rows"])
                    baked_count += row_count
                    print(f"  Baked {row_count} row(s) for table {table_oid}")
            
            # Write back if modified
            if modified:
                with open(schema_file, "w", encoding="utf-8") as f:
                    json.dump(schema, f, indent=2)
                print(f"✓ Updated {schema_file.relative_to(schema_dir.parent)}")
        
        except Exception as e:
            print(f"Error processing {schema_file}: {e}", file=sys.stderr)
    
    return baked_count


def main(argv: list[str] | None = None) -> int:
    """Main entry point for baking state into schemas."""
    parser = argparse.ArgumentParser(
        description="Bake current MIB state into agent-model schema files"
    )
    parser.add_argument(
        "--schema-dir",
        default="agent-model",
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--state-file",
        default="data/mib_state.json",
        help="MIB state file to bake from (default: data/mib_state.json)",
    )
    parser.add_argument(
        "--backup-dir",
        default="agent-model-backups",
        help="Directory for backups (default: agent-model-backups)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup before baking",
    )
    
    args = parser.parse_args(argv)
    
    schema_dir = Path(args.schema_dir)
    state_file = Path(args.state_file)
    backup_base = Path(args.backup_dir)
    
    print("=" * 60)
    print("Baking MIB State into Agent Model Schemas")
    print("=" * 60)
    
    # Backup existing schemas
    if not args.no_backup:
        backup_dir = backup_schemas(schema_dir, backup_base)
    else:
        print("Skipping backup (--no-backup specified)")
    
    # Load current state
    print(f"\nLoading state from {state_file}...")
    state = load_mib_state(state_file)
    scalar_count = len(state.get("scalars", {}))
    table_count = len(state.get("tables", {}))
    print(f"✓ Loaded {scalar_count} scalar(s) and {table_count} table(s)")
    
    # Bake state into schemas
    print(f"\nBaking state into schemas in {schema_dir}...")
    baked_count = bake_state_into_schemas(schema_dir, state)
    
    print("\n" + "=" * 60)
    print(f"✓ Baking complete! Baked {baked_count} value(s) into schemas")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

