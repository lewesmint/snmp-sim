import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.app_config import AppConfig
from app.app_logger import AppLogger, LoggingConfig, ColoredFormatter
from app.behaviour_store import BehaviourStore
from app.mib_object import MibObject
from app.mib_registry import MibRegistry
from app.mib_table import MibTable
from app.snmp_transport import SNMPTransport
from app.type_registry_validator import validate_type_registry


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(api.app)


def test_api_get_sysdescr_without_agent(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "snmp_agent", None)
    response = api_client.get("/sysdescr")
    assert response.status_code == 500
    assert response.json()["detail"] == "SNMP agent not initialized"


def test_api_set_sysdescr_without_agent(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "snmp_agent", None)
    response = api_client.post("/sysdescr", json={"value": "test"})
    assert response.status_code == 500
    assert response.json()["detail"] == "SNMP agent not initialized"


def test_api_get_and_set_sysdescr_with_agent(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgent:
        def __init__(self) -> None:
            self.last_set: tuple[tuple[int, ...], Any] | None = None

        def get_scalar_value(self, oid: tuple[int, ...]) -> str:
            assert oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)
            return "sysdescr-value"

        def set_scalar_value(self, oid: tuple[int, ...], value: Any) -> None:
            self.last_set = (oid, value)

    fake_agent = FakeAgent()
    monkeypatch.setattr(api, "snmp_agent", fake_agent)

    get_response = api_client.get("/sysdescr")
    assert get_response.status_code == 200
    assert get_response.json() == {
        "oid": [1, 3, 6, 1, 2, 1, 1, 1, 0],
        "value": "sysdescr-value",
    }

    post_response = api_client.post("/sysdescr", json={"value": "new-value"})
    assert post_response.status_code == 200
    assert post_response.json() == {
        "status": "ok",
        "oid": [1, 3, 6, 1, 2, 1, 1, 1, 0],
        "new_value": "new-value",
    }
    assert fake_agent.last_set == ((1, 3, 6, 1, 2, 1, 1, 1, 0), "new-value")


def test_behaviour_store_get_set() -> None:
    store = BehaviourStore()
    assert store.get("1.2.3") is None
    store.set("1.2.3", "value")
    store.load("/tmp/behaviour.json")
    store.save("/tmp/behaviour.json")
    assert store.get("1.2.3") == "value"


def test_mib_object_get_set() -> None:
    obj = MibObject("1.2.3", {"syntax": "Integer"}, value=10)
    assert obj.get_value() == 10
    obj.set_value(42)
    assert obj.get_value() == 42


def test_mib_table_add_row() -> None:
    table = MibTable("1.2.3", [])
    table.add_row(["row1", 1])
    table.add_row(["row2", 2])
    assert table.get_rows() == [["row1", 1], ["row2", 2]]


def test_mib_registry_get_type_default() -> None:
    registry = MibRegistry()
    registry.load_from_json("/tmp/types.json")
    assert registry.get_type("1.2.3") == {}
    registry.types["1.2.3"] = {"name": "sysDescr"}
    assert registry.get_type("1.2.3") == {"name": "sysDescr"}


def test_snmp_transport_start_stop_noop() -> None:
    transport = SNMPTransport()
    transport.start()
    transport.stop()


def _reset_app_config_singleton() -> None:
    AppConfig._instance = None


def test_app_config_reads_values(tmp_path: Path) -> None:
        _reset_app_config_singleton()
        try:
                config_dir = tmp_path / "cfg"
                config_dir.mkdir()
                config_path = config_dir / "test_config.yaml"
                config_path.write_text(
                        """
logger:
    level: INFO
simple_key: simple_value
system_mib_dir:
    darwin: /opt/test/mibs
    linux: /usr/share/snmp/mibs
""".strip()
                )

                config = AppConfig(config_path=str(config_path))
                assert config.get("simple_key") == "simple_value"
                platform_value = config.get_platform_setting("system_mib_dir")
                if sys.platform == "darwin":
                        assert platform_value == "/opt/test/mibs"
                else:
                        assert platform_value in {"/usr/share/snmp/mibs", None}
                assert config.get_platform_setting("simple_key", "default") == "default"
                config.reload()
        finally:
                _reset_app_config_singleton()


def test_app_config_missing_file() -> None:
    _reset_app_config_singleton()
    try:
        with pytest.raises(FileNotFoundError):
            AppConfig(config_path="/tmp/does-not-exist.yaml")
    finally:
        _reset_app_config_singleton()


def test_app_logger_configures_handlers(tmp_path: Path) -> None:
    AppLogger._configured = False
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    config = LoggingConfig(level="INFO", log_dir=log_dir, console=True)

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    try:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        AppLogger(config)
        root.info("test log")
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
        assert any(isinstance(h.formatter, ColoredFormatter) for h in root.handlers)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in old_handlers:
            root.addHandler(handler)


def test_app_logger_no_console(tmp_path: Path) -> None:
    AppLogger._configured = False
    log_dir = tmp_path / "logs-no-console"
    log_dir.mkdir()
    config = LoggingConfig(level="INFO", log_dir=log_dir, console=False)

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    try:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        AppLogger(config)
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
        assert not any(isinstance(h.formatter, ColoredFormatter) for h in root.handlers)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in old_handlers:
            root.addHandler(handler)


def test_app_logger_static_methods(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        AppLogger.info("info-msg")
        AppLogger.warning("warn-msg")
        AppLogger.error("error-msg")
    assert "info-msg" in caplog.text
    assert "warn-msg" in caplog.text
    assert "error-msg" in caplog.text


def test_app_logger_configured_short_circuit(tmp_path: Path) -> None:
    AppLogger._configured = True
    log_dir = tmp_path / "logs-short"
    log_dir.mkdir()
    config = LoggingConfig(level="INFO", log_dir=log_dir, console=True)
    AppLogger(config)
    AppLogger._configured = False


def test_colored_formatter_changes_levelname() -> None:
    formatter = ColoredFormatter(fmt="%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    original = record.levelname
    formatted = formatter.format(record)
    assert "hello" in formatted
    assert record.levelname == original


def test_validate_type_registry_ok(capsys: pytest.CaptureFixture[str]) -> None:
    registry = {
        "1.2.3": {
            "name": "sysDescr",
            "syntax": "DisplayString",
            "description": "System description",
        }
    }
    validate_type_registry(registry)
    output = capsys.readouterr()
    assert "Type registry validation passed." in output.out


def test_validate_type_registry_missing_fields(capsys: pytest.CaptureFixture[str]) -> None:
    registry = {
        "1.2.3": {
            "name": 123,
            "syntax": 123,
        }
    }
    with pytest.raises(SystemExit) as excinfo:
        validate_type_registry(registry)
    assert excinfo.value.code == 1
    output = capsys.readouterr()
    assert "Validation errors found" in output.out
    assert "missing fields" in output.out
    assert "'name' must be a string" in output.out
    assert "'description' must be a string" in output.out
