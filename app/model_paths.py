"""Centralized filesystem paths for model and related assets."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
AGENT_MODEL_DIR = PROJECT_ROOT / "agent-model"
MIB_STATE_FILE = AGENT_MODEL_DIR / "mib_state.json"
AGENT_MODEL_BACKUPS_DIR = PROJECT_ROOT / "agent-model-backups"
AGENT_MODEL_PRESETS_DIR = PROJECT_ROOT / "agent-model-presets"
COMPILED_MIBS_DIR = PROJECT_ROOT / "compiled-mibs"
AGENT_CONFIG_FILE = CONFIG_DIR / "agent_config.yaml"
GUI_CONFIG_YAML_FILE = CONFIG_DIR / "gui_config.yaml"
GUI_CONFIG_JSON_FILE = CONFIG_DIR / "gui_config.json"
SNMPD_CONFIG_FILE = CONFIG_DIR / "snmpd.conf"
TRAP_OVERRIDES_FILE = CONFIG_DIR / "trap_overrides.json"
TYPE_REGISTRY_FILE = CONFIG_DIR / "types.json"


def _resolve_project_root(module_file: str | Path | None = None) -> Path:
    if module_file is None:
        return PROJECT_ROOT
    return Path(module_file).resolve().parent.parent


def agent_model_dir(module_file: str | Path | None = None) -> Path:
    """Return the `agent-model` directory for the current project root."""
    return _resolve_project_root(module_file) / "agent-model"


def mib_state_file(module_file: str | Path | None = None) -> Path:
    """Return the canonical path to `mib_state.json` in the model directory."""
    return agent_model_dir(module_file) / "mib_state.json"


def compiled_mibs_dir(module_file: str | Path | None = None) -> Path:
    """Return the `compiled-mibs` directory for the current project root."""
    return _resolve_project_root(module_file) / "compiled-mibs"


def config_dir(module_file: str | Path | None = None) -> Path:
    """Return the `config` directory for the current project root."""
    return _resolve_project_root(module_file) / "config"
