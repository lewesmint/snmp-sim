"""Tests for test ui common."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ui.common import Logger, format_snmp_value, safe_call, save_gui_log


class FakeTextWidget:
    """Test helper class for FakeTextWidget."""

    def __init__(self) -> None:
        self.tags: dict[str, dict[str, Any]] = {}
        self.state: str | None = None
        self.entries: list[tuple[str, str]] = []
        self._text = ""

    def tag_config(self, tag: str, **kwargs: Any) -> None:
        """Test case for tag_config."""
        self.tags[tag] = kwargs

    def configure(self, **kwargs: Any) -> None:
        """Test case for configure."""
        if "state" in kwargs:
            self.state = kwargs["state"]

    def insert(self, _index: str, text: str, tag: str) -> None:
        """Test case for insert."""
        self.entries.append((tag, text))
        self._text += text

    def see(self, _index: str) -> None:
        """Test case for see."""
        return None

    def get(self, _start: str, _end: str) -> str:
        """Test case for get."""
        return self._text


class BrokenTextWidget(FakeTextWidget):
    """Test helper class for BrokenTextWidget."""

    def insert(self, _index: str, text: str, tag: str) -> None:
        raise RuntimeError("insert failed")


def test_logger_configure_and_log_with_widget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test case for test_logger_configure_and_log_with_widget."""
    widget = FakeTextWidget()
    logger = Logger(widget)

    logger.log("hello world", "WARNING")
    out = capsys.readouterr().out

    assert "WARNING: hello world" in out
    assert logger._tags_configured is True
    assert "WARNING" in widget.tags
    assert widget.entries
    assert widget.state == "disabled"


def test_logger_log_handles_widget_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """Test case for test_logger_log_handles_widget_errors."""
    logger = Logger(BrokenTextWidget())
    logger.log("should still print", "ERROR")
    out = capsys.readouterr().out
    assert "ERROR: should still print" in out


def test_logger_set_log_widget_resets_tags() -> None:
    """Test case for test_logger_set_log_widget_resets_tags."""
    logger = Logger(FakeTextWidget())
    logger._tags_configured = True
    logger.set_log_widget(FakeTextWidget())
    assert logger._tags_configured is False


def test_save_gui_log_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test case for test_save_gui_log_creates_file."""
    monkeypatch.chdir(tmp_path)
    widget = FakeTextWidget()
    widget.insert("end", "line1\n", "INFO")

    save_gui_log(widget, "test.log")

    log_file = tmp_path / "logs" / "test.log"
    assert log_file.exists()
    assert "line1" in log_file.read_text(encoding="utf-8")


def test_save_gui_log_handles_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test case for test_save_gui_log_handles_exceptions."""
    monkeypatch.chdir(tmp_path)

    class BrokenGetWidget(FakeTextWidget):
        """Test helper class for BrokenGetWidget."""

        def get(self, _start: str, _end: str) -> str:
            raise RuntimeError("get failed")

    save_gui_log(BrokenGetWidget(), "test.log")
    out = capsys.readouterr().out
    # No crash and outer function handles any errors gracefully
    assert "Error saving log" not in out


def test_format_snmp_value_paths() -> None:
    """Test case for test_format_snmp_value_paths."""

    class WithPretty:
        """Test helper class for WithPretty."""

        def prettyPrint(self) -> str:
            """Test case for prettyPrint."""
            return "pretty"

    class BadPretty:
        """Test helper class for BadPretty."""

        def prettyPrint(self) -> str:
            """Test case for prettyPrint."""
            raise RuntimeError("boom")

        def __str__(self) -> str:
            return "fallback"

    assert format_snmp_value(WithPretty()) == "pretty"
    assert format_snmp_value(BadPretty()) == "fallback"
    assert format_snmp_value(123) == "123"


def test_safe_call_success_and_error_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test case for test_safe_call_success_and_error_logging."""
    logger = Logger()

    assert safe_call(lambda: 5, default=0, logger=logger) == 5
    assert (
        safe_call(lambda: (_ for _ in ()).throw(RuntimeError("x")), default=9, logger=logger) == 9
    )
    out = capsys.readouterr().out
    assert "ERROR: Error in <lambda>: x" in out
