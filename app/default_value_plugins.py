"""Provide a default value plugin system for SNMP behavior generation.

This module provides a plugin system for determining default values when generating
SNMP behavior JSON files. Plugins are called during MIB-to-JSON generation to provide
sensible default values for SNMP types that don't have obvious defaults.

Each plugin is a simple function that takes type_info and symbol_name and returns
either a default value or None if it doesn't handle that type.
"""

import logging
from collections.abc import Callable
from typing import cast

from app.types import DefaultValuePlugin, TypeInfo

logger = logging.getLogger(__name__)


class DefaultValuePluginRegistry:
    """Registry for default value plugins used during JSON generation."""

    def __init__(self) -> None:
        """Initialize empty plugin registries."""
        self._plugins: list[DefaultValuePlugin] = []
        self._plugin_names: dict[str, DefaultValuePlugin] = {}

    @staticmethod
    def _run_plugin(
        plugin: DefaultValuePlugin,
        type_info: TypeInfo,
        symbol_name: str,
    ) -> object | None:
        try:
            return cast("object | None", plugin(type_info, symbol_name))
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            logger.exception("Plugin %s failed", plugin.__name__)
            return None

    def register(self, name: str, plugin: DefaultValuePlugin) -> None:
        """Register a plugin function with a name.

        Args:
            name: Descriptive name for the plugin (e.g., 'ip_address', 'system_objects')
            plugin: Function that takes (type_info, symbol_name) and returns a value or None

        """
        if name in self._plugin_names:
            old_plugin = self._plugin_names[name]
            if old_plugin != plugin and old_plugin in self._plugins:
                self._plugins.remove(old_plugin)
            logger.warning("Plugin '%s' already registered, replacing", name)

        self._plugin_names[name] = plugin
        if plugin not in self._plugins:
            self._plugins.append(plugin)

        logger.debug("Registered default value plugin: %s", name)

    def get_default_value(self, type_info: TypeInfo, symbol_name: str) -> object | None:
        """Get default value by calling all registered plugins in order.

        Args:
            type_info: Dictionary with 'base_type', 'enums', 'constraints', etc.
            symbol_name: Name of the SNMP symbol (e.g., 'sysDescr', 'ifIndex')

        Returns:
            The first non-None value returned by any plugin, or None if no plugin handles it

        """
        for plugin in self._plugins:
            value = self._run_plugin(plugin, type_info, symbol_name)
            if value is not None:
                return value

        return None

    def list_plugins(self) -> list[str]:
        """Return list of registered plugin names."""
        return list(self._plugin_names.keys())


# Global registry instance
_registry = DefaultValuePluginRegistry()


def register_plugin(name: str) -> Callable[[DefaultValuePlugin], DefaultValuePlugin]:
    """Register a plugin function via decorator.

    Usage:
        @register_plugin('my_plugin')
        def my_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[object]:
            if type_info.get('base_type') == 'IpAddress':
                return '192.168.1.1'
            return None
    """

    def decorator(func: DefaultValuePlugin) -> DefaultValuePlugin:
        _registry.register(name, func)
        return func

    return decorator


def get_default_value(type_info: TypeInfo, symbol_name: str) -> object | None:
    """Get default value using registered plugins.

    This is the main entry point for the generator to get default values.
    """
    return _registry.get_default_value(type_info, symbol_name)


def get_registry() -> DefaultValuePluginRegistry:
    """Get the global plugin registry."""
    return _registry
