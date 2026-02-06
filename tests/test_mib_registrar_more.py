from typing import Any, Iterable, cast

from app.mib_registrar import MibRegistrar

def make_registrar() -> MibRegistrar:
    # Simple fake logger and time
    import logging

    logger = logging.getLogger("test")
    return MibRegistrar(
        mib_builder=None,
        mib_scalar_instance=None,
        mib_table=None,
        mib_table_row=None,
        mib_table_column=None,
        logger=logger,
        start_time=0.0,
    )


def test_find_table_related_objects() -> None:
    reg = make_registrar()
    mib_json = {
        "MyTable": {"oid": [1]},
        "MyTableEntry": {"oid": [1, 2]},
        "col1": {"oid": [1, 2, 3]},
        "other": 5,
    }
    table_related = reg._find_table_related_objects(mib_json)
    assert "MyTable" in table_related
    assert "MyTableEntry" in table_related
    assert "col1" in table_related


def test_decode_value_hex_and_unknown() -> None:
    reg = make_registrar()
    v = {"value": "\\xAA\\xBB", "encoding": "hex"}
    out = reg._decode_value(v)
    assert isinstance(out, (bytes, bytearray))
    v2 = {"value": "zzz", "encoding": "base64"}
    assert reg._decode_value(v2) == "zzz"


def test_build_table_symbols_basic(monkeypatch: Any) -> None:
    reg = make_registrar()

    # Provide minimal implementations for MIB classes
    class FakeTable:
        def __init__(self, oid: Iterable[int]) -> None:
            self.oid = tuple(oid)

    class FakeRow:
        def __init__(self, oid: Iterable[int]) -> None:
            self.oid = tuple(oid)

        def setIndexNames(self, *specs: Any) -> Any:
            return self

    class FakeColumn:
        def __init__(self, oid: Iterable[int], *args: Any, **kwargs: Any) -> None:
            self.oid = tuple(oid)

        def setMaxAccess(self, a: Any) -> Any:
            return self

    class FakeInstance:
        def __init__(self, oid: Iterable[int], idx: Iterable[int], val: Any) -> None:
            self.oid = tuple(oid)
            self.idx = tuple(idx)
            self.val = val

    # Monkeypatch registrar types and helpers
    reg.MibTable = FakeTable
    reg.MibTableRow = FakeRow
    reg.MibTableColumn = FakeColumn
    reg.MibScalarInstance = FakeInstance
    # simplify _get_pysnmp_type to return int type for instantiation
    def fake_get_pysnmp_type(self: MibRegistrar, base_type: str) -> Any:
        return int
    monkeypatch.setattr(MibRegistrar, "_get_pysnmp_type", fake_get_pysnmp_type)
    # ensure encode_value is identity
    import app.mib_registrar as mr
    monkeypatch.setattr(mr, "encode_value", lambda v, t: v)

    # Construct mib_json describing a table, entry, and a column
    mib_json = {
        # Include a single row so instances are created
        "MyTable": {"oid": [1], "rows": [{"col1": 1}]},
        "MyEntry": {"oid": [1, 2], "indexes": ["col1"]},
        "col1": {"oid": [1, 2, 3], "type": "Integer32", "access": "read-only"},
    }

    symbols = reg._build_table_symbols("MIB", "MyTable", cast(dict[str, Any], mib_json["MyTable"]), mib_json, {"Integer32": {"base_type": "Integer"}})
    # Expect table and entry and instance keys
    assert "MyTable" in symbols
    # The registrar uses the defined Entry object name (e.g. 'MyEntry')
    assert "MyEntry" in symbols
    # instance name should be present for column
    assert any(k.startswith("col1Inst") for k in symbols.keys())


def test_get_pysnmp_type_uses_builder(_monkeypatch: Any) -> None:
    reg = make_registrar()

    class FakeType:
        pass

    class FakeBuilder:
        def import_symbols(self, _mod: str, _name: str) -> list[type]:
            return [FakeType]

    reg.mib_builder = FakeBuilder()
    t = reg._get_pysnmp_type("Whatever")
    assert t is FakeType
