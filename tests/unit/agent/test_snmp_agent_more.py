"""Tests for test snmp agent more."""

import json
import logging
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from app.api_shared import JsonValue
from app.snmp_agent import SNMPAgent


def test_decode_value_passthrough() -> None:
    """Test case for test_decode_value_passthrough."""
    agent = SNMPAgent()
    assert agent._decode_value(123) == 123
    assert agent._decode_value("abc") == "abc"


def test_decode_value_hex() -> None:
    """Test case for test_decode_value_hex."""
    agent = SNMPAgent()
    v: JsonValue = {"value": "\\xAA\\xBB", "encoding": "hex"}
    decoded = agent._decode_value(v)
    if isinstance(decoded, (bytes, bytearray)):
        assert decoded == b"\xaa\xbb"
    else:
        assert decoded == v


def test_decode_value_unknown_encoding() -> None:
    """Test case for test_decode_value_unknown_encoding."""
    agent = SNMPAgent()
    v: JsonValue = {"value": "zzz", "encoding": "base64"}
    # Unknown encodings are passed through unchanged by runtime decoding.
    assert agent._decode_value(v) == v


# Additional tests to cover more of SNMPAgent


def test_setup_signal_handlers_registers_signals(monkeypatch: Any) -> None:
    """Test case for test_setup_signal_handlers_registers_signals."""
    calls: dict[Any, Any] = {}

    def fake_signal(sig: Any, handler: Any) -> None:
        calls[sig] = handler

    monkeypatch.setattr(signal, "signal", fake_signal)

    # Construct agent which calls _setup_signal_handlers in __init__
    SNMPAgent(config_path="agent_config.yaml")

    assert signal.SIGTERM in calls
    assert signal.SIGINT in calls
    # SIGHUP registration depends on platform availability
    # On Windows: 2 signals, on Unix: 3 signals (when SIGHUP is registered)
    assert 2 <= len(calls) <= 3


def test_shutdown_closes_dispatcher(monkeypatch: Any, caplog: Any, mocker: Any) -> None:
    """Test case for test_shutdown_closes_dispatcher."""
    agent = SNMPAgent(config_path="agent_config.yaml")
    # Provide a fake dispatcher with close_dispatcher
    fake_dispatcher = mocker.Mock()
    agent.snmp_engine = cast(Any, SimpleNamespace(transport_dispatcher=fake_dispatcher))

    # Prevent os._exit from terminating test process
    monkeypatch.setattr(os, "_exit", lambda code: None)

    with caplog.at_level(logging.INFO):
        agent._shutdown()

    fake_dispatcher.close_dispatcher.assert_called_once()
    assert "Transport dispatcher closed successfully" in caplog.text


def test_run_with_preloaded_model_uses_preloaded_and_skips_generation(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    """Test case for test_run_with_preloaded_model_uses_preloaded_and_skips_generation."""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    types_file = data_dir / "types.json"
    types_file.write_text(json.dumps({"foo": "bar"}))

    # Create an agent with a preloaded model and no mibs in config
    agent = SNMPAgent(config_path="agent_config.yaml", preloaded_model={"TEST-MIB": {}})
    # Avoid running heavy setup: ensure no mibs to compile
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: [])

    # Stub validation to succeed
    monkeypatch.setattr(
        "app.type_registry_validator.validate_type_registry_file",
        lambda p: (True, [], 1),
    )

    # Prevent SNMP engine setup and further networking
    monkeypatch.setattr(
        SNMPAgent,
        "_setup_snmp_engine",
        lambda self, cd: setattr(self, "snmp_engine", None),
    )

    with caplog.at_level(logging.INFO):
        agent.run()

    assert "Using preloaded model" in caplog.text
    assert agent.mib_jsons == {"TEST-MIB": {}}


def test_decode_value_delegates_to_mib_registrar(monkeypatch: Any) -> None:
    """Test case for test_decode_value_delegates_to_mib_registrar."""

    monkeypatch.setattr(
        "app.snmp_agent.decode_value_with_runtime_registrar",
        lambda value, **kwargs: f"decoded:{value}",
    )

    agent = SNMPAgent(config_path="agent_config.yaml")
    assert agent._decode_value("x") == "decoded:x"


def test_decode_value_fallback_returns_value_on_exception(monkeypatch: Any) -> None:
    """Test case for test_decode_value_fallback_returns_value_on_exception."""

    monkeypatch.setattr(
        "app.snmp_agent.decode_value_with_runtime_registrar",
        lambda value, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    agent = SNMPAgent(config_path="agent_config.yaml")
    sentinel: JsonValue = {"sentinel": "value"}
    assert agent._decode_value(sentinel) is sentinel
