"""Centralized filesystem paths for model and related assets."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODEL_DIR = PROJECT_ROOT / "agent-model"
MIB_STATE_FILE = AGENT_MODEL_DIR / "mib_state.json"
AGENT_MODEL_BACKUPS_DIR = PROJECT_ROOT / "agent-model-backups"
AGENT_MODEL_PRESETS_DIR = PROJECT_ROOT / "agent-model-presets"
COMPILED_MIBS_DIR = PROJECT_ROOT / "compiled-mibs"


def _resolve_project_root(module_file: str | Path | None = None) -> Path:
    if module_file is None:
        return PROJECT_ROOT
    return Path(module_file).resolve().parent.parent


def agent_model_dir(module_file: str | Path | None = None) -> Path:
    return _resolve_project_root(module_file) / "agent-model"


def mib_state_file(module_file: str | Path | None = None) -> Path:
    return agent_model_dir(module_file) / "mib_state.json"


def compiled_mibs_dir(module_file: str | Path | None = None) -> Path:
    return _resolve_project_root(module_file) / "compiled-mibs"
