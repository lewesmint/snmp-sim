"""
Tests for the plugin_loader module.
"""

from pathlib import Path
import logging
from typing import Any
import pytest
from app.plugin_loader import load_plugins_from_directory, load_plugins


class TestPluginLoader:
    """Test the plugin loader functionality."""

    @staticmethod
    def _make_plugin_dir(tmp_path: Path, files: list[str] | None = None) -> Path:
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        for file_name in files or []:
            (plugin_dir / file_name).write_text("# test plugin")
        return plugin_dir

    @staticmethod
    def _setup_success_mocks(mocker: Any) -> tuple[Any, Any]:
        mock_module_from_spec = mocker.patch("importlib.util.module_from_spec")
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")

        mock_spec = mocker.MagicMock()
        mock_loader = mocker.MagicMock()
        mock_spec.loader = mock_loader
        mock_spec_from_file.return_value = mock_spec

        mock_module = mocker.MagicMock()
        mock_module_from_spec.return_value = mock_module
        return mock_spec_from_file, mock_loader

    def test_load_plugins_from_directory_nonexistent_dir(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test loading plugins from a nonexistent directory."""
        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory("nonexistent_dir")

        assert not result
        assert "Plugin directory 'nonexistent_dir' does not exist" in caplog.text

    def test_load_plugins_from_directory_not_a_dir(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test loading plugins from a path that's not a directory."""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("not a directory")

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(file_path))

        assert not result
        assert f"Plugin path '{file_path}' is not a directory" in caplog.text

    def test_load_plugins_from_directory_empty_dir(self, tmp_path: Path) -> None:
        """Test loading plugins from an empty directory."""
        plugin_dir = self._make_plugin_dir(tmp_path)

        result = load_plugins_from_directory(str(plugin_dir))
        assert not result

    def test_load_plugins_from_directory_with_underscore_files(self, tmp_path: Path) -> None:
        """Test that files starting with underscore are skipped."""
        plugin_dir = self._make_plugin_dir(tmp_path, ["__init__.py", "_private.py"])

        result = load_plugins_from_directory(str(plugin_dir))
        assert not result

    def test_load_plugins_from_directory_bad_spec(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of bad plugin spec."""
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = self._make_plugin_dir(tmp_path, ["test_plugin.py"])

        mock_spec_from_file.return_value = None

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(plugin_dir))

        assert not result
        assert "Could not load plugin spec" in caplog.text

    def test_load_plugins_from_directory_bad_loader(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of spec with no loader."""
        mock_spec_from_file = mocker.patch("importlib.util.spec_from_file_location")
        plugin_dir = self._make_plugin_dir(tmp_path, ["test_plugin.py"])

        mock_spec = mocker.MagicMock()
        mock_spec.loader = None
        mock_spec_from_file.return_value = mock_spec

        with caplog.at_level(logging.WARNING):
            result = load_plugins_from_directory(str(plugin_dir))

        assert not result
        assert "Could not load plugin spec" in caplog.text

    def test_load_plugins_from_directory_exec_error(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of execution errors during plugin loading."""
        plugin_dir = self._make_plugin_dir(tmp_path, ["test_plugin.py"])
        _, mock_loader = self._setup_success_mocks(mocker)

        # Make exec_module raise an exception
        mock_loader.exec_module.side_effect = Exception("Exec error")

        with caplog.at_level(logging.ERROR):
            result = load_plugins_from_directory(str(plugin_dir))

        assert not result
        assert "Failed to load plugin" in caplog.text
        assert "Exec error" in caplog.text

    def test_load_plugins_from_directory_success(
        self, mocker: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test successful plugin loading."""
        plugin_dir = self._make_plugin_dir(tmp_path, ["test_plugin.py"])
        self._setup_success_mocks(mocker)

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
        plugin_dir = self._make_plugin_dir(
            tmp_path,
            ["plugin_a.py", "plugin_b.py", "plugin_c.py"],
        )
        self._setup_success_mocks(mocker)

        result = load_plugins_from_directory(str(plugin_dir))

        # Should load plugins in sorted order
        expected = ["plugins.plugin_a", "plugins.plugin_b", "plugins.plugin_c"]
        assert result == expected
