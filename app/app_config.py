from dynaconf import Dynaconf
import os
import sys
from threading import Lock
from typing import Any  # Add this import


class AppConfig:
    _instance = None
    _lock = Lock()

    def get_platform_setting(self, key: str, default: Any = None) -> Any:  # Changed to Any
        platform_key = sys.platform  # e.g. 'linux', 'darwin', 'win32'
        value = self.get(key, {})
        if isinstance(value, dict):
            return value.get(platform_key, default)
        return default

    _instance = None
    _lock = Lock()

    def __new__(cls, config_path: str = "agent_config.yaml") -> "AppConfig":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_config(config_path)
            return cls._instance

    def _init_config(self, config_path: str) -> None:
        if not hasattr(self, "settings"):
            # If caller passed the default name, prefer data/agent_config.yaml if present
            if config_path == "agent_config.yaml":
                from pathlib import Path

                data_path = Path("data") / "agent_config.yaml"
                if data_path.exists():
                    config_path = str(data_path)

            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Config file {config_path} not found")

            self.settings = Dynaconf(settings_files=[config_path], environments=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def reload(self) -> None:
        self.settings.reload()
