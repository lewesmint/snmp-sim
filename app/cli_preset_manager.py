"""CLI tool to manage agent-model presets (scenarios).

This tool allows you to:
- Save current agent-model as a preset
- Load a preset to replace current agent-model
- List available presets
- Delete presets
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.model_paths import AGENT_MODEL_BACKUPS_DIR, AGENT_MODEL_DIR, AGENT_MODEL_PRESETS_DIR

logger = logging.getLogger(__name__)


def list_presets(preset_base: Path) -> list[str]:
    """List all available presets."""
    if not preset_base.exists():
        return []

    presets = [directory.name for directory in preset_base.iterdir() if directory.is_dir()]
    return sorted(presets)


def save_preset(schema_dir: Path, preset_base: Path, preset_name: str) -> int:
    """Save current agent-model as a preset."""
    if not schema_dir.exists():
        logger.error("Error: Schema directory %s does not exist", schema_dir)
        return 1

    preset_dir = preset_base / preset_name
    if preset_dir.exists():
        response = input(f"Preset '{preset_name}' already exists. Overwrite? (y/N): ")
        if response.lower() != "y":
            logger.info("Cancelled")
            return 1
        shutil.rmtree(preset_dir)

    logger.info("Saving preset '%s'...", preset_name)
    preset_base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(schema_dir, preset_dir)

    metadata = {
        "name": preset_name,
        "created": datetime.now(tz=UTC).isoformat(),
        "source": str(schema_dir),
    }
    with (preset_dir / "preset_metadata.json").open("w", encoding="utf-8") as file_obj:
        json.dump(metadata, file_obj, indent=2)

    logger.info("✓ Preset '%s' saved to %s", preset_name, preset_dir)
    return 0


def load_preset(
    schema_dir: Path,
    preset_base: Path,
    preset_name: str,
    backup_base: Path,
    *,
    no_backup: bool,
) -> int:
    """Load a preset to replace current agent-model."""
    preset_dir = preset_base / preset_name

    if not preset_dir.exists():
        logger.error("Error: Preset '%s' not found", preset_name)
        logger.info("Available presets: %s", ", ".join(list_presets(preset_base)) or "none")
        return 1

    if not no_backup and schema_dir.exists():
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = backup_base / f"before_preset_{preset_name}_{timestamp}"
        logger.info("Backing up current schemas to %s...", backup_dir)
        backup_base.mkdir(parents=True, exist_ok=True)
        shutil.copytree(schema_dir, backup_dir)
        logger.info("✓ Backup created")

    if schema_dir.exists():
        logger.info("Removing current schemas from %s...", schema_dir)
        shutil.rmtree(schema_dir)

    logger.info("Loading preset '%s'...", preset_name)
    shutil.copytree(preset_dir, schema_dir)

    metadata_file = schema_dir / "preset_metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()

    logger.info("✓ Preset '%s' loaded successfully", preset_name)
    return 0


def delete_preset(preset_base: Path, preset_name: str) -> int:
    """Delete a preset."""
    preset_dir = preset_base / preset_name

    if not preset_dir.exists():
        logger.error("Error: Preset '%s' not found", preset_name)
        return 1

    response = input(f"Delete preset '{preset_name}'? (y/N): ")
    if response.lower() != "y":
        logger.info("Cancelled")
        return 1

    shutil.rmtree(preset_dir)
    logger.info("✓ Preset '%s' deleted", preset_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Manage presets."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Manage agent-model presets (scenarios)")
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
        default=str(AGENT_MODEL_DIR),
        help="Directory containing MIB schema subdirectories (default: agent-model)",
    )
    parser.add_argument(
        "--preset-dir",
        default=str(AGENT_MODEL_PRESETS_DIR),
        help="Directory for presets (default: agent-model-presets)",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(AGENT_MODEL_BACKUPS_DIR),
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
            logger.info("Available presets:")
            for preset in presets:
                logger.info("  - %s", preset)
        else:
            logger.info("No presets found")
        return 0

    if not args.preset_name:
        logger.error("Error: preset_name required for action '%s'", args.action)
        return 1

    if args.action == "save":
        return save_preset(schema_dir, preset_base, args.preset_name)
    if args.action == "load":
        return load_preset(
            schema_dir,
            preset_base,
            args.preset_name,
            backup_base,
            no_backup=args.no_backup,
        )
    if args.action == "delete":
        return delete_preset(preset_base, args.preset_name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
