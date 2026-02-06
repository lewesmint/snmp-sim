"""Tests for mib_to_json CLI wrapper."""

import os
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from app.cli_mib_to_json import check_imported_mibs, main


def test_cli_success_prints_path(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should generate behaviour JSON and print the path."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=True)

    mock_generator = mocker.MagicMock()
    mock_generator.generate.return_value = "mock-behaviour/TEST-MIB/schema.json"
    mocker.patch("app.cli_mib_to_json.BehaviourGenerator", return_value=mock_generator)

    exit_code = main(["compiled-mibs/TEST-MIB.py", "TEST-MIB"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Schema JSON written to mock-behaviour/TEST-MIB/schema.json" in output.out


def test_cli_missing_compiled_mib(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should error when compiled MIB path is missing."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=False)

    exit_code = main(["compiled-mibs/MISSING.py", "MISSING-MIB"])
    output = capsys.readouterr()

    assert exit_code == 1
    assert "Error: compiled MIB not found" in output.err


def test_cli_checks_imports_when_txt_path_provided(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should call import checks when a MIB text file is provided."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=True)
    mock_check = mocker.patch("app.cli_mib_to_json.check_imported_mibs")

    mock_generator = mocker.MagicMock()
    mock_generator.generate.return_value = "mock-behaviour/TEST-MIB/schema.json"
    mocker.patch("app.cli_mib_to_json.BehaviourGenerator", return_value=mock_generator)

    exit_code = main(["compiled-mibs/TEST-MIB.py", "TEST-MIB", "data/mibs/TEST-MIB.txt"])
    output = capsys.readouterr()

    assert exit_code == 0
    mock_check.assert_called_once()
    assert "Schema JSON written to mock-behaviour/TEST-MIB/schema.json" in output.out


def test_cli_no_plugins_flag(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should disable plugin loading when --no-plugins is used."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=True)

    mock_generator = mocker.MagicMock()
    mock_generator.generate.return_value = "mock-behaviour/TEST-MIB/schema.json"
    mocker.patch("app.cli_mib_to_json.BehaviourGenerator", return_value=mock_generator)

    exit_code = main(["compiled-mibs/TEST-MIB.py", "TEST-MIB", "--no-plugins"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Schema JSON written to mock-behaviour/TEST-MIB/schema.json" in output.out


def test_check_imported_mibs_warns_missing_compiled(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check_imported_mibs should warn when compiled dependency is missing."""
    mibs_dir = tmp_path / "mibs"
    mibs_dir.mkdir(parents=True, exist_ok=True)
    mib_txt = mibs_dir / "TEST-MIB.txt"
    mib_txt.write_text(
        "IMPORTS\n"
        "    someType FROM SNMPv2-SMI\n"
        "    otherType FROM IF-MIB;\n"
    )

    compiled_dir = str(tmp_path / "compiled-mibs")
    os.makedirs(compiled_dir, exist_ok=True)

    check_imported_mibs(str(mib_txt), compiled_dir)
    output = capsys.readouterr()

    assert "WARNING: MIB imports SNMPv2-SMI" in output.out
    assert "WARNING: MIB imports IF-MIB" in output.out


def test_check_imported_mibs_missing_txt_path(capsys: pytest.CaptureFixture[str]) -> None:
    """check_imported_mibs should warn when MIB text file is missing."""
    check_imported_mibs("/no/such/file.txt", "compiled-mibs")
    output = capsys.readouterr()

    assert "WARNING: MIB source file" in output.out


def test_cli_output_dir_flag(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should pass output dir to BehaviourGenerator."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=True)

    mock_generator = mocker.MagicMock()
    mock_generator.generate.return_value = "custom-out/TEST-MIB/schema.json"
    mocker.patch("app.cli_mib_to_json.BehaviourGenerator", return_value=mock_generator)

    exit_code = main(["compiled-mibs/TEST-MIB.py", "TEST-MIB", "--output-dir", "custom-out"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Schema JSON written to custom-out/TEST-MIB/schema.json" in output.out


def test_cli_mib_name_optional(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI should allow mib_name to be omitted."""
    mocker.patch("app.cli_mib_to_json.os.path.exists", return_value=True)

    mock_generator = mocker.MagicMock()
    mock_generator.generate.return_value = "mock-behaviour/TEST-MIB/schema.json"
    mocker.patch("app.cli_mib_to_json.BehaviourGenerator", return_value=mock_generator)

    exit_code = main(["compiled-mibs/TEST-MIB.py"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Schema JSON written to mock-behaviour/TEST-MIB/schema.json" in output.out

