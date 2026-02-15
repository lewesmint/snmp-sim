#!/usr/bin/env python3
"""
CLI tool to bake current MIB state into agent-model schema files.

This tool:
1. Backs up existing agent-model directory to agent-model-backups/{timestamp}/
2. Reads current state from data/mib_state.json
3. Merges state values into schema files as initial values
4. Updates schema files in-place
"""

import argparse
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


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


def load_mib_state(state_file: Path) -> dict[str, Any]:
    """Load current MIB state from mib_state.json."""
    if not state_file.exists():
        print(f"Warning: State file {state_file} does not exist")
        return {"scalars": {}, "tables": {}, "deleted_instances": []}
    
    with open(state_file, "r", encoding="utf-8") as f:
        state: dict[str, Any] = json.load(f)
        return state


def bake_state_into_schemas(schema_dir: Path, state: dict[str, Any]) -> int:
    """
    Bake state values into schema files as initial values.
    
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
            
            # Handle both old flat structure and new {"objects": ..., "traps": ...} structure
            if "objects" in schema:
                objects = schema["objects"]
            else:
                objects = schema
            
            # Bake scalar values
            for oid, value in scalars.items():
                # Find object by OID string
                for obj_name, obj_data in objects.items():
                    if isinstance(obj_data, dict) and "oid" in obj_data:
                        obj_oid_str = ".".join(str(x) for x in obj_data["oid"])
                        if obj_oid_str == oid or oid.endswith(f".{obj_oid_str}.0"):
                            # Strip instance suffix (.0) if present
                            if oid.endswith(".0"):
                                obj_oid_base = oid[:-2]
                            else:
                                obj_oid_base = oid
                            
                            if obj_oid_str == obj_oid_base:
                                obj_data["initial"] = value
                                modified = True
                                baked_count += 1
                                print(f"  Baked scalar {obj_name} ({oid}) = {value}")
            
            # Bake table instances
            # table_instances format: {table_oid: {instance_str: {column_values: {...}, created_at: ...}}}
            for table_oid, instances_dict in tables.items():
                if not isinstance(instances_dict, dict):
                    continue
                # Find the table object and entry by OID
                for obj_name, obj_data in objects.items():
                    if isinstance(obj_data, dict) and obj_data.get("type") == "MibTable":
                        obj_oid_str = ".".join(str(x) for x in obj_data["oid"])
                        if obj_oid_str == table_oid:
                            # Find the entry object by OID structure (table_oid + [1])
                            entry_obj = {}
                            expected_entry_oid = list(obj_data["oid"]) + [1]
                            for other_name, other_data in objects.items():
                                if isinstance(other_data, dict) and other_data.get("type") == "MibTableRow":
                                    if list(other_data.get("oid", [])) == expected_entry_oid:
                                        entry_obj = other_data
                                        break
                            index_columns = entry_obj.get("indexes", [])
                            
                            # Build columns metadata for type info (needed for IpAddress parsing)
                            columns_meta: dict[str, Any] = {}
                            for col_name in index_columns:
                                if col_name in objects:
                                    columns_meta[col_name] = objects[col_name]
                            
                            # Convert instance dict to list of row dicts
                            rows: list[dict[str, Any]] = []
                            for instance_str, instance_data in instances_dict.items():
                                # Reconstruct index values from instance_str and index_columns metadata
                                row: dict[str, Any] = {}
                                
                                # Parse instance_str to extract index values
                                parts = instance_str.split(".")
                                pos = 0
                                for col_name in index_columns:
                                    col_meta = columns_meta.get(col_name, {})
                                    col_type = col_meta.get("type", "")
                                    
                                    if col_type == "IpAddress":
                                        # IpAddress uses 4 octets
                                        if pos + 4 <= len(parts):
                                            row[col_name] = ".".join(parts[pos:pos + 4])
                                            pos += 4
                                        else:
                                            # Fallback: use remaining parts
                                            row[col_name] = ".".join(parts[pos:])
                                            pos = len(parts)
                                    else:
                                        # Single value
                                        if pos < len(parts):
                                            # Try to convert to int if it looks like a number
                                            try:
                                                row[col_name] = int(parts[pos])
                                            except (ValueError, IndexError):
                                                row[col_name] = parts[pos] if pos < len(parts) else ""
                                            pos += 1
                                
                                # Add column values
                                if isinstance(instance_data, dict):
                                    if "column_values" in instance_data:
                                        row.update(instance_data["column_values"])
                                    elif "index_values" in instance_data:
                                        # Legacy format with explicit index_values
                                        row.update(instance_data["index_values"])
                                        if "column_values" in instance_data:
                                            row.update(instance_data["column_values"])
                                else:
                                    # Old format: instance_data is the row dict directly
                                    if isinstance(instance_data, dict):
                                        row.update(instance_data)
                                
                                if row:
                                    rows.append(row)
                            
                            if rows:
                                obj_data["rows"] = rows
                                modified = True
                                baked_count += len(rows)
                                print(f"  Baked {len(rows)} row(s) for table {obj_name} ({table_oid})")
                            break
            
            # Write back if modified
            if modified:
                with open(schema_file, "w", encoding="utf-8") as f:
                    json.dump(schema, f, indent=2)
                print(f"✓ Updated {schema_file.relative_to(schema_dir.parent)}")
        
        except Exception as e:
            print(f"Error processing {schema_file}: {e}", file=sys.stderr)
            traceback.print_exc()
    
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
        _backup_dir = backup_schemas(schema_dir, backup_base)
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

