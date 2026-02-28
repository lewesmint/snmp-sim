"""Generate a redundancy report based on per-test coverage contexts.

This script identifies tests that appear redundant from a line-coverage perspective:
- tests with zero unique covered lines
- groups of tests with identical covered-line signatures

It can optionally run pytest with ``--cov-context=test`` to produce context-aware
coverage data before analysis.
"""
# ruff: noqa: INP001
# pylint: disable=line-too-long,missing-class-docstring,missing-function-docstring

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coverage import CoverageData


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_context(raw_context: str) -> str:
    """Normalize a coverage context string to test node id when possible."""
    # pytest-cov contexts are usually like:
    #   tests/unit/test_x.py::test_name|run
    # keep only the test node-id part.
    return raw_context.split("|", maxsplit=1)[0]


def _is_test_context(raw_context: str) -> bool:
    context = _normalize_context(raw_context)
    if not context:
        return False
    return (
        "::" in context
        or ".test_" in context
        or context.startswith("test_")
        or "/tests/" in context
        or "tests/" in context
    )


@dataclass(frozen=True)
class Candidate:
    test_id: str
    covered_lines: int
    unique_lines: int
    shared_lines: int


def _run_pytest_for_contexts(pytest_args: list[str], root: Path) -> int:
    # Isolate this run's coverage artifacts to avoid schema/version conflicts.
    for stale in root.glob(".coverage.redundancy*"):
        if stale.is_file():
            stale.unlink()

    coverage_file = str(root / ".coverage.redundancy")
    env = os.environ.copy()
    rcfile_path = root / ".coverage.redundancy.rc"
    rcfile_path.write_text(
        "\n".join(
            [
                "[run]",
                "branch = true",
                "dynamic_context = test_function",
                "source = app,plugins,ui",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    erase_command = [
        sys.executable,
        "-m",
        "coverage",
        "erase",
        f"--rcfile={rcfile_path}",
        f"--data-file={coverage_file}",
    ]
    subprocess.run(erase_command, cwd=root, check=False, env=env)  # noqa: S603

    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--rcfile={rcfile_path}",
        f"--data-file={coverage_file}",
        "-m",
        "pytest",
        *pytest_args,
    ]
    try:
        completed = subprocess.run(command, cwd=root, check=False, env=env)  # noqa: S603
        return completed.returncode
    finally:
        if rcfile_path.exists():
            rcfile_path.unlink()


def _load_context_data(coverage_file: Path) -> tuple[dict[str, set[tuple[str, int]]], list[str]]:
    data = CoverageData()
    data.read()

    if not coverage_file.exists():
        msg = f"Coverage data file not found: {coverage_file}"
        raise FileNotFoundError(msg)

    measured_files = sorted(data.measured_files())
    measured_contexts = sorted(data.measured_contexts())

    test_contexts = [_normalize_context(ctx) for ctx in measured_contexts if _is_test_context(ctx)]
    if not test_contexts:
        return {}, measured_files

    # multiple raw contexts can map to same test id; aggregate per normalized id
    per_test_lines: dict[str, set[tuple[str, int]]] = defaultdict(set)

    # query by raw context to preserve exact database matching
    for raw_context in measured_contexts:
        if not _is_test_context(raw_context):
            continue

        test_id = _normalize_context(raw_context)
        data.set_query_contexts([raw_context])

        for file_path in measured_files:
            rel_path = str(Path(file_path).resolve().relative_to(_project_root().resolve()))
            lines = data.lines(file_path) or []
            for line_no in lines:
                per_test_lines[test_id].add((rel_path, line_no))

    data.set_query_contexts(None)
    return dict(per_test_lines), measured_files


def _build_candidates(per_test_lines: dict[str, set[tuple[str, int]]]) -> tuple[list[Candidate], dict[str, list[str]]]:
    line_to_tests: dict[tuple[str, int], set[str]] = defaultdict(set)
    for test_id, covered in per_test_lines.items():
        for key in covered:
            line_to_tests[key].add(test_id)

    candidates: list[Candidate] = []
    for test_id, covered in per_test_lines.items():
        unique = sum(1 for key in covered if len(line_to_tests[key]) == 1)
        total = len(covered)
        shared = total - unique
        candidates.append(
            Candidate(
                test_id=test_id,
                covered_lines=total,
                unique_lines=unique,
                shared_lines=shared,
            )
        )

    # exact-signature groups (strong duplicate indicator)
    signature_groups: dict[frozenset[tuple[str, int]], list[str]] = defaultdict(list)
    for test_id, covered in per_test_lines.items():
        signature_groups[frozenset(covered)].append(test_id)

    duplicate_groups = {
        f"group_{idx}": sorted(tests)
        for idx, tests in enumerate(
            (tests for tests in signature_groups.values() if len(tests) > 1),
            start=1,
        )
    }

    return candidates, duplicate_groups


def _print_report(candidates: list[Candidate], duplicate_groups: dict[str, list[str]], top_n: int) -> None:
    total_tests = len(candidates)
    no_coverage = [c for c in candidates if c.covered_lines == 0]
    zero_unique = [c for c in candidates if c.covered_lines > 0 and c.unique_lines == 0]

    print("\n=== Test Redundancy Report (line-coverage based) ===")
    print(f"Total tests analyzed: {total_tests}")
    print(f"Tests with no measured line coverage: {len(no_coverage)}")
    print(f"Tests with zero unique covered lines: {len(zero_unique)}")
    print(f"Exact duplicate-signature groups: {len(duplicate_groups)}")

    print("\nTop zero-unique-line candidates:")
    for item in sorted(zero_unique, key=lambda c: c.covered_lines, reverse=True)[:top_n]:
        print(
            f"- {item.test_id} | covered={item.covered_lines} "
            f"unique={item.unique_lines} shared={item.shared_lines}"
        )

    if duplicate_groups:
        print("\nExact duplicate-signature groups (first 10):")
        for group_id, tests in list(duplicate_groups.items())[:10]:
            print(f"- {group_id}: {len(tests)} tests")
            for test_id in tests[:8]:
                print(f"    - {test_id}")
            if len(tests) > 8:
                print(f"    - ... and {len(tests) - 8} more")

    print(
        "\nNote: zero-unique-line does not automatically mean removable; "
        "the test may still improve readability or assertion quality."
    )


def _write_json_report(
    output_path: Path,
    candidates: list[Candidate],
    duplicate_groups: dict[str, list[str]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "summary": {
            "total_tests": len(candidates),
            "no_coverage": sum(1 for c in candidates if c.covered_lines == 0),
            "zero_unique_lines": sum(
                1 for c in candidates if c.covered_lines > 0 and c.unique_lines == 0
            ),
            "duplicate_signature_groups": len(duplicate_groups),
        },
        "zero_unique_candidates": [
            {
                "test_id": c.test_id,
                "covered_lines": c.covered_lines,
                "unique_lines": c.unique_lines,
                "shared_lines": c.shared_lines,
            }
            for c in sorted(candidates, key=lambda x: (x.unique_lines, -x.covered_lines))
            if c.covered_lines > 0 and c.unique_lines == 0
        ],
        "no_coverage_tests": [
            c.test_id for c in sorted(candidates, key=lambda x: x.test_id) if c.covered_lines == 0
        ],
        "duplicate_signature_groups": duplicate_groups,
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run pytest with per-test coverage contexts before analysis.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional args passed to pytest when --run is used.",
    )
    parser.add_argument(
        "--coverage-file",
        default=".coverage.redundancy",
        help="Coverage data file path (default: .coverage.redundancy).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of top zero-unique candidates to print.",
    )
    parser.add_argument(
        "--json-out",
        default="logs/test_redundancy_report.json",
        help="Path to write JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = _project_root()

    if args.run:
        code = _run_pytest_for_contexts(args.pytest_args, root)
        if code != 0:
            print("pytest run failed; not generating redundancy report.", file=sys.stderr)
            return code

    coverage_path = (root / args.coverage_file).resolve()

    try:
        per_test_lines, _ = _load_context_data(coverage_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not per_test_lines:
        print(
            "No test contexts found in coverage data. "
            "Run with --run (or run pytest with --cov-context=test).",
            file=sys.stderr,
        )
        return 2

    candidates, duplicate_groups = _build_candidates(per_test_lines)
    _print_report(candidates, duplicate_groups, args.top)

    json_out = (root / args.json_out).resolve()
    _write_json_report(json_out, candidates, duplicate_groups)
    print(f"\nWrote JSON report to: {json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
