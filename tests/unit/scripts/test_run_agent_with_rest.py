# pylint: disable=missing-module-docstring,missing-function-docstring
# pylint: disable=missing-class-docstring,too-few-public-methods
# pylint: disable=import-error,no-name-in-module
from __future__ import annotations

import runpy
import socket
import sys
import threading
from typing import Any

import pytest
import uvicorn

import app.api
from app import api_state
import app.snmp_agent
import run_agent_with_rest as raw


def test_run_snmp_agent_handles_success() -> None:
    class DummyAgent:
        def __init__(self) -> None:
            self.ran = False

        def run(self) -> None:
            self.ran = True

    agent: Any = DummyAgent()
    raw.run_snmp_agent(agent)
    assert agent.ran is True


def test_run_snmp_agent_reports_error(capsys: Any) -> None:
    class DummyAgent:
        def run(self) -> None:
            msg = "boom"
            raise RuntimeError(msg)

    bad_agent: Any = DummyAgent()
    with pytest.raises(SystemExit) as exc:
        raw.run_snmp_agent(bad_agent)
    assert exc.value.code == 1

    output = capsys.readouterr()
    assert "SNMP Agent ERROR" in output.err


def test_main_starts_uvicorn_and_sets_agent(monkeypatch: Any) -> None:
    run_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class DummyAgent:
        pass

    class DummyThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self.started = False

        def start(self) -> None:
            self.started = True

    class DummySocket:
        def setsockopt(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def bind(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def close(self) -> None:
            return None

    def fake_run(*args: Any, **kwargs: Any) -> None:
        run_calls.append((args, kwargs))
        return None

    monkeypatch.setattr(app.snmp_agent, "SNMPAgent", DummyAgent)
    monkeypatch.setattr(threading, "Thread", DummyThread)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: DummySocket())
    monkeypatch.setattr(sys, "argv", ["run_agent_with_rest.py"])

    with pytest.raises(SystemExit):
        runpy.run_module("run_agent_with_rest", run_name="__main__")

    assert api_state.state.snmp_agent is not None
    assert run_calls
    args, kwargs = run_calls[0]
    assert args[0] == "app.api:app"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8800
    assert kwargs["reload"] is False
