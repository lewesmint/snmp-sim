"""Fix pylint missing docstring warnings by inserting concise docstrings."""
# ruff: noqa: INP001

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\d+:\s+(?P<code>C011[456]):")
logger = logging.getLogger(__name__)


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
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pylint", "app", "tests"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    warnings: dict[str, list[tuple[int, str]]] = {}
    for raw in result.stdout.splitlines() + result.stderr.splitlines():
        match = PATTERN.search(raw.strip())
        if not match:
            continue
        rel = match.group("file")
        warnings.setdefault(rel, []).append((int(match.group("line")), match.group("code")))
    return warnings


def _insert_docstrings(  # pylint: disable=too-many-locals
    file_path: Path,
    rel: str,
    items: list[tuple[int, str]],
) -> bool:
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    inserts: list[tuple[int, str]] = []

    for line_no, code in sorted(items, key=lambda item: item[0], reverse=True):
        idx = line_no - 1
        if code == "C0114":
            stripped = "".join(lines).lstrip()
            if stripped.startswith(('"""', "'''")):
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
    """Collect pylint docstring warnings and insert generated docstrings."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    warnings = _collect_warnings()
    if not warnings:
        logger.info("No missing docstring warnings found.")
        return

    changed: list[str] = []
    for rel, items in sorted(warnings.items()):
        path = ROOT / rel
        if not path.exists():
            continue
        if _insert_docstrings(path, rel, items):
            changed.append(rel)

    logger.info("Updated %s files", len(changed))
    for rel in changed:
        logger.info("%s", rel)


if __name__ == "__main__":
    main()
