"""Application configuration management using Dynaconf."""

import os
import sys
from threading import Lock
from typing import Any

from dynaconf import Dynaconf


class AppConfig:
    """Singleton configuration manager for the SNMP agent application."""

    _instance = None
    _lock = Lock()
    _initialized = False

    def get_platform_setting(self, key: str, default: Any = None) -> Any:
        """Get a platform-specific setting value."""
        platform_key = sys.platform  # e.g. 'linux', 'darwin', 'win32'
        value = self.get(key, {})
        if isinstance(value, dict):
            return value.get(platform_key, default)
        return default

    def __new__(cls, config_path: str = "agent_config.yaml") -> "AppConfig":
        """Create or return the singleton instance of AppConfig."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._initialized = False
            return cls._instance

    def __init__(self, config_path: str = "agent_config.yaml") -> None:
        """Initialize singleton settings once from the specified config path."""
        if self.__class__._initialized and hasattr(self, "settings"):
            return
        self._init_config(config_path)

    def _init_config(self, config_path: str) -> None:
        """Initialize the configuration from the specified file."""
        if self.__class__._initialized:
            return

        # If caller passed the default name, prefer data/agent_config.yaml if present
        if config_path == "agent_config.yaml":
            from pathlib import Path

            data_path = Path("data") / "agent_config.yaml"
            if data_path.exists():
                config_path = str(data_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file {config_path} not found")

        self.settings = Dynaconf(settings_files=[config_path], environments=False)
        self.__class__._initialized = True

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return self.settings.get(key, default)

    def reload(self) -> None:
        """Reload the configuration from disk."""
        self.settings.reload()
