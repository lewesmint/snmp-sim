"""Configuration, state, and preset endpoints."""


from __future__ import annotations

import contextlib
import json
import sys
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api_state import logger, state
from app.app_config import AppConfig
from app.cli_bake_state import backup_schemas, bake_state_into_schemas, load_mib_state
from app.cli_preset_manager import (
    delete_preset as delete_preset_impl,
)
from app.cli_preset_manager import (
    list_presets as list_presets_impl,
)
from app.cli_preset_manager import (
    load_preset as load_preset_impl,
)
from app.cli_preset_manager import (
    save_preset as save_preset_impl,
)
from app.generator import BehaviourGenerator
from app.model_paths import (
    AGENT_MODEL_BACKUPS_DIR,
    AGENT_MODEL_DIR,
    AGENT_MODEL_PRESETS_DIR,
    COMPILED_MIBS_DIR,
    CONFIG_DIR,
    GUI_CONFIG_JSON_FILE,
    GUI_CONFIG_YAML_FILE,
    MIB_STATE_FILE,
)

if TYPE_CHECKING:
    from app.api_shared import JsonObject

router = APIRouter()


class ConfigData(BaseModel):
    """Configuration data model for SNMP simulator settings."""

    host: str
    port: str
    trap_destinations: list[JsonObject]
    selected_trap: str
    trap_index: str
    trap_overrides: JsonObject


class PresetRequest(BaseModel):
    """Request model for loading a preset configuration."""

    preset_name: str


def _write_empty_state(state_file: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_payload: dict[str, object] = {"deleted_instances": [], "scalars": {}, "tables": {}}
    with state_file.open("w", encoding="utf-8") as f:
        json.dump(state_payload, f, indent=2, sort_keys=True)


def _clear_agent_state() -> None:
    if state.snmp_agent is not None:
        state.snmp_agent.overrides = {}
        state.snmp_agent.table_instances = {}
        state.snmp_agent.deleted_instances = []
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            state.snmp_agent.save_mib_state()


@router.get("/config")
def get_config() -> dict[str, object]:
    """Get GUI configuration from server."""
    try:
        config_path = GUI_CONFIG_YAML_FILE
        if config_path.exists():
            with config_path.open(encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config_path = GUI_CONFIG_JSON_FILE
            if config_path.exists():
                with config_path.open(encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {}
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        logger.exception("Failed to load config")
        return {}
    return config


@router.post("/config")
def save_config(config: ConfigData) -> dict[str, object]:
    """Save GUI configuration to server."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config_dict = config.model_dump()

        config_path = GUI_CONFIG_YAML_FILE
        with config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(config_dict, f)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        logger.exception("Failed to save config")
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e!s}") from e
    return {"status": "ok", "message": "Configuration saved"}


@router.post("/bake-state")
def bake_state() -> dict[str, object]:
    """Bake current MIB state into agent-model schema files."""
    schema_dir = AGENT_MODEL_DIR
    state_file = MIB_STATE_FILE
    backup_base = AGENT_MODEL_BACKUPS_DIR

    try:
        backup_dir = backup_schemas(schema_dir, backup_base)
        state_payload = load_mib_state(state_file)
        baked_count = bake_state_into_schemas(schema_dir, state_payload)
        _write_empty_state(state_file)
        _clear_agent_state()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to bake state: {e}") from e
    return {
        "status": "ok",
        "baked_count": baked_count,
        "backup_dir": str(backup_dir),
        "message": (
            f"Successfully baked {baked_count} value(s) into schemas and cleared state"
        ),
    }


@router.post("/state/reset")
def reset_state() -> dict[str, object]:
    """Clear mib_state.json (scalars, tables, deletions)."""
    state_file = MIB_STATE_FILE

    try:
        _write_empty_state(state_file)
        _clear_agent_state()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset state: {e}") from e
    return {"status": "ok", "message": "State reset"}


@router.post("/state/fresh")
def fresh_state() -> dict[str, object]:
    """Regenerate schemas and clear mib_state.json."""
    schema_dir = AGENT_MODEL_DIR
    backup_base = AGENT_MODEL_BACKUPS_DIR
    state_file = MIB_STATE_FILE

    try:
        backup_dir = backup_schemas(schema_dir, backup_base)

        config = AppConfig()
        mibs_value = config.get("mibs", [])
        mibs = mibs_value if isinstance(mibs_value, list) else []
        generator = BehaviourGenerator(output_dir=str(schema_dir))

        regenerated = 0
        for mib in mibs:
            compiled_path = COMPILED_MIBS_DIR / f"{mib}.py"
            if not compiled_path.exists():
                continue
            generator.generate(str(compiled_path), mib_name=mib, force_regenerate=True)
            regenerated += 1

        _write_empty_state(state_file)
        _clear_agent_state()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to run fresh state: {e}") from e
    return {
        "status": "ok",
        "backup_dir": str(backup_dir),
        "regenerated": regenerated,
        "message": "Fresh state complete",
    }


@router.get("/presets")
def list_presets() -> dict[str, object]:
    """List all available agent-model presets."""
    preset_base = AGENT_MODEL_PRESETS_DIR
    presets = list_presets_impl(preset_base)

    return {
        "presets": presets,
        "count": len(presets),
    }


@router.post("/presets/save")
def save_preset(request: PresetRequest) -> dict[str, object]:
    """Save current agent-model as a preset."""
    schema_dir = AGENT_MODEL_DIR
    preset_base = AGENT_MODEL_PRESETS_DIR

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = save_preset_impl(schema_dir, preset_base, request.preset_name)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to save preset: {output}")
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to save preset: {e}") from e
    return {
        "status": "ok",
        "preset_name": request.preset_name,
        "message": f"Preset '{request.preset_name}' saved successfully",
    }


@router.post("/presets/load")
def load_preset(request: PresetRequest) -> dict[str, object]:
    """Load a preset to replace current agent-model."""
    schema_dir = AGENT_MODEL_DIR
    preset_base = AGENT_MODEL_PRESETS_DIR
    backup_base = AGENT_MODEL_BACKUPS_DIR

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = load_preset_impl(
            schema_dir, preset_base, request.preset_name, backup_base, no_backup=False
        )
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to load preset: {output}")

        _write_empty_state(MIB_STATE_FILE)
        _clear_agent_state()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to load preset: {e}") from e
    return {
        "status": "ok",
        "preset_name": request.preset_name,
        "message": (
            f"Preset '{request.preset_name}' loaded successfully. "
            "Restart agent to apply changes."
        ),
    }


@router.delete("/presets/{preset_name}")
def delete_preset(preset_name: str) -> dict[str, object]:
    """Delete a preset."""
    preset_base = AGENT_MODEL_PRESETS_DIR

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        result = delete_preset_impl(preset_base, preset_name)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if result != 0:
            raise HTTPException(status_code=400, detail=f"Failed to delete preset: {output}")
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        sys.stdout = old_stdout
        raise HTTPException(status_code=500, detail=f"Failed to delete preset: {e}") from e
    return {
        "status": "ok",
        "preset_name": preset_name,
        "message": f"Preset '{preset_name}' deleted successfully",
    }
