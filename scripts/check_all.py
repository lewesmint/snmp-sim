"""Run consolidated quality checks for the main project Python folders."""
# ruff: noqa: INP001

from __future__ import annotations

import argparse
import logging
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRS = ("app", "tests", "plugins", "ui", "scripts")
logger = logging.getLogger(__name__)


def dirs_with_python_files(root: Path, dirs: list[str]) -> list[str]:
    """Filter dirs to only those containing .py or .pyi files."""
    filtered: list[str] = []
    for d in dirs:
        base = root / d
        if any(base.rglob("*.py")) or any(base.rglob("*.pyi")):
            filtered.append(d)
    return filtered


@dataclass(frozen=True)
class ToolRun:
    """Metadata describing one external tool execution."""

    name: str
    command: list[str]
    install_hint: str


@dataclass(frozen=True)
class ToolResult:
    """Execution result for an external tool run."""

    name: str
    ok: bool
    return_code: int


@dataclass(frozen=True)
class SuppressionHit:
    """A suppression marker found in source code."""

    file: Path
    line_no: int
    line: str
    pattern: str


SUPPRESSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noqa", re.compile(r"#\s*noqa(?::\s*[A-Z0-9, ]+)?\b", re.IGNORECASE)),
    ("ruff-noqa", re.compile(r"ruff:\s*noqa\b", re.IGNORECASE)),
    ("type-ignore", re.compile(r"#\s*type:\s*ignore(\[[^\]]+\])?\b", re.IGNORECASE)),
    ("pyright-ignore", re.compile(r"#\s*pyright:\s*ignore\b", re.IGNORECASE)),
    ("pyright-report-suppress", re.compile(r"report[A-Za-z]+:\s*ignore\b")),
    ("pylint-disable", re.compile(r"pylint:\s*disable\b", re.IGNORECASE)),
    ("flake8-noqa", re.compile(r"noqa:\s*[A-Z0-9]+", re.IGNORECASE)),
    ("mypy-ignore", re.compile(r"#\s*mypy:\s*ignore-errors\b", re.IGNORECASE)),
    ("pragma-no-cover", re.compile(r"pragma:\s*no\s*cover\b", re.IGNORECASE)),
)

DEFAULT_EXCLUDES = (
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    ".git",
    ".tox",
)


def quote_cmd(parts: Iterable[str]) -> str:
    """Return a shell-safe printable command string."""
    return " ".join(shlex.quote(p) for p in parts)


def require_executable(executable: str, install_hint: str) -> None:
    """Ensure an executable exists on PATH before a tool run."""
    if shutil.which(executable) is None:
        logger.info("")
        logger.error("ERROR: Required tool '%s' is not installed or not on PATH.", executable)
        logger.error("Install it, then re-run this script.")
        logger.info("")
        logger.error("Suggested install:")
        logger.error("%s", install_hint)
        raise SystemExit(2)


def run_tool(name: str, command: list[str], cwd: Path) -> ToolResult:
    """Execute one tool command and normalise its status."""
    if name == "pytest (with coverage)":
        clear_coverage_artifacts(cwd)

    logger.info("")
    logger.info("==> %s", name)
    logger.info("    %s", quote_cmd(command))
    completed = subprocess.run(command, cwd=str(cwd), check=False)  # noqa: S603
    return ToolResult(name=name, ok=completed.returncode == 0, return_code=completed.returncode)


def clear_coverage_artifacts(root: Path) -> None:
    """Remove existing coverage data files to avoid mixed-mode combine errors."""
    for path in root.glob(".coverage*"):
        if path.is_file():
            path.unlink()


def existing_target_dirs(root: Path) -> list[str]:
    """Validate all configured project target directories exist."""
    missing = [d for d in PROJECT_DIRS if not (root / d).exists()]
    if missing:
        logger.info("")
        logger.error("ERROR: These expected directories do not exist at project root:")
        for d in missing:
            logger.error("- %s", d)
        logger.info("")
        logger.error("Project root is:")
        logger.error("%s", root)
        raise SystemExit(2)

    return list(PROJECT_DIRS)


