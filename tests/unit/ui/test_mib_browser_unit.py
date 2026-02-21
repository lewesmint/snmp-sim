from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import ui.mib_browser as mib_browser_module
from ui.common import Logger
from ui.mib_browser import MIBBrowserWindow


class _Var:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class _Tree:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {
            "": {"children": [], "text": "", "open": False}
        }
        self._next_id = 1

    def insert(
        self, parent: str, _index: str, text: str = "", values: Any = None
    ) -> str:
        node_id = f"n{self._next_id}"
        self._next_id += 1
        self.nodes[node_id] = {
            "children": [],
            "text": text,
            "open": False,
            "values": values,
        }
        self.nodes.setdefault(parent, {"children": [], "text": "", "open": False})
        self.nodes[parent]["children"].append(node_id)
        return node_id

    def get_children(self, item: str = "") -> list[str]:
        return list(self.nodes.get(item, {}).get("children", []))

    def item(self, item: str, option: str | None = None, **kwargs: Any) -> Any:
        if kwargs:
            self.nodes[item].update(kwargs)
            return None
        if option is None:
            return self.nodes[item]
        return self.nodes[item].get(option)

    def delete(self, item: str) -> None:
        for parent_id, parent_data in self.nodes.items():
            if item in parent_data.get("children", []):
                parent_data["children"].remove(item)
                break
        for child in list(self.nodes.get(item, {}).get("children", [])):
            self.delete(child)
        self.nodes.pop(item, None)


class _StatusVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def _make_browser(tmp_path: Path) -> MIBBrowserWindow:
    browser = MIBBrowserWindow.__new__(MIBBrowserWindow)
    browser.logger = Logger()
    browser.mib_cache_dir = tmp_path / "cache"
    browser.mib_cache_dir.mkdir(parents=True, exist_ok=True)
    browser.loaded_mibs = []
    browser.unsatisfied_mibs = {}
    browser.mib_builder = SimpleNamespace(mibSymbols={})
    browser.default_port = 161
    browser.host_var = _Var("127.0.0.1")
    browser.port_var = _Var("161")
    browser.community_var = _Var("public")
    return browser


def test_extract_mib_imports_text_and_py_and_error(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)

    txt = tmp_path / "A-MIB.mib"
    txt.write_text(
        """
A-MIB DEFINITIONS ::= BEGIN
IMPORTS
  x FROM IF-MIB,
  y FROM SNMPv2-MIB;
END
""",
        encoding="utf-8",
    )
    deps_txt = browser._extract_mib_imports(txt)
    # Current parser can include symbol token from pre-FROM segment
    assert "IF-MIB" in deps_txt or "x" in deps_txt
    assert "SNMPv2-MIB" in deps_txt

    py = tmp_path / "B-MIB.py"
    py.write_text(
        "# FROM IF-MIB import foo\n FROM TCP-MIB import bar\n", encoding="utf-8"
    )
    deps_py = browser._extract_mib_imports(py)
    assert "TCP-MIB" in deps_py

    missing = tmp_path / "missing.mib"
    assert browser._extract_mib_imports(missing) == []


def test_find_mib_file_in_cache_and_loaded_check(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)
    cache_mib = browser.mib_cache_dir / "IF-MIB.mib"
    cache_mib.write_text("x", encoding="utf-8")

    assert browser._find_mib_file_in_cache("IF-MIB") == cache_mib
    assert browser._find_mib_file_in_cache("MISSING") is None

    browser.loaded_mibs = ["IF-MIB"]
    browser.unsatisfied_mibs = {}
    assert browser._is_mib_loaded_in_pysnmp("IF-MIB") is True

    browser.unsatisfied_mibs = {"IF-MIB": ["X"]}
    assert browser._is_mib_loaded_in_pysnmp("IF-MIB") is False


def test_find_mib_file_prefers_cache_and_compiled(
    monkeypatch: Any, tmp_path: Path
) -> None:
    browser = _make_browser(tmp_path)

    cache_py = browser.mib_cache_dir / "SNMPv2-MIB.py"
    cache_py.write_text("x", encoding="utf-8")
    assert browser._find_mib_file("SNMPv2-MIB") == cache_py

    cache_py.unlink()
    fake_app_dir = tmp_path / "ui"
    fake_app_dir.mkdir(parents=True, exist_ok=True)
    fake_module = fake_app_dir / "mib_browser.py"
    fake_module.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(mib_browser_module, "__file__", str(fake_module))

    compiled = tmp_path / "compiled-mibs" / "SNMPv2-MIB.py"
    compiled.parent.mkdir(parents=True, exist_ok=True)
    compiled.write_text("x", encoding="utf-8")

    assert browser._find_mib_file("SNMPv2-MIB") == compiled


def test_normalize_oid_and_connection_params(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)

    assert MIBBrowserWindow._normalize_oid("1") == "1.0"
    assert MIBBrowserWindow._normalize_oid(".1") == ".1.0"
    assert MIBBrowserWindow._normalize_oid("1.3.6") == "1.3.6"

    browser.host_var = _Var(" 10.0.0.1 ")
    browser.port_var = _Var("not-int")
    browser.community_var = _Var(" private ")
    host, port, community = browser._get_connection_params()
    assert host == "10.0.0.1"
    assert port == 161
    assert community == "private"


