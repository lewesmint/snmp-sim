from app.mib_registry import MibRegistry


def test_mib_registry_get_type_and_load_noop() -> None:
    mr = MibRegistry()
    # Initially empty
    assert mr.get_type("1.2.3") == {}

    # Setting internal types and retrieving
    mr.types["1.2.3"] = {"type": "Integer32"}
    assert mr.get_type("1.2.3") == {"type": "Integer32"}

    # load_from_json is a noop placeholder; calling should not raise
    mr.load_from_json("/non/existent/path.json")
