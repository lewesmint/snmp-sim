"""Tests for test cli run agent."""

from typing import Any
import pytest
import app.cli_run_agent as cli



def test_main_missing_config(monkeypatch: Any, capsys: Any) -> None:
    """Test case for test_main_missing_config."""

    # AppConfig constructor raises FileNotFoundError
    class BadConfig:
        """Test helper class for BadConfig."""

        def __init__(self, path: str) -> None:
            raise FileNotFoundError()

    monkeypatch.setattr(cli, "AppConfig", BadConfig)

    ret = cli.main(["--config", "nope.yaml"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "Error: Config file not found" in captured.err


def test_main_no_mibs_configured(monkeypatch: Any, capsys: Any) -> None:
    """Test case for test_main_no_mibs_configured."""

    class EmptyConfig:
        """Test helper class for EmptyConfig."""

        def __init__(self, path: str) -> None:
            pass

        def get(self, _key: str, _default: Any = None) -> Any:
            """Test case for get."""
            return []

    monkeypatch.setattr(cli, "AppConfig", EmptyConfig)

    ret = cli.main(["--config", "some.yaml"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "No MIBs configured" in captured.err


def test_main_no_schemas_loaded(monkeypatch: Any, capsys: Any) -> None:
    """Test case for test_main_no_schemas_loaded."""

    class Cfg:
        """Test helper class for Cfg."""

        def __init__(self, path: str) -> None:
            pass

        def get(self, _key: str, _default: Any = None) -> Any:
            """Test case for get."""
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {})

    ret = cli.main(["--config", "some.yaml", "--schema-dir", "unused"])
    captured = capsys.readouterr()
    assert ret == 1
    assert "Error: No schemas could be loaded" in captured.err


@pytest.mark.parametrize(
    "agent_outcome,argv,expected_rc,expected_stream,expected_text",
    [
        (
            KeyboardInterrupt(),
            ["--config", "some.yaml"],
            0,
            "out",
            "Agent stopped by user",
        ),
        (
            RuntimeError("boom"),
            ["--config", "some.yaml"],
            1,
            "err",
            "Error running agent: boom",
        ),
        (
            None,
            ["--host", "0.0.0.0", "--port", "9999", "--config", "c.yaml"],
            0,
            "out",
            "Starting SNMP agent on 0.0.0.0:9999",
        ),
    ],
)
def test_main_agent_run_outcomes(
    monkeypatch: Any,
    capsys: Any,
    agent_outcome: BaseException | None,
    argv: list[str],
    expected_rc: int,
    expected_stream: str,
    expected_text: str,
) -> None:
    """Test run outcomes for keyboard interrupt, runtime failure, and success."""

    class Cfg:
        """Test helper class for Cfg."""

        def __init__(self, path: str) -> None:
            pass

        def get(self, _key: str, _default: Any = None) -> Any:
            """Test case for get."""
            return ["TEST-MIB"]

    monkeypatch.setattr(cli, "AppConfig", Cfg)
    monkeypatch.setattr(cli, "build_internal_model", lambda mibs, sd: {"TEST-MIB": {}})

    class Agent:
        """Test helper class for agent run outcomes."""

        def __init__(self, host: str, port: int, config_path: str, preloaded_model: Any) -> None:
            pass

        def run(self) -> None:
            """Raise configured exception, or succeed when no exception is configured."""
            if agent_outcome is not None:
                raise agent_outcome

    monkeypatch.setattr(cli, "SNMPAgent", Agent)

    ret = cli.main(argv)
    captured = capsys.readouterr()
    assert ret == expected_rc
    text = captured.out if expected_stream == "out" else captured.err
    assert expected_text in text