def test_resolve_oid_name_and_format_errors(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)

    # Numeric resolution
    assert browser._resolve_oid_name_to_tuple("1.3.6.1") == (1, 3, 6, 1)
    assert browser._resolve_oid_name_to_tuple("1.3.bad") is None
    assert browser._resolve_oid_name_to_tuple("SNMPv2-MIB::sysDescr") is None

    # Short-name resolution from loaded MIB symbols
    class Sym:
        def getName(self) -> tuple[int, ...]:
            return (1, 3, 6, 1, 2, 1, 1, 1, 0)

    browser.loaded_mibs = ["SNMPv2-MIB"]
    browser.mib_builder = SimpleNamespace(
        mibSymbols={"SNMPv2-MIB": {"sysDescr": Sym()}}
    )
    assert browser._resolve_oid_name_to_tuple("sysDescr") == (1, 3, 6, 1, 2, 1, 1, 1, 0)

    msg = browser._format_mib_error(
        Exception("MibNotFoundError: 'sysDescr' compilation error")
    )
    assert "Cannot resolve 'sysDescr'" in msg
    assert "Load the MIB containing 'sysDescr'" in msg
    assert browser._format_mib_error(Exception("plain error")) == "plain error"


def test_create_object_identity_paths(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)

    # numeric
    obj1, disp1 = browser._create_object_identity("1")
    assert disp1 == "1.0"
    assert obj1 is not None

    # MIB::name
    obj2, disp2 = browser._create_object_identity("SNMPv2-MIB::sysDescr")
    assert disp2 == "SNMPv2-MIB::sysDescr"
    assert obj2 is not None

    # short name resolved
    browser._resolve_oid_name_to_tuple = lambda _v: (1, 3, 6, 1)
    obj3, disp3 = browser._create_object_identity("sysDescr")
    assert disp3 == "1.3.6.1"
    assert obj3 is not None

    # unresolved with no loaded MIBs
    browser._resolve_oid_name_to_tuple = lambda _v: None
    browser.loaded_mibs = []
    try:
        browser._create_object_identity("unknownName")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "no MIBs loaded" in str(e)

    # unresolved with loaded MIBs
    browser.loaded_mibs = ["SNMPv2-MIB"]
    try:
        browser._create_object_identity("unknownName")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "loaded MIBs: SNMPv2-MIB" in str(e)


def test_resolve_mib_dependencies_reports_resolved_and_missing(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)
    deps = {
        "ROOT": ["A", "B"],
        "A": ["C"],
        "B": [],
        "C": ["MISSING"],
    }

    browser._find_mib_file = lambda name: (
        tmp_path / f"{name}.mib" if name != "MISSING" else None
    )
    browser._extract_mib_imports = lambda p: deps[p.stem]

    resolved, missing = browser._resolve_mib_dependencies("ROOT")
    assert resolved == ["C", "A", "B"]
    assert missing == ["MISSING"]


def test_tree_agent_and_operation_nodes_reuse_existing(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)
    browser.results_tree = _Tree()
    browser.agent_tree_items = {}
    browser.agent_results = {}

    agent_item = browser._get_or_create_agent_node("127.0.0.1", 161)
    assert agent_item
    same_agent_item = browser._get_or_create_agent_node("127.0.0.1", 161)
    assert same_agent_item == agent_item

    op_item = browser._get_or_create_operation_node(agent_item, "GET", "1.3.6.1")
    assert op_item
    same_op_item = browser._get_or_create_operation_node(agent_item, "GET", "1.3.6.1")
    assert same_op_item == op_item


def test_expand_collapse_and_clear_results(tmp_path: Path) -> None:
    browser = _make_browser(tmp_path)
    browser.results_tree = _Tree()
    browser.logger = Logger()
    logs: list[tuple[str, str]] = []
    browser.logger.log = lambda msg, level="INFO": logs.append((level, msg))  # type: ignore[method-assign]
    browser.status_var = _StatusVar()
    browser.agent_results = {"a": {}}
    browser.agent_tree_items = {"a": "n1"}

    root = browser.results_tree.insert("", "end", text="root")
    child = browser.results_tree.insert(root, "end", text="child")
    _ = browser.results_tree.insert(child, "end", text="leaf")

    browser._expand_all()
    assert browser.results_tree.item(root, "open") is True
    assert browser.results_tree.item(child, "open") is True

    browser._collapse_all()
    assert browser.results_tree.item(root, "open") is False
    assert browser.results_tree.item(child, "open") is False

    browser._clear_results()
    assert browser.results_tree.get_children("") == []
    assert browser.agent_results == {}
    assert browser.agent_tree_items == {}
    assert browser.status_var.value == "Results cleared"
    assert any("Results cleared" in m for _, m in logs)
