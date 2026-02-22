import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from app.default_value_plugins import (
    DefaultValuePluginRegistry,
    get_registry,
    get_default_value,
)
import importlib.util

from app.plugin_loader import load_plugins_from_directory
from app.snmp_type_initializer import SNMPTypeInitializer, _init_ipaddress
from app.type_registry import TypeRegistry


class _FakeMibBuilder:
    def __init__(self, symbols: dict[tuple[str, str], Any] | None = None) -> None:
        self._symbols = symbols or {}

    def import_symbols(self, mib_name: str, symbol_name: str) -> list[Any]:
        key = (mib_name, symbol_name)
        if key in self._symbols:
            return [self._symbols[key]]
        raise Exception("not found")


def test_default_value_registry_gets_first_non_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = DefaultValuePluginRegistry()

    def bad_plugin(_type_info: dict[str, Any], _symbol_name: str) -> Any:
        raise RuntimeError("boom")

    def good_plugin(_type_info: dict[str, Any], _symbol_name: str) -> Any:
        return "value"

    registry.register("bad", bad_plugin)
    registry.register("good", good_plugin)

    with caplog.at_level(logging.ERROR):
        value = registry.get_default_value({}, "sysDescr")

    assert value == "value"
    assert "failed" in caplog.text
    assert "bad" in registry.list_plugins()
    assert "good" in registry.list_plugins()


def test_default_value_registry_duplicate_and_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = DefaultValuePluginRegistry()

    def none_plugin(_type_info: dict[str, Any], _symbol_name: str) -> Any:
        return None

    registry.register("dup", none_plugin)
    with caplog.at_level(logging.WARNING):
        registry.register("dup", none_plugin)

    assert registry.get_default_value({}, "sysDescr") is None
    assert "already registered" in caplog.text


def test_default_value_module_level_get() -> None:
    assert get_default_value({}, "sysDescr") is None


