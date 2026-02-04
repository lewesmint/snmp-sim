"""
Plugin loader for default value plugins.

This module discovers and loads plugin files from the plugins/ directory.
"""
import importlib.util
import sys
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


def load_plugins_from_directory(plugin_dir: str = "plugins") -> List[str]:
    """Load all Python plugin files from the specified directory.
    
    Args:
        plugin_dir: Directory containing plugin .py files (default: "plugins")
    
    Returns:
        List of loaded plugin module names
    """
    plugin_path = Path(plugin_dir)
    
    if not plugin_path.exists():
        logger.warning(f"Plugin directory '{plugin_dir}' does not exist")
        return []
    
    if not plugin_path.is_dir():
        logger.warning(f"Plugin path '{plugin_dir}' is not a directory")
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
                logger.warning(f"Could not load plugin spec for {plugin_file}")
                continue
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            loaded_plugins.append(module_name)
            logger.info(f"Loaded plugin: {module_name}")
            
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_file}: {e}", exc_info=True)
    
    return loaded_plugins


def load_plugins() -> List[str]:
    """Load all plugins from the default plugins/ directory.
    
    Returns:
        List of loaded plugin module names
    """
    return load_plugins_from_directory("plugins")

