import json
import logging
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.snmp_agent import SNMPAgent


def test_decode_value_passthrough() -> None:
    agent = SNMPAgent()
    assert agent._decode_value(123) == 123
    assert agent._decode_value("abc") == "abc"


def test_decode_value_hex() -> None:
    agent = SNMPAgent()
    v = {"value": "\\xAA\\xBB", "encoding": "hex"}
    decoded = agent._decode_value(v)
    assert isinstance(decoded, (bytes, bytearray))
    assert decoded == b"\xAA\xBB"


def test_decode_value_unknown_encoding() -> None:
    agent = SNMPAgent()
    v = {"value": "zzz", "encoding": "base64"}
    # unknown encoding should return raw encoded value
    assert agent._decode_value(v) == "zzz"


# Additional tests to cover more of SNMPAgent

def test_setup_signal_handlers_registers_signals(monkeypatch: Any) -> None:
    calls: dict[Any, Any] = {}

    def fake_signal(sig: Any, handler: Any) -> None:
        calls[sig] = handler

    monkeypatch.setattr(signal, "signal", fake_signal)

    # Construct agent which calls _setup_signal_handlers in __init__
    agent = SNMPAgent(config_path="agent_config.yaml")

    assert signal.SIGTERM in calls
    assert signal.SIGINT in calls
    if hasattr(signal, "SIGHUP"):
        assert signal.SIGHUP in calls


def test_shutdown_closes_dispatcher(monkeypatch: Any, caplog: Any, mocker: Any) -> None:
    agent = SNMPAgent(config_path="agent_config.yaml")
    # Provide a fake dispatcher with close_dispatcher
    fake_dispatcher = mocker.Mock()
    agent.snmpEngine = SimpleNamespace(transport_dispatcher=fake_dispatcher)

    # Prevent os._exit from terminating test process
    monkeypatch.setattr(os, "_exit", lambda code: None)

    with caplog.at_level(logging.INFO):
        agent._shutdown()

    fake_dispatcher.close_dispatcher.assert_called_once()
    assert "Transport dispatcher closed successfully" in caplog.text


def test_run_with_preloaded_model_uses_preloaded_and_skips_generation(monkeypatch: Any, tmp_path: Any, caplog: Any) -> None:
    # Ensure data/types.json exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    types_file = data_dir / "types.json"
    types_file.write_text(json.dumps({"foo": "bar"}))

    # Create an agent with a preloaded model and no mibs in config
    agent = SNMPAgent(config_path="agent_config.yaml", preloaded_model={"TEST-MIB": {}})
    # Avoid running heavy setup: ensure no mibs to compile
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: [])

    # Stub validation to succeed
    monkeypatch.setattr("app.type_registry_validator.validate_type_registry_file", lambda p: (True, [], 1))

    # Prevent SNMP engine setup and further networking
    monkeypatch.setattr(SNMPAgent, "_setup_snmpEngine", lambda self, cd: setattr(self, "snmpEngine", None))

    with caplog.at_level(logging.INFO):
        agent.run()

    assert "Using preloaded model" in caplog.text
    assert agent.mib_jsons == {"TEST-MIB": {}}


def test_decode_value_delegates_to_mib_registrar(monkeypatch: Any) -> None:
    # Replace MibRegistrar with a fake that returns a sentinel value
    class FakeRegistrar:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _decode_value(self, v: Any) -> str:
            return f"decoded:{v}"

    monkeypatch.setattr("app.mib_registrar.MibRegistrar", FakeRegistrar)

    agent = SNMPAgent(config_path="agent_config.yaml")
    assert agent._decode_value("x") == "decoded:x"


def test_decode_value_fallback_returns_value_on_exception(monkeypatch: Any) -> None:
    # Make MibRegistrar constructor raise to trigger fallback
    class FailingRegistrar:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("app.mib_registrar.MibRegistrar", FailingRegistrar)

    agent = SNMPAgent(config_path="agent_config.yaml")
    sentinel = object()
    assert agent._decode_value(sentinel) is sentinel
