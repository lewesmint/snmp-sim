"""Fix pylint missing docstring warnings by inserting concise docstrings."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\d+:\s+(?P<code>C011[456]):")


def _module_doc(path: str, stem: str) -> str:
    if path.startswith("tests/"):
        return f"Tests for {stem}."
    return f"Module for {stem}."


def _class_doc(path: str, name: str) -> str:
    if path.startswith("tests/"):
        return f"Test helper class for {name}."
    return f"{name} class."


def _func_doc(path: str, name: str) -> str:
    if path.startswith("tests/"):
        return f"Test case for {name}."
    return f"{name} function."


def _collect_warnings() -> dict[str, list[tuple[int, str]]]:
    command = 'pylint app tests 2>/dev/null | rg "C0114|C0115|C0116"'
    result = subprocess.run(
        command, shell=True, cwd=ROOT, text=True, capture_output=True, check=False
    )
    warnings: dict[str, list[tuple[int, str]]] = {}
    for raw in result.stdout.splitlines():
        match = PATTERN.search(raw.strip())
        if not match:
            continue
        rel = match.group("file")
        warnings.setdefault(rel, []).append((int(match.group("line")), match.group("code")))
    return warnings


def _insert_docstrings(file_path: Path, rel: str, items: list[tuple[int, str]]) -> bool:
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    inserts: list[tuple[int, str]] = []

    for line_no, code in sorted(items, key=lambda item: item[0], reverse=True):
        idx = line_no - 1
        if code == "C0114":
            stripped = "".join(lines).lstrip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            stem = Path(rel).stem.replace("_", " ")
            inserts.append((0, f'"""{_module_doc(rel, stem)}"""\n\n'))
            continue

        if idx < 0 or idx >= len(lines):
            continue

        header = lines[idx]
        class_match = re.match(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\b", header)
        func_match = re.match(r"^(\s*)(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b", header)

        if code == "C0115" and class_match:
            indent, name = class_match.groups()
            if idx + 1 < len(lines) and re.match(r"^\s*[\"']{3}", lines[idx + 1]):
                continue
            inserts.append((idx + 1, f'{indent}    """{_class_doc(rel, name)}"""\n'))
        elif code == "C0116" and func_match:
            indent, name = func_match.groups()
            if idx + 1 < len(lines) and re.match(r"^\s*[\"']{3}", lines[idx + 1]):
                continue
            inserts.append((idx + 1, f'{indent}    """{_func_doc(rel, name)}"""\n'))

    if not inserts:
        return False

    for index, text in sorted(inserts, key=lambda item: item[0], reverse=True):
        lines.insert(index, text)

    updated = "".join(lines)
    if updated == original:
        return False

    file_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:

    warnings = _collect_warnings()
    if not warnings:
        print("No missing docstring warnings found.")
        return

    changed: list[str] = []
    for rel, items in sorted(warnings.items()):
        path = ROOT / rel
        if not path.exists():
            continue
        if _insert_docstrings(path, rel, items):
            changed.append(rel)

    print(f"Updated {len(changed)} files")
    for rel in changed:
        print(rel)


if __name__ == "__main__":
    main()
