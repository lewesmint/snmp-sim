"""Unit tests for cli_compile_mib module."""
import pytest
from typing import Any
from app.cli_compile_mib import _print_results, _has_failures, main
from app.compiler import MibCompilationError


class TestPrintResults:
    """Test _print_results function"""

    def test_print_results_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print all results"""
        results = {"TEST-MIB": "compiled", "OTHER-MIB": "untouched"}
        _print_results(results)
        captured = capsys.readouterr()
        assert "TEST-MIB: compiled" in captured.out
        assert "OTHER-MIB: untouched" in captured.out

    def test_print_results_with_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print results including failures"""
        results = {"TEST-MIB": "failed"}
        _print_results(results)
        captured = capsys.readouterr()
        assert "TEST-MIB: failed" in captured.out


class TestHasFailures:
    """Test _has_failures function"""

    def test_has_failures_with_compiled(self) -> None:
        """Should return False when all compiled"""
        results = {"TEST-MIB": "compiled"}
        assert _has_failures(results) is False

    def test_has_failures_with_untouched(self) -> None:
        """Should return False when all untouched"""
        results = {"TEST-MIB": "untouched"}
        assert _has_failures(results) is False

    def test_has_failures_with_mixed(self) -> None:
        """Should return False when compiled and untouched"""
        results = {"TEST-MIB": "compiled", "OTHER-MIB": "untouched"}
        assert _has_failures(results) is False

    def test_has_failures_with_error(self) -> None:
        """Should return True when any failure present"""
        results = {"TEST-MIB": "compiled", "OTHER-MIB": "error"}
        assert _has_failures(results) is True

    def test_has_failures_empty(self) -> None:
        """Should return False for empty results"""
        assert _has_failures({}) is False


class TestMain:
    """Test main function"""

    def test_main_file_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should return 1 when file not found"""
        result = main(["/nonexistent/path.txt", "output"])
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_main_no_app_config(self, capsys: pytest.CaptureFixture[str], mocker: Any) -> None:
        """Should handle missing app_config gracefully"""
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch("app.cli_compile_mib.AppConfig", side_effect=FileNotFoundError)
        mock_compiler_class = mocker.patch("app.cli_compile_mib.MibCompiler")
        
        mock_compiler = mocker.Mock()
        mock_compiler.last_compile_results = {"TEST-MIB": "compiled"}
        mock_compiler_class.return_value = mock_compiler
        
        result = main(["test.txt", "output"])
        assert result == 0
        mock_compiler_class.assert_called_once_with("output", None)

    def test_main_compilation_error(self, capsys: pytest.CaptureFixture[str], mocker: Any) -> None:
        """Should handle compilation errors"""
        mocker.patch("os.path.exists", return_value=True)
        mock_config_class = mocker.patch("app.cli_compile_mib.AppConfig")
        mock_compiler_class = mocker.patch("app.cli_compile_mib.MibCompiler")
        
        mock_config = mocker.Mock()
        mock_config_class.return_value = mock_config
        
        mock_compiler = mocker.Mock()
        mock_compiler.compile.side_effect = MibCompilationError("Compilation failed")
        mock_compiler.last_compile_results = {"TEST-MIB": "error"}
        mock_compiler_class.return_value = mock_compiler
        
        result = main(["test.txt", "output"])
        assert result == 1
        captured = capsys.readouterr()
        assert "Compilation failed" in captured.err
        assert "TEST-MIB: error" in captured.out

    def test_main_success_with_untouched(self, capsys: pytest.CaptureFixture[str], mocker: Any) -> None:
        """Should return 0 when compilation succeeds"""
        mocker.patch("os.path.exists", return_value=True)
        mock_config_class = mocker.patch("app.cli_compile_mib.AppConfig")
        mock_compiler_class = mocker.patch("app.cli_compile_mib.MibCompiler")
        
        mock_config = mocker.Mock()
        mock_config_class.return_value = mock_config
        
        mock_compiler = mocker.Mock()
        mock_compiler.last_compile_results = {"TEST-MIB": "compiled"}
        mock_compiler_class.return_value = mock_compiler
        
        result = main(["test.txt", "output"])
        assert result == 0

    def test_main_with_failures(self, capsys: pytest.CaptureFixture[str], mocker: Any) -> None:
        """Should return 1 when compilation has failures"""
        mocker.patch("os.path.exists", return_value=True)
        mock_config_class = mocker.patch("app.cli_compile_mib.AppConfig")
        mock_compiler_class = mocker.patch("app.cli_compile_mib.MibCompiler")
        
        mock_config = mocker.Mock()
        mock_config_class.return_value = mock_config
        
        mock_compiler = mocker.Mock()
        mock_compiler.last_compile_results = {"TEST-MIB": "compiled", "OTHER": "failed"}
        mock_compiler_class.return_value = mock_compiler
        
        result = main(["test.txt", "output"])
        assert result == 1
