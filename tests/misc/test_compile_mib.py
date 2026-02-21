"""Tests for compile_mib CLI wrapper."""

import pytest
import pytest_mock

from app.cli_compile_mib import main
from app.compiler import MibCompilationError


def _setup_compiler(
    mock_results: dict[str, str],
    mocker: "pytest_mock.MockerFixture",
    compile_side_effect: Exception | None = None,
) -> None:
    mock_compiler = mocker.MagicMock()
    mock_compiler.last_compile_results = mock_results
    if compile_side_effect is not None:
        mock_compiler.compile.side_effect = compile_side_effect
    else:
        mock_compiler.compile.return_value = "compiled-mibs/CISCO-ALARM-MIB.py"

    mocker.patch("app.cli_compile_mib.MibCompiler", return_value=mock_compiler)
    mocker.patch("app.cli_compile_mib.os.path.exists", return_value=True)


def test_compile_mib_success(
    mocker: pytest_mock.MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test successful MIB compilation."""
    mock_results = {"CISCO-ALARM-MIB": "compiled"}
    _setup_compiler(mock_results, mocker)

    exit_code = main(["CISCO-ALARM-MIB.txt"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "CISCO-ALARM-MIB: compiled" in output.out


def test_compile_mib_failure(
    mocker: pytest_mock.MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test MIB compilation failure."""
    mock_results = {"CISCO-ALARM-MIB": "failed"}
    _setup_compiler(
        mock_results, mocker, compile_side_effect=MibCompilationError("boom")
    )

    exit_code = main(["CISCO-ALARM-MIB.txt"])
    output = capsys.readouterr()

    assert exit_code == 1
    assert "CISCO-ALARM-MIB: failed" in output.out
    assert "boom" in output.err


def test_compile_mib_partial_success(
    mocker: pytest_mock.MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test MIB compilation with partial success."""
    mock_results = {
        "CISCO-ALARM-MIB": "compiled",
        "SNMPv2-SMI": "missing",
    }
    _setup_compiler(mock_results, mocker)

    exit_code = main(["CISCO-ALARM-MIB.txt"])
    output = capsys.readouterr()

    assert exit_code == 1
    assert "CISCO-ALARM-MIB: compiled" in output.out
    assert "SNMPv2-SMI: missing" in output.out
