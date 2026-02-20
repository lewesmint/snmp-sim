"""
Unit tests for CLI scripts.
"""
import pytest
from pathlib import Path
from typing import Any
from app.compiler import MibCompilationError

def test_cli_compile_mib_main(tmp_path: Path, mocker: Any) -> None:
    """Test cli_compile_mib main function"""
    # Create a fake MIB file
    mib_file = tmp_path / "TEST-MIB.txt"
    mib_file.write_text("TEST-MIB DEFINITIONS ::= BEGIN END")
    
    mocker.patch('sys.argv', ['cli_compile_mib.py', str(mib_file)])
    mock_compiler = mocker.patch('app.cli_compile_mib.MibCompiler')
    
    mock_instance = mocker.Mock()
    mock_instance.compile.return_value = '/fake/output.py'
    mock_instance.last_compile_results = {"TEST-MIB": "OK"}
    mock_compiler.return_value = mock_instance
    
    from app.cli_compile_mib import main
    main()
    
    mock_instance.compile.assert_called_once()


def test_cli_compile_mib_no_args(mocker: Any) -> None:
    """Test cli_compile_mib with no arguments"""
    mocker.patch('sys.argv', ['cli_compile_mib.py'])
    with pytest.raises(SystemExit):
        from app.cli_compile_mib import main
        main()


def test_cli_mib_to_json_main(tmp_path: Path, mocker: Any) -> None:
    """Test cli_mib_to_json main function"""
    # Create a fake compiled MIB
    mib_py = tmp_path / "SNMPv2-MIB.py"
    mib_py.write_text("# compiled MIB")
    
    mocker.patch('sys.argv', ['cli_mib_to_json.py', str(mib_py)])
    mock_gen = mocker.patch('app.cli_mib_to_json.BehaviourGenerator')
    
    mock_instance = mocker.Mock()
    mock_instance.generate.return_value = '/fake/output.json'
    mock_gen.return_value = mock_instance
    
    from app.cli_mib_to_json import main
    main()
    
    mock_instance.generate.assert_called_once()


def test_cli_mib_to_json_no_args(mocker: Any) -> None:
    """Test cli_mib_to_json with no arguments"""
    mocker.patch('sys.argv', ['cli_mib_to_json.py'])
    mocker.patch('app.cli_mib_to_json.AppConfig', side_effect=FileNotFoundError("No config"))
    from app.cli_mib_to_json import main
    result = main()
    # Should return non-zero (config not found)
    assert result == 1


def test_cli_mib_to_json_with_mib_name(tmp_path: Path, mocker: Any) -> None:
    """Test cli_mib_to_json with explicit MIB name"""
    # Create a fake compiled MIB
    mib_py = tmp_path / "SNMPv2-MIB.py"
    mib_py.write_text("# compiled MIB")
    
    mocker.patch('sys.argv', ['cli_mib_to_json.py', str(mib_py), 'SNMPv2-MIB'])
    mock_gen = mocker.patch('app.cli_mib_to_json.BehaviourGenerator')
    
    mock_instance = mocker.Mock()
    mock_instance.generate.return_value = '/fake/output.json'
    mock_gen.return_value = mock_instance
    
    from app.cli_mib_to_json import main
    main()
    
    # Should be called with the file and mib_name as positional args
    call_args = mock_instance.generate.call_args
    assert str(mib_py) in str(call_args[0])  # Check that path is in args


def test_cli_compile_mib_config_not_found(tmp_path: Path, mocker: Any) -> None:
    """Test cli_compile_mib when config file not found"""
    mib_file = tmp_path / "TEST-MIB.txt"
    mib_file.write_text("TEST-MIB DEFINITIONS ::= BEGIN END")
    
    mocker.patch('sys.argv', ['cli_compile_mib.py', str(mib_file)])
    mock_config = mocker.patch('app.cli_compile_mib.AppConfig')
    mock_compiler = mocker.patch('app.cli_compile_mib.MibCompiler')
    
    # Simulate FileNotFoundError when loading config
    mock_config.side_effect = FileNotFoundError("No config")
    
    mock_instance = mocker.Mock()
    mock_instance.compile.return_value = '/fake/output.py'
    mock_instance.last_compile_results = {"TEST-MIB": "compiled"}
    mock_compiler.return_value = mock_instance
    
    from app.cli_compile_mib import main
    result = main()
    
    # Should still work with None config
    assert result == 0
    mock_compiler.assert_called_once_with('compiled-mibs', None)


def test_cli_compile_mib_compilation_error(tmp_path: Path, mocker: Any) -> None:
    """Test cli_compile_mib when compilation raises MibCompilationError"""
    mib_file = tmp_path / "BAD-MIB.txt"
    mib_file.write_text("BAD MIB")
    
    mocker.patch('sys.argv', ['cli_compile_mib.py', str(mib_file)])
    mock_compiler = mocker.patch('app.cli_compile_mib.MibCompiler')
    
    mock_instance = mocker.Mock()
    mock_instance.compile.side_effect = MibCompilationError("Compilation failed")
    mock_instance.last_compile_results = {"BAD-MIB": "failed"}
    mock_compiler.return_value = mock_instance
    
    from app.cli_compile_mib import main
    result = main()
    
    # Should return 1 on compilation error
    assert result == 1


def test_cli_compile_mib_has_failures(tmp_path: Path, mocker: Any) -> None:
    """Test cli_compile_mib returns 1 when compilation has failures"""
    mib_file = tmp_path / "TEST-MIB.txt"
    mib_file.write_text("TEST-MIB DEFINITIONS ::= BEGIN END")
    
    mocker.patch('sys.argv', ['cli_compile_mib.py', str(mib_file)])
    mock_compiler = mocker.patch('app.cli_compile_mib.MibCompiler')
    
    mock_instance = mocker.Mock()
    mock_instance.compile.return_value = '/fake/output.py'
    mock_instance.last_compile_results = {"TEST-MIB": "error: failed"}
    mock_compiler.return_value = mock_instance
    
    from app.cli_compile_mib import main
    result = main()
    
    # Should return 1 when there are failures
    assert result == 1


def test_cli_compile_mib_compilation_error_no_results(tmp_path: Path, mocker: Any) -> None:
    """Test cli_compile_mib when MibCompilationError with no results"""
    mib_file = tmp_path / "BAD-MIB.txt"
    mib_file.write_text("BAD MIB")
    
    mocker.patch('sys.argv', ['cli_compile_mib.py', str(mib_file)])
    mock_compiler = mocker.patch('app.cli_compile_mib.MibCompiler')
    
    mock_instance = mocker.Mock()
    mock_instance.compile.side_effect = MibCompilationError("Compilation failed")
    mock_instance.last_compile_results = None
    mock_compiler.return_value = mock_instance
    
    from app.cli_compile_mib import main
    result = main()
    
    # Should return 1 on compilation error even without results
    assert result == 1
