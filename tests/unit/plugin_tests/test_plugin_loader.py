"""
Tests for the plugin_loader module.
"""

import pytest
from pathlib import Path
import logging
from typing import Any
from app.plugin_loader import load_plugins_from_directory, load_plugins


class TestPluginLoader:
    """Test the plugin loader functionality."""

    def test_load_plugins_from_directory_nonexistent_dir(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test loading plugins from a nonexistent directory."""
        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory("nonexistent_dir")

        assert result == []
        assert "Plugin directory 'nonexistent_dir' does not exist" in caplog.text

    def test_load_plugins_from_directory_not_a_dir(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test loading plugins from a path that's not a directory."""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("not a directory")

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(file_path))

        assert result == []
        assert f"Plugin path '{file_path}' is not a directory" in caplog.text

    def test_load_plugins_from_directory_empty_dir(self, tmp_path: Path) -> None:
        """Test loading plugins from an empty directory."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        result = load_plugins_from_directory(str(plugin_dir))
        assert result == []

    def test_load_plugins_from_directory_with_underscore_files(
        self, tmp_path: Path
    ) -> None:
        """Test that files starting with underscore are skipped."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        # Create files that should be skipped
        (plugin_dir / "__init__.py").write_text("# init file")
        (plugin_dir / "_private.py").write_text("# private plugin")

        result = load_plugins_from_directory(str(plugin_dir))
        assert result == []

    def test_load_plugins_from_directory_bad_spec(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of bad plugin spec."""
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text("# test plugin")

        mock_spec_from_file.return_value = None

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(plugin_dir))

        assert result == []
        assert "Could not load plugin spec" in caplog.text

    def test_load_plugins_from_directory_bad_loader(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of spec with no loader."""
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text("# test plugin")

        mock_spec = mocker.MagicMock()
        mock_spec.loader = None
        mock_spec_from_file.return_value = mock_spec

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(plugin_dir))

        assert result == []
        assert "Could not load plugin spec" in caplog.text

    def test_load_plugins_from_directory_exec_error(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of execution errors during plugin loading."""
        mock_module_from_spec = mocker.patch("importlib.util.module_from_spec")
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text("# test plugin")

        mock_spec = mocker.MagicMock()
        mock_loader = mocker.MagicMock()
        mock_spec.loader = mock_loader
        mock_spec_from_file.return_value = mock_spec

        mock_module = mocker.MagicMock()
        mock_module_from_spec.return_value = mock_module

        # Make exec_module raise an exception
        mock_loader.exec_module.side_effect = Exception("Exec error")

        with caplog.at_level(logging.ERROR):
            result = load_plugins_from_directory(str(plugin_dir))

        assert result == []
        assert "Failed to load plugin" in caplog.text
        assert "Exec error" in caplog.text

    def test_load_plugins_from_directory_success(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test successful plugin loading."""
        mock_module_from_spec = mocker.patch("importlib.util.module_from_spec")
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text("# test plugin")

        mock_spec = mocker.MagicMock()
        mock_loader = mocker.MagicMock()
        mock_spec.loader = mock_loader
        mock_spec_from_file.return_value = mock_spec

        mock_module = mocker.MagicMock()
        mock_module_from_spec.return_value = mock_module

        with caplog.at_level(logging.INFO):
            result = load_plugins_from_directory(str(plugin_dir))

        assert result == ["plugins.test_plugin"]
        assert "Loaded plugin: plugins.test_plugin" in caplog.text

    def test_load_plugins_calls_load_plugins_from_directory(self, mocker: Any) -> None:
        """Test that load_plugins calls load_plugins_from_directory with 'plugins'."""
        mock_load = mocker.patch("app.plugin_loader.load_plugins_from_directory")
        mock_load.return_value = ["plugins.test"]
        result = load_plugins()

        mock_load.assert_called_once_with("plugins")
        assert result == ["plugins.test"]

    def test_load_plugins_from_directory_multiple_plugins(
        self, mocker: Any, tmp_path: Path
    ) -> None:
        """Test loading multiple plugins."""
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        mock_module_from_spec = mocker.patch("importlib.util.module_from_spec")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        # Create multiple plugin files
        (plugin_dir / "plugin_a.py").write_text("# plugin a")
        (plugin_dir / "plugin_b.py").write_text("# plugin b")
        (plugin_dir / "plugin_c.py").write_text("# plugin c")

        # Set up mocks for successful loading
        mock_spec = mocker.MagicMock()
        mock_loader = mocker.MagicMock()
        mock_spec.loader = mock_loader
        mock_spec_from_file.return_value = mock_spec

        mock_module = mocker.MagicMock()
        mock_module_from_spec.return_value = mock_module

        result = load_plugins_from_directory(str(plugin_dir))

        # Should load plugins in sorted order
        expected = ["plugins.plugin_a", "plugins.plugin_b", "plugins.plugin_c"]
        assert result == expected
