from typing import Any

import app.cli_run_agent as cli


def test_main_missing_config(monkeypatch: Any, capsys: Any) -> None:
    # AppConfig constructor raises FileNotFoundError
    class BadConfig:
        def __init__(self, path: str) -> None:
            raise FileNotFoundError()

    monkeypatch.setattr(cli, "AppConfig", BadConfig)

    ret = cli.main(["--config", "nope.yaml"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "Error: Config file not found" in captured.err


def test_main_no_mibs_configured(monkeypatch: Any, capsys: Any) -> None:
    class EmptyConfig:
        def __init__(self, path: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return []

    monkeypatch.setattr(cli, "AppConfig", EmptyConfig)

    ret = cli.main(["--config", "some.yaml"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "No MIBs configured" in captured.err


def test_main_no_schemas_loaded(monkeypatch: Any, capsys: Any) -> None:
    class Cfg:
        def __init__(self, path: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {})

    ret = cli.main(["--config", "some.yaml", "--schema-dir", "unused"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "Error: No schemas could be loaded" in captured.err


def test_main_agent_keyboard_interrupt(monkeypatch: Any, capsys: Any) -> None:
    class Cfg:
        def __init__(self, path: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {"TEST-MIB": {}})

    class FakeAgent:
        def __init__(
            self, host: str, port: int, config_path: str, preloaded_model: Any
        ) -> None:
            pass

        def run(self) -> None:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "SNMPAgent", FakeAgent)

    ret = cli.main(["--config", "some.yaml"])
    captured = capsys.readouterr()
    assert ret == 0
    assert "Agent stopped by user" in captured.out


def test_main_agent_exception(monkeypatch: Any, capsys: Any) -> None:
    class Cfg:
        def __init__(self, path: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {"TEST-MIB": {}})

    class BadAgent:
        def __init__(
            self, host: str, port: int, config_path: str, preloaded_model: Any
        ) -> None:
            pass

        def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "SNMPAgent", BadAgent)

    ret = cli.main(["--config", "some.yaml"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "Error running agent: boom" in captured.err


def test_main_success(monkeypatch: Any, capsys: Any) -> None:
    class Cfg:
        def __init__(self, path: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {"TEST-MIB": {}})

    class OkAgent:
        def __init__(
            self, host: str, port: int, config_path: str, preloaded_model: Any
        ) -> None:
            pass

        def run(self) -> None:
            return None

    monkeypatch.setattr(cli, "SNMPAgent", OkAgent)

    ret = cli.main(["--host", "0.0.0.0", "--port", "9999", "--config", "c.yaml"])
    captured = capsys.readouterr()
    assert ret == 0
    assert "Starting SNMP agent on 0.0.0.0:9999" in captured.out
