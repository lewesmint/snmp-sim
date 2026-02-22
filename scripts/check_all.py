#!/usr/bin/env python3
"""Run consolidated quality checks for the main project Python folders."""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_DIRS = ("app", "tests", "plugins", "ui", "scripts")


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
        print()
        print(f"ERROR: Required tool '{executable}' is not installed or not on PATH.")
        print("Install it, then re-run this script.")
        print()
        print("Suggested install:")
        print(install_hint)
        raise SystemExit(2)


def run_tool(name: str, command: list[str], cwd: Path) -> ToolResult:
    """Execute one tool command and normalise its status."""
    if name == "pytest (with coverage)":
        clear_coverage_artifacts(cwd)

    print()
    print(f"==> {name}")
    print("    " + quote_cmd(command))
    completed = subprocess.run(command, cwd=str(cwd), check=False)
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
        print()
        print("ERROR: These expected directories do not exist at project root:")
        for d in missing:
            print(f"- {d}")
        print()
        print("Project root is:")
        print(str(root))
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
        print()
        print("Suppression markers found")
        print("-------------------------")
        for hit in hits:
            print(f"{hit.file}:{hit.line_no} [{hit.pattern}] {hit.line}")
        return 1
    print("No suppression markers found.")
    return 0


def build_tools(
    targets: list[str],
    mypy_targets: list[str],
    fix: bool,
    optional: bool,
    pip_audit_verbose: bool,
) -> list[ToolRun]:
    """Build the ordered set of quality tools to execute."""
    tools: list[ToolRun] = []

    # Ruff: format + lint
    if fix:
        tools.append(
            ToolRun(
                name="ruff format",
                command=["ruff", "format"] + targets,
                install_hint="python -m pip install -U ruff",
            )
        )
        tools.append(
            ToolRun(
                name="ruff check (fix)",
                command=["ruff", "check", "--fix"] + targets,
                install_hint="python -m pip install -U ruff",
            )
        )
    else:
        tools.append(
            ToolRun(
                name="ruff format (check)",
                command=["ruff", "format", "--check"] + targets,
                install_hint="python -m pip install -U ruff",
            )
        )
        tools.append(
            ToolRun(
                name="ruff check",
                command=["ruff", "check"] + targets,
                install_hint="python -m pip install -U ruff",
            )
        )

    # Types
    tools.append(
        ToolRun(
            name="mypy",
            command=["mypy"] + mypy_targets,
            install_hint="python -m pip install -U mypy",
        )
    )
    tools.append(
        ToolRun(
            name="pyright",
            command=["pyright"] + targets,
            install_hint="python -m pip install -U pyright",
        )
    )

    # Tests + coverage (pytest-cov)
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
            command=["bandit", "-q", "-r"] + targets,
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
                command=["vulture"] + targets,
                install_hint="python -m pip install -U vulture",
            )
        )
        tools.append(
            ToolRun(
                name="radon (complexity)",
                command=["radon", "cc", "-s", "-a"] + targets,
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
        print()
        if not targets_for_tools:
            print("ERROR: None of the target directories contain any .py or .pyi files.")
            print("Targets checked:")
            for d in targets:
                print(f"- {d}")
        else:
            print("ERROR: No Python files found for mypy after excludes.")
        return 2

    # Preflight: require every tool that will be run
    tools = build_tools(
        targets=targets_for_tools,
        mypy_targets=mypy_targets,
        fix=args.fix,
        optional=args.optional,
        pip_audit_verbose=args.pip_audit_verbose,
    )
    for tool in tools:
        require_executable(tool.command[0], tool.install_hint)

    results: list[ToolResult] = []
    for tool in tools:
        results.append(run_tool(tool.name, tool.command, cwd=root))

    hits = scan_suppressions(root, targets)

    print()
    print("Summary")
    print("-------")
    any_failed = False
    for res in results:
        status = "OK" if res.ok else f"FAIL ({res.return_code})"
        print(f"{res.name}: {status}")
        if not res.ok:
            any_failed = True

    if hits:
        print()
        print("Suppression markers found")
        print("-------------------------")
        for hit in hits:
            print(f"{hit.file}:{hit.line_no} [{hit.pattern}] {hit.line}")

        if args.fail_on_suppressions:
            any_failed = True

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
