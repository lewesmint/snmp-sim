#!/usr/bin/env python3
"""
CLI tool to manage agent-model presets (scenarios).

This tool allows you to:
- Save current agent-model as a preset
- Load a preset to replace current agent-model
- List available presets
- Delete presets
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def list_presets(preset_base: Path) -> list[str]:
    """List all available presets."""
    if not preset_base.exists():
        return []
    
    presets = [d.name for d in preset_base.iterdir() if d.is_dir()]
    return sorted(presets)


def save_preset(schema_dir: Path, preset_base: Path, preset_name: str) -> int:
    """Save current agent-model as a preset."""
    if not schema_dir.exists():
        print(f"Error: Schema directory {schema_dir} does not exist", file=sys.stderr)
        return 1
    
    preset_dir = preset_base / preset_name
    
    if preset_dir.exists():
        response = input(f"Preset '{preset_name}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return 1
        shutil.rmtree(preset_dir)
    
    print(f"Saving preset '{preset_name}'...")
    preset_base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(schema_dir, preset_dir)
    
    # Save metadata
    metadata = {
        "name": preset_name,
        "created": datetime.now().isoformat(),
        "source": str(schema_dir),
    }
    
    import json
    with open(preset_dir / "preset_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✓ Preset '{preset_name}' saved to {preset_dir}")
    return 0


def load_preset(schema_dir: Path, preset_base: Path, preset_name: str, backup_base: Path, no_backup: bool) -> int:
    """Load a preset to replace current agent-model."""
    preset_dir = preset_base / preset_name
    
    if not preset_dir.exists():
        print(f"Error: Preset '{preset_name}' not found", file=sys.stderr)
        print(f"Available presets: {', '.join(list_presets(preset_base)) or 'none'}")
        return 1
    
    # Backup current schemas
    if not no_backup and schema_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = backup_base / f"before_preset_{preset_name}_{timestamp}"
        print(f"Backing up current schemas to {backup_dir}...")
        backup_base.mkdir(parents=True, exist_ok=True)
        shutil.copytree(schema_dir, backup_dir)
        print(f"✓ Backup created")
    
    # Remove current schemas
    if schema_dir.exists():
        print(f"Removing current schemas from {schema_dir}...")
        shutil.rmtree(schema_dir)
    
    # Copy preset to schema directory
    print(f"Loading preset '{preset_name}'...")
    shutil.copytree(preset_dir, schema_dir)
    
    # Remove metadata file from loaded preset
    metadata_file = schema_dir / "preset_metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()
    
    print(f"✓ Preset '{preset_name}' loaded successfully")
    return 0


def delete_preset(preset_base: Path, preset_name: str) -> int:
    """Delete a preset."""
    preset_dir = preset_base / preset_name
    
    if not preset_dir.exists():
        print(f"Error: Preset '{preset_name}' not found", file=sys.stderr)
        return 1
    
    response = input(f"Delete preset '{preset_name}'? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled")
        return 1
    
    shutil.rmtree(preset_dir)
    print(f"✓ Preset '{preset_name}' deleted")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for preset management."""
    parser = argparse.ArgumentParser(
        description="Manage agent-model presets (scenarios)"
    )
    parser.add_argument(
        "action",
        choices=["list", "save", "load", "delete"],
        help="Action to perform",
    )
    parser.add_argument(
        "preset_name",
        nargs="?",
        help="Preset name (required for save/load/delete)",
    )
    parser.add_argument(
        "--schema-dir",
        default="agent-model",
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--preset-dir",
        default="agent-model-presets",
        help="Directory for presets (default: agent-model-presets)",
    )
    parser.add_argument(
        "--backup-dir",
        default="agent-model-backups",
        help="Directory for backups (default: agent-model-backups)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup when loading preset",
    )
    
    args = parser.parse_args(argv)
    
    schema_dir = Path(args.schema_dir)
    preset_base = Path(args.preset_dir)
    backup_base = Path(args.backup_dir)
    
    if args.action == "list":
        presets = list_presets(preset_base)
        if presets:
            print("Available presets:")
            for preset in presets:
                print(f"  - {preset}")
        else:
            print("No presets found")
        return 0
    
    # Other actions require preset_name
    if not args.preset_name:
        print(f"Error: preset_name required for action '{args.action}'", file=sys.stderr)
        return 1
    
    if args.action == "save":
        return save_preset(schema_dir, preset_base, args.preset_name)
    elif args.action == "load":
        return load_preset(schema_dir, preset_base, args.preset_name, backup_base, args.no_backup)
    elif args.action == "delete":
        return delete_preset(preset_base, args.preset_name)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

