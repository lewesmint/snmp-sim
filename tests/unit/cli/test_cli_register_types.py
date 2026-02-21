from pathlib import Path
import pytest
from typing import Any

from app import cli_register_types as crt


def test_main_missing_compiled_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_dir = tmp_path / "nope"
    rc = crt.main(["--compiled-mibs-dir", str(fake_dir)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Compiled MIBs directory not found" in captured.err


def test_main_success_with_mocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mocker: Any
) -> None:
    # Mock build_type_registry to return a simple registry
    fake_registry = {"MyType": {"base_type": "Integer32", "used_by": []}}
    mocker.patch("app.cli_register_types.build_type_registry", return_value=fake_registry)
    rc = crt.main(["--compiled-mibs-dir", str(tmp_path), "--output", str(tmp_path / "out.json")])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Successfully built type registry" in captured.out


def test_main_verbose_output_formatting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mocker: Any
) -> None:
    # Mock build_type_registry and BaseTypeHandler for verbose output
    fake_registry = {
        "MyType": {
            "base_type": "Integer32",
            "used_by": ["some.mib"],
            "defined_in": "MY-MIB",
            "abstract": False,
        },
        "EnumType": {
            "base_type": "Integer32",
            "used_by": ["other.mib"],
            "defined_in": "OTHER-MIB",
            "abstract": False,
            "enums": [{"name": "up", "value": 1}, {"name": "down", "value": 2}],
        },
        "StringType": {
            "base_type": "DisplayString",
            "used_by": ["string.mib"],
            "defined_in": "STRING-MIB",
            "abstract": False,
        },
        "BytesType": {
            "base_type": "OctetString",
            "used_by": ["bytes.mib"],
            "defined_in": "BYTES-MIB",
            "abstract": False,
        },
    }

    class MockHandler:
        def get_default_value(self, type_name: str) -> object:
            if type_name == "MyType":
                return 42
            elif type_name == "EnumType":
                return 1  # Should format as 1(up)
            elif type_name == "StringType":
                return "hello world"  # Should truncate
            elif type_name == "BytesType":
                return b"binary data"  # Should format as b"..."
            return None

    mocker.patch("app.cli_register_types.build_type_registry", return_value=fake_registry)
    mocker.patch("app.cli_register_types.BaseTypeHandler", return_value=MockHandler())
    rc = crt.main(["--compiled-mibs-dir", str(tmp_path), "--verbose"])
    captured = capsys.readouterr()
    assert rc == 0
    out = captured.out
    assert "MyType" in out
    assert "Integer32" in out
    assert "42" in out
    assert "1(up)" in out  # Enum formatting
    assert '"hello w..."' in out  # String truncation (matches current 7-char slice)
    assert 'b"binary ..."' in out  # Bytes formatting (includes space in 7-char slice)


def test_main_exception_handling(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mocker: Any
) -> None:
    mocker.patch(
        "app.cli_register_types.build_type_registry",
        side_effect=Exception("test error"),
    )
    rc = crt.main(["--compiled-mibs-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Error building type registry: test error" in captured.err