def iter_python_files(root: Path, targets: Iterable[str]) -> Iterable[Path]:
    """Yield Python files under targets, skipping excluded directories."""
    exclude_names = set(DEFAULT_EXCLUDES)
    for target in targets:
        base = root / target
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".pyi"}:
                continue
            parts = {p.name for p in path.parents}
            if parts & exclude_names:
                continue
            yield path


def scan_suppressions(root: Path, targets: list[str]) -> list[SuppressionHit]:
    """Scan target files for suppression comments used by linters/type checkers."""
    hits: list[SuppressionHit] = []
    for py_file in iter_python_files(root, targets):
        try:
            text = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = py_file.read_text(encoding="utf-8", errors="replace")

        for idx, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SUPPRESSION_PATTERNS:
                if pattern.search(line):
                    hits.append(
                        SuppressionHit(
                            file=py_file.relative_to(root),
                            line_no=idx,
                            line=line.rstrip(),
                            pattern=label,
                        )
                    )
    return hits


def run_suppressions_only(root: Path, targets: list[str]) -> int:
    """Run suppression scan mode and return a process-style status code."""
    hits = scan_suppressions(root, targets)
    if hits:
        logger.info("")
        logger.info("Suppression markers found")
        logger.info("-------------------------")
        for hit in hits:
            logger.info("%s:%s [%s] %s", hit.file, hit.line_no, hit.pattern, hit.line)
        return 1
    logger.info("No suppression markers found.")
    return 0


def build_tools(
    targets: list[str],
    mypy_targets: list[str],
    *,
    fix: bool,
    optional: bool,
    with_pylint: bool,
    with_wrapper_sync: bool,
    with_wrapper_source_check: bool,
    pip_audit_verbose: bool,
) -> list[ToolRun]:
    """Build the ordered set of quality tools to execute."""
    tools: list[ToolRun] = []

    if fix:
        tools.append(
            ToolRun(
                name="ruff format",
                command=["ruff", "format", *targets],
                install_hint="python -m pip install -U ruff",
            )
        )
        tools.append(
            ToolRun(
                name="ruff check (fix)",
                command=["ruff", "check", "--fix", *targets],
                install_hint="python -m pip install -U ruff",
            )
        )
    else:
        tools.append(
            ToolRun(
                name="ruff format (check)",
                command=["ruff", "format", "--check", *targets],
                install_hint="python -m pip install -U ruff",
            )
        )
        tools.append(
            ToolRun(
                name="ruff check",
                command=["ruff", "check", *targets],
                install_hint="python -m pip install -U ruff",
            )
        )

    # Types
    tools.append(
        ToolRun(
            name="mypy",
            command=["mypy", *mypy_targets],
            install_hint="python -m pip install -U mypy",
        )
    )
    tools.append(
        ToolRun(
            name="pyright",
            command=["pyright", *targets],
            install_hint="python -m pip install -U pyright",
        )
    )

    if with_pylint:
        tools.append(
            ToolRun(
                name="pylint",
                command=[sys.executable, "-m", "pylint", *targets],
                install_hint="python -m pip install -U pylint",
            )
        )

    if with_wrapper_sync:
        tools.append(
            ToolRun(
                name="wrapper sync",
                command=["bash", "scripts/check_wrapper_sync.sh"],
                install_hint="Ensure bash is available (standard on macOS/Linux)",
            )
        )

    if with_wrapper_source_check:
        tools.append(
            ToolRun(
                name="wrapper source",
                command=["bash", "scripts/check_wrapper_package_source.sh"],
                install_hint="Ensure bash is available (standard on macOS/Linux)",
            )
        )

    tools.append(
        ToolRun(
            name="pytest (with coverage)",
            command=[
                "pytest",
                "-q",
                "--maxfail=1",
                "--disable-warnings",
                "--cov",
                "--cov-report=term-missing",
            ],
            install_hint="python -m pip install -U pytest pytest-cov",
        )
    )

    # Security
    tools.append(
        ToolRun(
            name="bandit",
            command=["bandit", "-q", "-r", *targets],
            install_hint="python -m pip install -U bandit",
        )
    )

    # Use the active interpreter to avoid pyenv/venv mismatches
    pip_audit_cmd = [sys.executable, "-m", "pip_audit"]
    if pip_audit_verbose:
        pip_audit_cmd.append("-v")

    tools.append(
        ToolRun(
            name="pip-audit",
            command=pip_audit_cmd,
            install_hint="python -m pip install -U pip-audit",
        )
    )

    # Optional heavier checks
    if optional:
        tools.append(
            ToolRun(
                name="vulture (dead code)",
                command=["vulture", *targets],
                install_hint="python -m pip install -U vulture",
            )
        )
        tools.append(
            ToolRun(
                name="radon (complexity)",
                command=["radon", "cc", "-s", "-a", *targets],
                install_hint="python -m pip install -U radon",
            )
        )
        tools.append(
            ToolRun(
                name="jscpd (duplication)",
                command=[
                    "jscpd",
                    "--languages",
                    "python",
                    "--ignore",
                    "**/.venv/**,**/build/**,**/dist/**,**/.mypy_cache/**,**/.ruff_cache/**,"
                    "**/__pycache__/**,**/.pytest_cache/**",
                    "--min-lines",
                    "8",
                    "--min-tokens",
                    "70",
                    ".",
                ],
                install_hint="npm install -g jscpd",
            )
        )

    return tools


