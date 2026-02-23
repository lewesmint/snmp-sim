"""Application configuration management using Dynaconf."""

import sys
from pathlib import Path
from threading import Lock

from dynaconf import Dynaconf
from typing_extensions import Self

from app.model_paths import AGENT_CONFIG_FILE


class ConfigFileNotFoundError(FileNotFoundError):
    """Raised when the configuration file is missing."""

    def __init__(self, config_path: str) -> None:
        """Initialize the exception with the missing config path."""
        super().__init__(f"Config file {config_path} not found")


class AppConfig:
    """Singleton configuration manager for the SNMP agent application."""

    _instance = None
    _lock = Lock()
    initialized = False

    def get_platform_setting(self, key: str, default: object = None) -> object:
        """Get a platform-specific setting value."""
        platform_key = sys.platform  # e.g. 'linux', 'darwin', 'win32'
        value = self.get(key, {})
        if isinstance(value, dict):
            return value.get(platform_key, default)
        return default

    def __new__(cls, *_args: object, **_kwargs: object) -> Self:
        """Create or return the singleton instance of AppConfig."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls.initialized = False
            return cls._instance

    def __init__(self, config_path: str = "agent_config.yaml") -> None:
        """Initialize singleton settings once from the specified config path."""
        if self.__class__.initialized and hasattr(self, "settings"):
            return
        self._init_config(config_path)

    def _init_config(self, config_path: str) -> None:
        """Initialize the configuration from the specified file."""
        if self.__class__.initialized:
            return

        # If caller passed the default name, prefer config/agent_config.yaml if present
        if config_path == "agent_config.yaml":
            if AGENT_CONFIG_FILE.exists():
                config_path = str(AGENT_CONFIG_FILE)

        if not Path(config_path).exists():
            raise ConfigFileNotFoundError(config_path)

        self.settings = Dynaconf(settings_files=[config_path], environments=False)
        self.__class__.initialized = True

    def get(self, key: str, default: object = None) -> object:
        """Get a configuration value by key."""
        return self.settings.get(key, default)

    def reload(self) -> None:
        """Reload the configuration from disk."""
        self.settings.reload()