def test_load_plugins_from_directory(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "test_plugin.py"
    plugin_file.write_text("""
from app.default_value_plugins import register_plugin

@register_plugin('test_plugin')
def _plugin(type_info, symbol_name):
    if symbol_name == 'sysDescr':
        return 'plugin-value'
    return None
""".strip())

    loaded = load_plugins_from_directory(str(plugin_dir))
    assert "plugins.test_plugin" in loaded

    registry = get_registry()
    assert registry.get_default_value({}, "sysDescr") == "plugin-value"

    module_name = "plugins.test_plugin"
    if module_name in sys.modules:
        del sys.modules[module_name]


def test_load_plugins_from_directory_bad_spec(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "bad_spec.py"
    plugin_file.write_text("x = 1")

    monkeypatch.setattr(
        importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None
    )

    with caplog.at_level(logging.WARNING):
        loaded = load_plugins_from_directory(str(plugin_dir))
    assert loaded == []
    assert "Could not load plugin spec" in caplog.text


def test_load_plugins_from_directory_exec_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "boom.py"
    plugin_file.write_text("raise RuntimeError('boom')")

    with caplog.at_level(logging.ERROR):
        loaded = load_plugins_from_directory(str(plugin_dir))
    assert loaded == []
    assert "Failed to load plugin" in caplog.text


def test_load_plugins_from_directory_missing_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing_dir = tmp_path / "does_not_exist"
    with caplog.at_level(logging.WARNING):
        loaded = load_plugins_from_directory(str(missing_dir))
    assert loaded == []
    assert "does not exist" in caplog.text


def test_load_plugins_from_directory_not_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("noop")
    with caplog.at_level(logging.WARNING):
        loaded = load_plugins_from_directory(str(file_path))
    assert loaded == []
    assert "is not a directory" in caplog.text


def test_type_registry_build_and_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeRecorder:
        def __init__(self, _path: Path) -> None:
            self.registry = {"1.2.3": {"name": "sysDescr"}}
            self.built = False

        def build(self) -> None:
            self.built = True

    monkeypatch.setattr("app.type_registry.TypeRecorder", FakeRecorder)

    registry = TypeRegistry(tmp_path)
    registry.build()
    assert registry.registry == {"1.2.3": {"name": "sysDescr"}}

    output_path = tmp_path / "types.json"
    registry.export_to_json(str(output_path))
    assert output_path.exists()


def test_type_registry_registry_requires_build() -> None:
    registry = TypeRegistry()
    with pytest.raises(RuntimeError):
        _ = registry.registry


def test_type_registry_export_requires_build(tmp_path: Path) -> None:
    registry = TypeRegistry(tmp_path)
    with pytest.raises(RuntimeError):
        registry.export_to_json(str(tmp_path / "types.json"))


def test_snmp_type_initializer_default_and_custom() -> None:
    mib_builder = _FakeMibBuilder({("SNMPv2-SMI", "Integer32"): int})
    initializer = SNMPTypeInitializer(mib_builder, {})

    col_info = {"type": "Integer32"}
    assert initializer.initialize(col_info) == 0

    def custom_init(
        _col_info: dict[str, Any], _initializer: SNMPTypeInitializer
    ) -> Any:
        return "custom"

    SNMPTypeInitializer.register_initializer("CustomType", custom_init)
    custom_value = initializer.initialize({"type": "CustomType"})
    assert custom_value == "custom"


def test_snmp_type_initializer_get_type_class_sources() -> None:
    mib_builder = _FakeMibBuilder({("SNMPv2-SMI", "OctetString"): str})
    initializer = SNMPTypeInitializer(mib_builder, {})
    assert initializer.get_type_class("OctetString") is str

    mib_builder_tc = _FakeMibBuilder({("SNMPv2-TC", "DisplayString"): str})
    initializer_tc = SNMPTypeInitializer(mib_builder_tc, {})
    assert initializer_tc.get_type_class("DisplayString") is str

    mib_builder_none = _FakeMibBuilder()
    initializer_none = SNMPTypeInitializer(mib_builder_none, {})
    assert initializer_none.get_type_class("Integer32") is not None
    assert initializer_none.get_type_class("NonexistentType") is None
    assert initializer_none.get_type_class("") is None


def test_snmp_type_initializer_get_type_class_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mib_builder = _FakeMibBuilder()
    initializer = SNMPTypeInitializer(mib_builder, {})

    original_import = __import__

    def fake_import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: tuple[str, ...] | list[str] = (),
        level: int = 0,
    ) -> Any:
        if name == "pysnmp.proto":
            raise ImportError("boom")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert initializer.get_type_class("Integer32") is None


def test_snmp_type_initializer_default_values_for_enums() -> None:
    initializer = SNMPTypeInitializer(_FakeMibBuilder(), {})
    type_info = {"enums": [{"value": 7}, {"value": 9}]}
    assert initializer.get_default_value("EnumType", type_info) == 7
    assert initializer.get_default_value("EnumType", {"enums": []}) == 0
    assert initializer.get_default_value("EnumType", {"enums": "bad"}) == 0
    assert initializer.get_default_value("OctetString", {}) == ""
    assert initializer.get_default_value("ObjectIdentifier", {}) == "0.0"


def test_init_ipaddress_helper() -> None:
    mib_builder = _FakeMibBuilder({("SNMPv2-SMI", "IpAddress"): str})
    initializer = SNMPTypeInitializer(mib_builder, {})
    assert _init_ipaddress({"initial": "1.2.3.4"}, initializer) == "1.2.3.4"

    initializer_no_class = SNMPTypeInitializer(_FakeMibBuilder(), {})
    initializer_no_class.get_type_class = lambda _name: None  # type: ignore[assignment]
    assert _init_ipaddress({}, initializer_no_class) == "0.0.0.0"


def test_snmp_type_initializer_error_paths() -> None:
    mib_builder = _FakeMibBuilder()
    logger = logging.getLogger("test")
    initializer = SNMPTypeInitializer(mib_builder, {}, logger=logger)

    def failing_initializer(
        _col_info: dict[str, Any], _initializer: SNMPTypeInitializer
    ) -> Any:
        raise RuntimeError("boom")

    SNMPTypeInitializer.register_initializer("FailType", failing_initializer)
    with pytest.raises(RuntimeError):
        initializer.initialize({"type": "FailType"})

    class BadType:
        def __call__(self, _value: Any) -> Any:
            raise ValueError("boom")

    initializer.get_type_class = lambda _name: BadType()  # type: ignore[assignment]
    value = initializer.initialize({"type": "Integer32", "initial": 5})
    assert value == 5

    initializer.get_type_class = lambda _name: BadType()  # type: ignore[assignment]
    value = initializer.initialize({"type": "UnknownType"})
    assert value == 0

    initializer.get_type_class = lambda _name: None  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        initializer.initialize({"type": "AnotherUnknown"})
