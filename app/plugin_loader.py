"""Plugin loader for default value plugins.

This module discovers and loads plugin files from the plugins/ directory.
"""

import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def load_plugins_from_directory(plugin_dir: str = "plugins") -> list[str]:
    """Load all Python plugin files from the specified directory.

    Args:
        plugin_dir: Directory containing plugin .py files (default: "plugins")

    Returns:
        List of loaded plugin module names

    """
    plugin_path = Path(plugin_dir)

    if not plugin_path.exists():
        logger.warning("Plugin directory '%s' does not exist", plugin_dir)
        return []

    if not plugin_path.is_dir():
        logger.warning("Plugin path '%s' is not a directory", plugin_dir)
        return []

    loaded_plugins = []

    # Find all .py files in the plugin directory
    for plugin_file in sorted(plugin_path.glob("*.py")):
        if plugin_file.name.startswith("_"):
            # Skip files starting with underscore (like __init__.py)
            continue

        try:
            # Load the plugin module
            module_name = f"plugins.{plugin_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)

            if spec is None or spec.loader is None:
                logger.warning("Could not load plugin spec for %s", plugin_file)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            loaded_plugins.append(module_name)
            logger.info("Loaded plugin: %s", module_name)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            logger.exception("Failed to load plugin %s: %s", plugin_file, e)

    return loaded_plugins


def load_plugins() -> list[str]:
    """Load all plugins from the default plugins/ directory.

    Returns:
        List of loaded plugin module names

    """
    return load_plugins_from_directory("plugins")