def main() -> int:
    """Parse CLI arguments, run checks, and print a summary."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Run Python quality checks across app/tests/plugins/ui/scripts, "
            "and scan for suppressions."
        )
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply auto-fixes (ruff format and ruff check --fix).",
    )
    parser.add_argument(
        "--optional",
        action="store_true",
        help="Run heavier optional tools (vulture, radon, jscpd).",
    )
    parser.add_argument(
        "--with-pylint",
        action="store_true",
        help="Run pylint in addition to the default quality toolchain.",
    )
    parser.add_argument(
        "--with-wrapper-sync",
        action="store_true",
        help="Run vendored-wrapper drift check against ../pysnmp-type-wrapper.",
    )
    parser.add_argument(
        "--with-wrapper-source-check",
        action="store_true",
        help="Report where pysnmp_type_wrapper resolves from (vendored vs external).",
    )
    parser.add_argument(
        "--fail-on-suppressions",
        action="store_true",
        help="Fail if any suppression markers are found (noqa, type: ignore, pylint disable, etc).",
    )
    parser.add_argument(
        "--suppressions-only",
        action="store_true",
        help="Only scan for suppressions, do not run external tools.",
    )
    parser.add_argument(
        "--pip-audit-verbose",
        action="store_true",
        help="Run pip-audit with verbose output for full vulnerability details.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets = existing_target_dirs(root)
    targets_for_tools = dirs_with_python_files(root, targets)
    mypy_targets = [
        str(path.relative_to(root)) for path in iter_python_files(root, targets_for_tools)
    ]

    if args.suppressions_only:
        return run_suppressions_only(root, targets)

    if not targets_for_tools or not mypy_targets:
        logger.info("")
        if not targets_for_tools:
            logger.error("ERROR: None of the target directories contain any .py or .pyi files.")
            logger.error("Targets checked:")
            for d in targets:
                logger.error("- %s", d)
        else:
            logger.error("ERROR: No Python files found for mypy after excludes.")
        return 2

    # Preflight: require every tool that will be run
    tools = build_tools(
        targets=targets_for_tools,
        mypy_targets=mypy_targets,
        fix=args.fix,
        optional=args.optional,
        with_pylint=args.with_pylint,
        with_wrapper_sync=args.with_wrapper_sync,
        with_wrapper_source_check=args.with_wrapper_source_check,
        pip_audit_verbose=args.pip_audit_verbose,
    )
    for tool in tools:
        require_executable(tool.command[0], tool.install_hint)

    results: list[ToolResult] = [run_tool(tool.name, tool.command, cwd=root) for tool in tools]

    hits = scan_suppressions(root, targets)

    logger.info("")
    logger.info("Summary")
    logger.info("-------")
    any_failed = False
    for res in results:
        status = "OK" if res.ok else f"FAIL ({res.return_code})"
        logger.info("%s: %s", res.name, status)
        if not res.ok:
            any_failed = True

    if hits:
        logger.info("")
        logger.info("Suppression markers found")
        logger.info("-------------------------")
        for hit in hits:
            logger.info("%s:%s [%s] %s", hit.file, hit.line_no, hit.pattern, hit.line)

        if args.fail_on_suppressions:
            any_failed = True

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
