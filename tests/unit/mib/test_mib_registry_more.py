from pathlib import Path
from app.mib_registry import MibRegistry


def test_get_type_empty() -> None:
    r = MibRegistry()
    # unknown oid returns empty dict
    assert r.get_type("1.3.6.1.4.1") == {}


def test_set_and_get_type() -> None:
    r = MibRegistry()
    r.types["1.2.3"] = {"name": "TestType", "syntax": "Integer"}
    t = r.get_type("1.2.3")
    assert isinstance(t, dict)
    assert t["name"] == "TestType"
    assert t["syntax"] == "Integer"


def test_load_from_json_noop(tmp_path: Path) -> None:
    r = MibRegistry()
    # load_from_json is currently a no-op; calling should not raise
    p = tmp_path / "fake.json"
    p.write_text("{}")
    r.load_from_json(str(p))
    # registry still empty
    assert r.types == {}
