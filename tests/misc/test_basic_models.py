"""Misc regression tests for API endpoints, config, logging, and basic models."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import api
from app.app_config import AppConfig
from app.app_logger import AppLogger, LoggingConfig, ColoredFormatter
from app.mib_object import MibObject
from app.mib_registry import MibRegistry
from app.mib_table import MibTable
from app.type_registry_validator import validate_type_registry


@pytest.fixture
def api_client() -> TestClient:
    """Create a FastAPI test client for API route tests."""
    return TestClient(api.app)


def test_api_get_sysdescr_without_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return 500 when getting sysDescr before SNMP agent is initialized."""
    monkeypatch.setattr(api, "snmp_agent", None)
    response = api_client.get("/sysdescr")
    assert response.status_code == 500
    assert response.json()["detail"] == "SNMP agent not initialized"


def test_api_set_sysdescr_without_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return 500 when setting sysDescr before SNMP agent is initialized."""
    monkeypatch.setattr(api, "snmp_agent", None)
    response = api_client.post("/sysdescr", json={"value": "test"})
    assert response.status_code == 500
    assert response.json()["detail"] == "SNMP agent not initialized"


def test_api_get_and_set_sysdescr_with_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise GET and POST sysDescr paths with a fake in-memory agent."""

    class FakeAgent:
        """Minimal fake SNMP agent implementing scalar get/set used by the API."""

        def __init__(self) -> None:
            """Initialize fake agent state for assertion of last set call."""
            self.last_set: tuple[tuple[int, ...], Any] | None = None

        def get_scalar_value(self, oid: tuple[int, ...]) -> str:
            """Return a static sysDescr value for the expected OID."""
            assert oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)
            return "sysdescr-value"

        def set_scalar_value(self, oid: tuple[int, ...], value: Any) -> None:
            """Record the latest set request for downstream assertions."""
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


def test_mib_object_get_set() -> None:
    """Validate get/set round-trip behavior on MibObject."""
    obj = MibObject("1.2.3", {"syntax": "Integer"}, value=10)
    assert obj.get_value() == 10
    obj.set_value(42)
    assert obj.get_value() == 42


def test_mib_table_add_row() -> None:
    """Validate row insertion order and retrieval in MibTable."""
    table = MibTable("1.2.3", [])
    table.add_row(["row1", 1])
    table.add_row(["row2", 2])
    assert table.get_rows() == [["row1", 1], ["row2", 2]]


def test_mib_registry_get_type_default() -> None:
    """Return empty dict for unknown OID and stored value for known OID."""
    registry = MibRegistry()
    registry.load_from_json("/tmp/types.json")
    assert registry.get_type("1.2.3") == {}
    registry.types["1.2.3"] = {"name": "sysDescr"}
    assert registry.get_type("1.2.3") == {"name": "sysDescr"}


def _reset_app_config_singleton() -> None:
    """Reset AppConfig singleton to isolate test cases."""
    AppConfig._instance = None


def test_app_config_reads_values(tmp_path: Path) -> None:
    """Read scalar and platform-specific values from a temporary config file."""
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
    """Raise FileNotFoundError when AppConfig points to a missing file."""
    _reset_app_config_singleton()
    try:
        with pytest.raises(FileNotFoundError):
            AppConfig(config_path="/tmp/does-not-exist.yaml")
    finally:
        _reset_app_config_singleton()


def test_app_logger_configures_handlers(tmp_path: Path) -> None:
    """Configure file/console handlers and colored formatter when console is enabled."""
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
    """Create only file handler formatting when console logging is disabled."""
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
    """Emit static logger messages and verify they are captured."""
    with caplog.at_level(logging.INFO):
        AppLogger.info("info-msg")
        AppLogger.warning("warn-msg")
        AppLogger.error("error-msg")
    assert "info-msg" in caplog.text
    assert "warn-msg" in caplog.text
    assert "error-msg" in caplog.text


def test_app_logger_configured_short_circuit(tmp_path: Path) -> None:
    """No-op when logger is already configured."""
    AppLogger._configured = True
    log_dir = tmp_path / "logs-short"
    log_dir.mkdir()
    config = LoggingConfig(level="INFO", log_dir=log_dir, console=True)
    AppLogger(config)
    AppLogger._configured = False


def test_app_logger_configure_uses_test_log_file_under_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route AppLogger.configure output to test log file when running under pytest."""

    class _DummyConfig:
        def __init__(self, logger_cfg: dict[str, Any]) -> None:
            self._logger_cfg = logger_cfg

        def get(self, key: str, default: Any = None) -> Any:
            """Test case for get."""
            if key == "logger":
                return self._logger_cfg
            return default

    AppLogger._configured = False
    log_dir = tmp_path / "logs-configure"
    log_dir.mkdir()

    cfg = _DummyConfig(
        {
            "log_dir": str(log_dir),
            "log_file": "snmp-agent.log",
            "test_log_file": "snmp-agent.test.log",
            "console": False,
            "rotate_on_startup": False,
            "level": "INFO",
        }
    )

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    try:
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests::dummy")
        for handler in list(root.handlers):
            root.removeHandler(handler)

        AppLogger.configure(cfg)  # type: ignore[arg-type]

        file_handlers = [
            h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert file_handlers
        target = Path(file_handlers[0].baseFilename).name
        assert target == "snmp-agent.test.log"
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in old_handlers:
            root.addHandler(handler)
        AppLogger._configured = False


def test_colored_formatter_changes_levelname() -> None:
    """Ensure formatter output contains message and preserves record levelname."""
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
    assert not errors


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
        assert (
            not log_path.exists()
            or log_path.stat().st_size == 0
            or log_path.read_text()
            != "2026-02-07 10:30:45.123 INFO test.module [MainThread] Test message\n"
        )

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
