"""MIB compilation utilities using pysmi."""

import re
from pathlib import Path
from typing import cast

from pysmi.codegen.pysnmp import PySnmpCodeGen
from pysmi.compiler import MibCompiler as PysmiMibCompiler
from pysmi.parser.smi import parserFactory
from pysmi.reader.localfile import FileReader
from pysmi.searcher import PyFileSearcher
from pysmi.writer import PyFileWriter

from app.app_config import AppConfig
from app.app_logger import AppLogger

logger = AppLogger.get(__name__)


class MibCompilationError(Exception):
    """Raised when MIB compilation fails."""

    def __init__(self, message: str, missing_dependencies: list[str] | None = None) -> None:
        """Initialize error details for failed MIB compilation."""
        super().__init__(message)
        self.missing_dependencies = missing_dependencies or []


class MibCompiler:
    """Handles compilation of MIB .txt files to Python using pysmi."""

    def __init__(
        self, output_dir: str = "compiled-mibs", app_config: AppConfig | None = None
    ) -> None:
        """Initialize compiler output directory and optional app configuration."""
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self.last_compile_results: dict[str, str] = {}  # Track last compilation results
        self.app_config = app_config

    def _add_source_readers(self, compiler: PysmiMibCompiler, mib_dir: str) -> None:
        compiler.addSources(FileReader(mib_dir))
        compiler.addSources(FileReader("."))

        mib_data_dir = Path("data") / "mibs"
        if mib_data_dir.exists():
            compiler.addSources(FileReader(str(mib_data_dir)))
            # Use Path.iterdir() for subdirectories
            for subdir in mib_data_dir.iterdir():
                if subdir.is_dir():
                    compiler.addSources(FileReader(str(subdir)))

        system_mib_dir = (
            self.app_config.get_platform_setting("system_mib_dir")
            if self.app_config is not None
            else None
        )
        if isinstance(system_mib_dir, str) and system_mib_dir and Path(system_mib_dir).exists():
            compiler.addSources(FileReader(system_mib_dir))

    @staticmethod
    def _collect_compile_status(
        results: dict[object, object],
    ) -> tuple[list[str], list[tuple[str, str]], str | None]:
        missing_deps: list[str] = []
        failed_mibs: list[tuple[str, str]] = []
        actual_mib_name: str | None = None

        for mib, status in results.items():
            mib_name_str = str(mib)
            status_str = str(status)

            if actual_mib_name is None:
                actual_mib_name = mib_name_str

            if status_str not in ("compiled", "untouched"):
                failed_mibs.append((mib_name_str, status_str))
                if "missing" in status_str.lower():
                    missing_deps.append(mib_name_str)

        return missing_deps, failed_mibs, actual_mib_name

    @staticmethod
    def _build_missing_deps_error(actual_mib_name: str, missing_deps: list[str]) -> str:
        error_msg = f"\n{'=' * 70}\n"
        error_msg += f"ERROR: Failed to compile {actual_mib_name}\n"
        error_msg += f"{'=' * 70}\n"
        error_msg += f"Missing MIB dependencies: {', '.join(missing_deps)}\n\n"
        error_msg += "To resolve this:\n"
        error_msg += f"  1. Download the missing MIB files ({', '.join(missing_deps)})\n"
        error_msg += "  2. Place them in data/mibs/ or a subdirectory\n"
        error_msg += f"  3. Add them to agent_config.yaml before {actual_mib_name}\n"
        error_msg += f"{'=' * 70}\n"
        return error_msg

    def compile(self, mib_txt_path: str) -> str:
        """Compile a MIB .txt file to Python.

        Args:
            mib_txt_path: Path to the MIB .txt file

        Returns:
            Path to the compiled .py file

        Raises:
            RuntimeError: If compilation fails

        """
        # Get the directory containing the MIB file
        mib_path = Path(mib_txt_path).resolve()
        mib_dir = str(mib_path.parent)
        mib_filename = mib_path.name

        # Create pysmi compiler
        compiler = PysmiMibCompiler(
            parserFactory()(), PySnmpCodeGen(), PyFileWriter(self.output_dir)
        )

        # Add sources: the directory containing the MIB file and standard locations
        self._add_source_readers(compiler, mib_dir)

        # Add searchers for already compiled MIBs
        compiler.addSearchers(PyFileSearcher(self.output_dir))

        # Compile the MIB
        results = compiler.compile(mib_filename)

        # Store results for caller to access
        self.last_compile_results = {
            str(cast("object", mib)): str(cast("object", status)) for mib, status in results.items()
        }

        # Collect all missing dependencies
        missing_deps, failed_mibs, actual_mib_name = self._collect_compile_status(results)

        # Determine the compiled output path using the actual module name
        if actual_mib_name is None:
            msg = f"No MIB module found in {mib_filename}"
            raise MibCompilationError(msg)

        compiled_py = str(Path(self.output_dir) / f"{actual_mib_name}.py")

        # If there are missing dependencies, provide helpful error message
        if missing_deps:
            error_msg = self._build_missing_deps_error(actual_mib_name, missing_deps)
            raise MibCompilationError(error_msg, missing_dependencies=missing_deps)

        # If there are other failures, report them
        if failed_mibs:
            error_msg = f"Failed to compile {actual_mib_name}:\n"
            for mib, status in failed_mibs:
                error_msg += f"  - {mib}: {status}\n"
            raise MibCompilationError(error_msg)

        if not Path(compiled_py).exists():
            msg = f"Compilation reported success but output file not found: {compiled_py}"
            raise MibCompilationError(msg)

        return compiled_py

    def _parse_missing_from_status(self, status: str) -> list[str]:
        """Parse missing dependencies from compilation status message."""
        missing: set[str] = set()
        # Look for patterns like "MIB-NAME is missing" or similar
        for match in re.finditer(r"([A-Za-z0-9\-]+)\s+is missing", status):
            missing.add(match.group(1))
        return list(missing)
