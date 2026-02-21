from __future__ import annotations

import json
from pathlib import Path

from app.mib_dependency_resolver import MibDependencyResolver


def _write_mib(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_find_mib_source_direct_and_recursive(tmp_path: Path) -> None:
    d1 = tmp_path / "mibs_reference"
    d2 = tmp_path / "mibs"
    d3 = tmp_path / "compiled-mibs"
    _write_mib(d1 / "IF-MIB.txt", "IF-MIB DEFINITIONS ::= BEGIN\nEND\n")
    _write_mib(
        d2 / "nested" / "SNMPv2-MIB.mib", "SNMPv2-MIB DEFINITIONS ::= BEGIN\nEND\n"
    )

    resolver = MibDependencyResolver([str(d1), str(d2), str(d3)])

    p1 = resolver._find_mib_source("IF-MIB")
    p2 = resolver._find_mib_source("SNMPv2-MIB")
    p3 = resolver._find_mib_source("MISSING-MIB")

    assert p1 is not None and p1.endswith("IF-MIB.txt")
    assert p2 is not None and p2.endswith("SNMPv2-MIB.mib")
    assert p3 is None


def test_parse_imports_and_missing_file(tmp_path: Path) -> None:
    resolver = MibDependencyResolver([str(tmp_path)])
    mib = tmp_path / "TEST-MIB.txt"
    _write_mib(
        mib,
        """
TEST-MIB DEFINITIONS ::= BEGIN
IMPORTS
  ifIndex FROM IF-MIB,
  sysDescr FROM SNMPv2-MIB;
END
""",
    )

    deps = resolver._parse_imports(str(mib))
    assert deps == {"IF-MIB", "SNMPv2-MIB"}
    assert resolver._parse_imports(str(tmp_path / "nope.mib")) == set()


def test_get_direct_dependencies_uses_cache(tmp_path: Path) -> None:
    mib_dir = tmp_path / "mibs"
    _write_mib(
        mib_dir / "A-MIB.txt",
        "A-MIB DEFINITIONS ::= BEGIN\nIMPORTS x FROM B-MIB;\nEND\n",
    )
    resolver = MibDependencyResolver([str(mib_dir)])

    first = resolver.get_direct_dependencies("A-MIB")
    # mutate on caller side should not affect cache internals
    first.add("X")
    second = resolver.get_direct_dependencies("A-MIB")

    assert second == {"B-MIB"}


def test_get_all_dependencies_transitive_and_cycle(tmp_path: Path) -> None:
    mib_dir = tmp_path / "mibs"
    _write_mib(
        mib_dir / "A-MIB.txt",
        "A-MIB DEFINITIONS ::= BEGIN\nIMPORTS a FROM B-MIB;\nEND\n",
    )
    _write_mib(
        mib_dir / "B-MIB.txt",
        "B-MIB DEFINITIONS ::= BEGIN\nIMPORTS b FROM C-MIB;\nEND\n",
    )
    _write_mib(
        mib_dir / "C-MIB.txt",
        "C-MIB DEFINITIONS ::= BEGIN\nIMPORTS c FROM A-MIB;\nEND\n",
    )
    resolver = MibDependencyResolver([str(mib_dir)])

    all_deps = resolver.get_all_dependencies("A-MIB")
    # Transitive closure includes direct and transitive deps; cycles are handled safely.
    assert "B-MIB" in all_deps
    assert "C-MIB" in all_deps


def test_build_tree_and_configured_summary(tmp_path: Path) -> None:
    mib_dir = tmp_path / "mibs"
    _write_mib(
        mib_dir / "ROOT-MIB.txt",
        "ROOT-MIB DEFINITIONS ::= BEGIN\nIMPORTS x FROM DEP1-MIB, y FROM DEP2-MIB;\nEND\n",
    )
    _write_mib(
        mib_dir / "DEP1-MIB.txt",
        "DEP1-MIB DEFINITIONS ::= BEGIN\nIMPORTS z FROM LEAF-MIB;\nEND\n",
    )
    _write_mib(mib_dir / "DEP2-MIB.txt", "DEP2-MIB DEFINITIONS ::= BEGIN\nEND\n")
    _write_mib(mib_dir / "LEAF-MIB.txt", "LEAF-MIB DEFINITIONS ::= BEGIN\nEND\n")

    resolver = MibDependencyResolver([str(mib_dir)])
    tree = resolver.build_dependency_tree(["ROOT-MIB"])
    info = resolver.get_configured_mibs_with_deps(["ROOT-MIB"])

    assert tree["ROOT-MIB"]["is_configured"] is True
    assert "DEP1-MIB" in tree and tree["DEP1-MIB"]["is_configured"] is False
    assert info["summary"]["configured_count"] == 1
    assert info["summary"]["total_count"] >= 3


def test_mermaid_outputs(tmp_path: Path) -> None:
    mib_dir = tmp_path / "mibs"
    _write_mib(
        mib_dir / "A-MIB.txt",
        "A-MIB DEFINITIONS ::= BEGIN\nIMPORTS x FROM B-MIB;\nEND\n",
    )
    _write_mib(mib_dir / "B-MIB.txt", "B-MIB DEFINITIONS ::= BEGIN\nEND\n")
    resolver = MibDependencyResolver([str(mib_dir)])

    code = resolver.generate_mermaid_diagram(["A-MIB"])
    payload = resolver.generate_mermaid_diagram_json(["A-MIB"])

    assert "graph TD" in code
    assert "A_MIB" in code and "B_MIB" in code
    assert payload["mermaid_code"].startswith("graph TD")
    assert payload["configured_mibs"] == ["A-MIB"]
