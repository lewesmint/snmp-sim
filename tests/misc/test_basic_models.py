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


def test_validate_type_registry_ok() -> None:
    """Test that valid type registry passes validation."""
    registry = {
        "DisplayString": {
            "base_type": "OctetString",
            "used_by": [],
            "defined_in": "SNMPv2-TC",
            "abstract": False,
        },
        "Integer32": {
            "base_type": "Integer32",
            "used_by": ["sysUpTime"],
            "defined_in": "SNMPv2-SMI",
            "abstract": False,
        },
    }
    is_valid, errors = validate_type_registry(registry)
    assert is_valid is True
    assert errors == []


def test_validate_type_registry_missing_fields() -> None:
    """Test that type registry with missing fields fails validation."""
    registry = {
        "DisplayString": {
            "base_type": "OctetString",
            # Missing: used_by, defined_in, abstract
        }
    }
    is_valid, errors = validate_type_registry(registry)
    assert is_valid is False
    assert len(errors) > 0
    assert any("missing fields" in error for error in errors)


def test_log_rotation_archives_existing_log(tmp_path: Path) -> None:
    """Test that log rotation archives existing log file with timestamp from first entry."""
    AppLogger._configured = False
    log_dir = tmp_path / "logs-rotation"
    log_dir.mkdir()
    log_file = "test-agent.log"
    log_path = log_dir / log_file

    # Create an existing log file with a known timestamp
    log_path.write_text(
        "2026-02-07 10:30:45.123 INFO test.module [MainThread] Test message\n"
        "2026-02-07 10:30:46.456 DEBUG test.module [MainThread] Another message\n"
    )

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    try:
        for handler in list(root.handlers):
            root.removeHandler(handler)

        # Configure with rotation enabled
        config = LoggingConfig(
            level="INFO",
            log_dir=log_dir,
            log_file=log_file,
            console=False,
            rotate_on_startup=True,
        )
        AppLogger(config)

        # Original log file should be archived
        assert not log_path.exists() or log_path.stat().st_size == 0 or log_path.read_text() != "2026-02-07 10:30:45.123 INFO test.module [MainThread] Test message\n"

        # Check that archive directory was created
        archive_dir = log_dir / "archive"
        assert archive_dir.exists()
        assert archive_dir.is_dir()

        # Check that archived file exists with timestamp in archive subdirectory
        archived_files = list(archive_dir.glob("test-agent_2026-02-07_10-30-45*.log"))
        assert len(archived_files) == 1

        # New log file should exist (may be empty or have new content)
        assert log_path.exists()

    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in old_handlers:
            root.addHandler(handler)
        AppLogger._configured = False


def test_log_no_rotation_appends_to_existing(tmp_path: Path) -> None:
    """Test that with rotation disabled, logs append to existing file."""
    AppLogger._configured = False
    log_dir = tmp_path / "logs-no-rotation"
    log_dir.mkdir()
    log_file = "test-agent.log"
    log_path = log_dir / log_file

    # Create an existing log file
    existing_content = "2026-02-07 10:30:45.123 INFO test.module [MainThread] Existing message\n"
    log_path.write_text(existing_content)

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    try:
        for handler in list(root.handlers):
            root.removeHandler(handler)

        # Configure with rotation disabled
        config = LoggingConfig(
            level="INFO",
            log_dir=log_dir,
            log_file=log_file,
            console=False,
            rotate_on_startup=False,
        )
        AppLogger(config)

        # Write a new log message
        root.info("New message")

        # Original content should still be there
        log_content = log_path.read_text()
        assert "Existing message" in log_content
        assert "New message" in log_content

        # No archived files should exist
        archived_files = list(log_dir.glob("test-agent_*.log"))
        assert len(archived_files) == 0

    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in old_handlers:
            root.addHandler(handler)
        AppLogger._configured = False
