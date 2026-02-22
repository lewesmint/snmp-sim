#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "compiled-mibs",
    "compiled-mibs-test",
    "minimal-for-reference",
    "manual-tests",
    "retired",
    "logs",
    "agent-model",
    "agent-model-backups",
    "scripts",
}


@dataclass
class FunctionHotspot:
    path: Path
    name: str
    lineno: int
    end_lineno: int
    length: int
    complexity: int
    branches: int

    @property
    def score(self) -> int:
        return (self.length // 5) + (self.complexity * 4) + (self.branches * 2)


@dataclass
class FileHotspot:
    path: Path
    line_count: int
    function_count: int


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.complexity = 1
        self.branches = 0

    def _bump(self, by: int = 1) -> None:
        self.complexity += by
        self.branches += by

    def visit_If(self, node: ast.If) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._bump(len(node.handlers) + (1 if node.finalbody else 0))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self._bump(max(0, len(node.values) - 1))
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._bump()
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._bump(1 + len(node.ifs))
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._bump(max(0, len(node.cases) - 1))
        self.generic_visit(node)


class FunctionCollector(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: list[FunctionHotspot] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._collect(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._collect(node)
        self.generic_visit(node)

    def _collect(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end_lineno = getattr(node, "end_lineno", node.lineno)
        length = max(1, end_lineno - node.lineno + 1)
        visitor = ComplexityVisitor()
        visitor.visit(node)
        self.items.append(
            FunctionHotspot(
                path=self.path,
                name=node.name,
                lineno=node.lineno,
                end_lineno=end_lineno,
                length=length,
                complexity=visitor.complexity,
                branches=visitor.branches,
            )
        )


def analyze_file(path: Path) -> tuple[FileHotspot | None, list[FunctionHotspot]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, []

    line_count = source.count("\n") + (0 if source.endswith("\n") else 1)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return FileHotspot(path=path, line_count=line_count, function_count=0), []

    collector = FunctionCollector(path)
    collector.visit(tree)
    return (
        FileHotspot(
            path=path, line_count=line_count, function_count=len(collector.items)
        ),
        collector.items,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank Python refactor hotspots by size and complexity."
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root to scan.")
    parser.add_argument(
        "--top-files", type=int, default=20, help="Number of files to show."
    )
    parser.add_argument(
        "--top-functions", type=int, default=30, help="Number of functions to show."
    )
    parser.add_argument(
        "--min-function-lines", type=int, default=40, help="Minimum function size."
    )
    parser.add_argument(
        "--min-complexity", type=int, default=10, help="Minimum function complexity."
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files: list[FileHotspot] = []
    functions: list[FunctionHotspot] = []

    for file_path in iter_python_files(root):
        file_data, fn_data = analyze_file(file_path)
        if file_data is not None:
            files.append(file_data)
        functions.extend(fn_data)

    files_sorted = sorted(files, key=lambda item: item.line_count, reverse=True)
    functions_sorted = sorted(functions, key=lambda item: item.score, reverse=True)

    print("== Largest Files ==")
    for file_item in files_sorted[: args.top_files]:
        rel = file_item.path.relative_to(root)
        print(
            f"{file_item.line_count:5d} lines  {file_item.function_count:4d} funcs  {rel}"
        )

    print("\n== Function Hotspots ==")
    shown = 0
    for fn_item in functions_sorted:
        if (
            fn_item.length < args.min_function_lines
            and fn_item.complexity < args.min_complexity
        ):
            continue
        rel = fn_item.path.relative_to(root)
        print(
            f"score={fn_item.score:4d}  cc={fn_item.complexity:2d}  branches={fn_item.branches:2d}  "
            f"lines={fn_item.length:4d}  {rel}:{fn_item.lineno}-{fn_item.end_lineno}  {fn_item.name}()"
        )
        shown += 1
        if shown >= args.top_functions:
            break

    if shown == 0:
        print("No functions met current thresholds.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
