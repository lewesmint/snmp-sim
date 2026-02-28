"""Detect test redundancy by running tests individually and comparing covered lines.

Approach:
1) Collect test node IDs with pytest --collect-only.
2) Run each test in isolation under coverage.
3) Build per-test covered line sets for target source folders.
4) Report tests with zero unique covered lines and exact duplicates.

This is slower than context-based approaches, but robust across coverage/pytest-cov
configuration differences.
"""
# ruff: noqa: INP001

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coverage import CoverageData

SOURCE_PREFIXES = ("app/", "plugins/", "ui/")


@dataclass(frozen=True)
class TestResult:
    nodeid: str
    success: bool
    covered_lines: int
    unique_lines: int = 0
    shared_lines: int = 0


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def _collect_tests(root: Path, collect_args: list[str]) -> list[str]:
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", *collect_args]
    completed = _run_command(command, root)
    if completed.returncode != 0:
        msg = (
            "Failed to collect tests.\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )
        raise RuntimeError(msg)

    nodeids: list[str] = []
    for line in completed.stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if "::" not in candidate:
            continue
        if candidate.startswith("="):
            continue
        nodeids.append(candidate)

    return nodeids


def _read_covered_lines(data_file: Path, root: Path) -> set[tuple[str, int]]:
    data = CoverageData(basename=str(data_file))
    data.read()

    covered: set[tuple[str, int]] = set()
    for file_path in data.measured_files():
        abs_path = Path(file_path).resolve()
        try:
            rel = abs_path.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue

        if not rel.startswith(SOURCE_PREFIXES):
            continue

        lines = data.lines(file_path) or []
        for line_no in lines:
            covered.add((rel, line_no))

    return covered


def _run_single_test(root: Path, nodeid: str, data_file: Path) -> tuple[bool, set[tuple[str, int]]]:
    erase_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "erase",
        f"--data-file={data_file}",
    ]
    _run_command(erase_cmd, root)

    run_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--branch",
        f"--data-file={data_file}",
        "-m",
        "pytest",
        "-q",
        nodeid,
    ]
    completed = _run_command(run_cmd, root)

    success = completed.returncode == 0
    covered = set()
    if data_file.exists():
        covered = _read_covered_lines(data_file, root)

    return success, covered


def _analyze(
    per_test_lines: dict[str, set[tuple[str, int]]],
    failures: list[str],
) -> tuple[list[TestResult], dict[str, list[str]]]:
    line_to_tests: dict[tuple[str, int], set[str]] = defaultdict(set)
    for test_id, lines in per_test_lines.items():
        for key in lines:
            line_to_tests[key].add(test_id)

    results: list[TestResult] = []
    for test_id, lines in per_test_lines.items():
        unique = sum(1 for key in lines if len(line_to_tests[key]) == 1)
        total = len(lines)
        results.append(
            TestResult(
                nodeid=test_id,
                success=test_id not in failures,
                covered_lines=total,
                unique_lines=unique,
                shared_lines=total - unique,
            )
        )

    sig_groups: dict[frozenset[tuple[str, int]], list[str]] = defaultdict(list)
    for test_id, lines in per_test_lines.items():
        sig_groups[frozenset(lines)].append(test_id)

    duplicates = {
        f"group_{idx}": sorted(group)
        for idx, group in enumerate(
            (g for g in sig_groups.values() if len(g) > 1),
            start=1,
        )
    }

    return results, duplicates


def _print_report(results: list[TestResult], duplicates: dict[str, list[str]], top: int) -> None:
    zero_unique = [r for r in results if r.covered_lines > 0 and r.unique_lines == 0 and r.success]
    no_coverage = [r for r in results if r.covered_lines == 0 and r.success]
    failed = [r for r in results if not r.success]

    print("\n=== Test Redundancy Report (isolated coverage) ===")
    print(f"Tests analyzed: {len(results)}")
    print(f"Failed during isolated run: {len(failed)}")
    print(f"No-coverage tests: {len(no_coverage)}")
    print(f"Zero-unique-line candidates: {len(zero_unique)}")
    print(f"Exact duplicate-signature groups: {len(duplicates)}")

    print("\nTop zero-unique-line candidates:")
    for row in sorted(zero_unique, key=lambda x: x.covered_lines, reverse=True)[:top]:
        print(
            f"- {row.nodeid} | covered={row.covered_lines} "
            f"unique={row.unique_lines} shared={row.shared_lines}"
        )

    if duplicates:
        print("\nExact duplicate-signature groups (first 10):")
        for gid, tests in list(duplicates.items())[:10]:
            print(f"- {gid}: {len(tests)} tests")
            for test in tests[:8]:
                print(f"    - {test}")
            if len(tests) > 8:
                print(f"    - ... and {len(tests) - 8} more")


def _write_json(output_path: Path, results: list[TestResult], duplicates: dict[str, list[str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "summary": {
            "tests_analyzed": len(results),
            "failed_isolated": sum(1 for r in results if not r.success),
            "no_coverage": sum(1 for r in results if r.success and r.covered_lines == 0),
            "zero_unique": sum(
                1
                for r in results
                if r.success and r.covered_lines > 0 and r.unique_lines == 0
            ),
            "duplicate_groups": len(duplicates),
        },
        "results": [
            {
                "nodeid": r.nodeid,
                "success": r.success,
                "covered_lines": r.covered_lines,
                "unique_lines": r.unique_lines,
                "shared_lines": r.shared_lines,
            }
            for r in sorted(results, key=lambda x: x.nodeid)
        ],
        "duplicate_groups": duplicates,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-tests",
        type=int,
        default=0,
        help="Analyze only the first N collected tests (0 means all).",
    )
    parser.add_argument(
        "--collect-args",
        nargs="*",
        default=[],
        help="Arguments for pytest collection (e.g. tests/unit).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Top zero-unique candidates to print.",
    )
    parser.add_argument(
        "--json-out",
        default="logs/test_redundancy_isolation.json",
        help="Path for JSON output report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = _project_root()

    try:
        nodeids = _collect_tests(root, args.collect_args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.max_tests and args.max_tests > 0:
        nodeids = nodeids[: args.max_tests]

    if not nodeids:
        print("No tests collected.", file=sys.stderr)
        return 2

    data_file = root / ".coverage.redundancy.isolated"
    if data_file.exists():
        data_file.unlink()

    per_test_lines: dict[str, set[tuple[str, int]]] = {}
    failed: list[str] = []

    total = len(nodeids)
    for idx, nodeid in enumerate(nodeids, start=1):
        success, covered = _run_single_test(root, nodeid, data_file)
        per_test_lines[nodeid] = covered
        if not success:
            failed.append(nodeid)

        if idx % 25 == 0 or idx == total:
            print(f"Progress: {idx}/{total} tests analyzed")

    results, duplicates = _analyze(per_test_lines, failed)
    _print_report(results, duplicates, args.top)

    output_path = (root / args.json_out).resolve()
    _write_json(output_path, results, duplicates)
    print(f"\nWrote JSON report to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
