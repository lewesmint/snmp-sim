"""
Tests for the default value plugin system.
"""

import pytest
from typing import Any, Optional

from app.default_value_plugins import (
    DefaultValuePluginRegistry,
    register_plugin,
    get_default_value,
    get_registry,
)
from app.types import TypeInfo


class TestDefaultValuePluginRegistry:
    """Test the DefaultValuePluginRegistry class."""

    def test_register_and_list_plugins(self) -> None:
        """Test registering plugins and listing them."""
        registry = DefaultValuePluginRegistry()

        def dummy_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            return None

        registry.register("test_plugin", dummy_plugin)
        assert "test_plugin" in registry.list_plugins()
        assert len(registry.list_plugins()) == 1

    def test_register_duplicate_plugin_replaces(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that registering a plugin with the same name replaces the old one."""
        registry = DefaultValuePluginRegistry()

        def plugin1(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            return "value1"

        def plugin2(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            return "value2"

        registry.register("test_plugin", plugin1)
        assert registry.get_default_value({}, "test") == "value1"

        with caplog.at_level("WARNING"):
            registry.register("test_plugin", plugin2)

        assert "Plugin 'test_plugin' already registered, replacing" in caplog.text
        assert registry.get_default_value({}, "test") == "value2"
        assert len(registry.list_plugins()) == 1

    def test_get_default_value_no_plugins(self) -> None:
        """Test get_default_value returns None when no plugins are registered."""
        registry = DefaultValuePluginRegistry()
        result = registry.get_default_value({"base_type": "Integer32"}, "sysDescr")
        assert result is None

    def test_get_default_value_with_plugins(self) -> None:
        """Test get_default_value calls plugins in order and returns first non-None value."""
        registry = DefaultValuePluginRegistry()

        def plugin1(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            if type_info.get("base_type") == "IpAddress":
                return "192.168.1.1"
            return None

        def plugin2(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            if symbol_name == "sysDescr":
                return "Test Description"
            return None

        registry.register("ip_plugin", plugin1)
        registry.register("sys_plugin", plugin2)

        # Test plugin1 matches
        result = registry.get_default_value({"base_type": "IpAddress"}, "ifIndex")
        assert result == "192.168.1.1"

        # Test plugin2 matches when plugin1 doesn't
        result = registry.get_default_value({"base_type": "OctetString"}, "sysDescr")
        assert result == "Test Description"

        # Test no match
        result = registry.get_default_value({"base_type": "Integer32"}, "unknown")
        assert result is None

    def test_get_default_value_plugin_exception_handled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that plugin exceptions are caught and logged, allowing other plugins to run."""
        registry = DefaultValuePluginRegistry()

        def failing_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            raise ValueError("Plugin failed")

        def working_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
            return "success"

        registry.register("failing", failing_plugin)
        registry.register("working", working_plugin)

        with caplog.at_level("ERROR"):
            result = registry.get_default_value({}, "test")

        assert result == "success"
        assert "Plugin failing_plugin failed: Plugin failed" in caplog.text


class TestGlobalFunctions:
    """Test the global functions and decorator."""

    def test_register_plugin_decorator(self) -> None:
        """Test the register_plugin decorator."""
        # Create a fresh registry for this test to avoid interference
        from app.default_value_plugins import _registry

        original_plugins = _registry._plugins.copy()
        original_names = _registry._plugin_names.copy()

        # Clear the global registry
        _registry._plugins.clear()
        _registry._plugin_names.clear()

        try:

            @register_plugin("decorated_plugin")
            def my_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
                if type_info.get("base_type") == "Counter32":
                    return 42
                return None

            assert "decorated_plugin" in _registry.list_plugins()
            result = get_default_value({"base_type": "Counter32"}, "test")
            assert result == 42

            # Test that it returns None for non-matching types
            result = get_default_value({"base_type": "Integer32"}, "test")
            assert result is None
        finally:
            # Restore the original registry
            _registry._plugins = original_plugins
            _registry._plugin_names = original_names

    def test_get_default_value_global_function(self) -> None:
        """Test the global get_default_value function."""
        # Clear any existing plugins for clean test
        registry = get_registry()
        original_plugins = registry._plugins.copy()
        registry._plugins.clear()
        registry._plugin_names.clear()

        try:

            def test_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
                return "global_test"

            registry.register("global_test", test_plugin)

            result = get_default_value({"base_type": "Test"}, "test_symbol")
            assert result == "global_test"
        finally:
            # Restore original plugins
            registry._plugins = original_plugins
            registry._plugin_names = {
                name: plugin
                for name, plugin in zip(registry.list_plugins(), original_plugins)
            }

    def test_get_registry_returns_global_instance(self) -> None:
        """Test that get_registry returns the global registry instance."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2
        assert isinstance(registry1, DefaultValuePluginRegistry)
