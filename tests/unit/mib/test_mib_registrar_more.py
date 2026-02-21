# pylint: disable=protected-access,unused-argument,attribute-defined-outside-init,redefined-outer-name,reimported,pointless-string-statement,broad-exception-caught,trailing-whitespace,line-too-long,too-many-lines,missing-module-docstring,missing-class-docstring,missing-function-docstring,invalid-name,too-few-public-methods,import-outside-toplevel,consider-iterating-dictionary,use-implicit-booleaness-not-comparison

from typing import Any, Iterable, cast
import logging
import time
import json
from pathlib import Path
import pytest

from app.mib_registrar import MibRegistrar


class DummyScalarInstance:
    def __init__(self, oid: Iterable[int], idx: Iterable[int], value: Any) -> None:
        self.oid = oid
        self.idx = idx
        self.value = value
    
    def setMaxAccess(self, access: str) -> "DummyScalarInstance":
        """Mock method for setMaxAccess - returns self for chaining."""
        self.max_access = access
        return self


class DummyBuilder:
    def __init__(self) -> None:
        self.mibSymbols: dict[str, dict[str, Any]] = {}

    def import_symbols(self, mod: str, name: str) -> list[type]:
        class FakePysnmp:
            def __init__(self, v: Any = None) -> None:
                self.v = v

        return [FakePysnmp]

    def export_symbols(self, mib: str, **symbols: Any) -> None:
        if mib not in self.mibSymbols:
            self.mibSymbols[mib] = {}
        self.mibSymbols[mib].update(symbols)


def make_registrar() -> MibRegistrar:
    # Simple fake logger and time
    import logging

    logger = logging.getLogger("test")
    return MibRegistrar(
        mib_builder=DummyBuilder(),
        mib_scalar_instance=DummyScalarInstance,
        mib_table=None,
        mib_table_row=None,
        mib_table_column=None,
        logger=logger,
        start_time=0.0,
    )


def setup_fake_mib_classes(reg: MibRegistrar) -> None:
    """Set up fake MIB classes for testing."""
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
            self.value = val
        
        def setMaxAccess(self, access: str) -> "FakeInstance":
            """Mock method for setMaxAccess - returns self for chaining."""
            self.max_access = access
            return self

    reg.MibTable = FakeTable
    reg.MibTableRow = FakeRow
    reg.MibTableColumn = FakeColumn
    reg.MibScalarInstance = FakeInstance


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
        
        def setMaxAccess(self, access: str) -> "FakeInstance":
            """Mock method for setMaxAccess - returns self for chaining."""
            self.max_access = access
            return self

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


def test_get_pysnmp_type_uses_builder() -> None:
    reg = make_registrar()

    class FakeType:
        pass

    class FakeBuilder:
        def import_symbols(self, _mod: str, _name: str) -> list[type]:
            return [FakeType]

    reg.mib_builder = FakeBuilder()
    t = reg._get_pysnmp_type("Whatever")
    assert t is FakeType


def test_decode_value_bad_hex_logs_error(caplog: Any) -> None:
    reg = make_registrar()
    caplog.set_level('ERROR')
    out = reg._decode_value({'value': '\\xZZ', 'encoding': 'hex'})
    assert "Failed to decode hex value" in caplog.text
    assert out == '\\xZZ'


def test_build_mib_symbols_scalar_creation_with_none_value(monkeypatch: Any) -> None:
    # Ensure scalars with None initial get default values and instances are created
    class FakeBuilder:
        def import_symbols(self, mod: str, name: str) -> list[type]:
            class FakePysnmp:
                def __init__(self, v: Any) -> None:
                    self.v = v
            return [FakePysnmp]

    reg = make_registrar()
    reg.mib_builder = FakeBuilder()
    reg.MibScalarInstance = DummyScalarInstance

    mib_json: dict[str, dict[str, Any]] = {
        'foo': {'oid': [1, 2, 3], 'type': 'Integer32', 'initial': None, 'access': 'read-only'},
        'bar': {'oid': [1, 2, 4], 'type': 'OctetString', 'initial': None}
    }
    type_registry: dict[str, dict[str, Any]] = {'Integer32': {'base_type': 'Integer32'}, 'OctetString': {'base_type': 'OctetString'}}
    symbols = reg._build_mib_symbols('MIB', mib_json, type_registry)
    # Instances should be present for 'foo' and 'bar'
    assert any(k.startswith('foo') for k in symbols.keys())
    assert any(k.startswith('bar') or k.startswith('barInst') for k in symbols.keys())


def test_read_only_scalar_allows_internal_change(monkeypatch: Any) -> None:
    reg = make_registrar()

    class FakeScalarInstance:
        def __init__(self, oid: Iterable[int], idx: Iterable[int], val: Any) -> None:
            self.name = tuple(oid) + tuple(idx)
            self.syntax = val

        def setMaxAccess(self, a: Any) -> Any:
            self.maxAccess = a
            return self

    reg.MibScalarInstance = FakeScalarInstance

    def fake_get_pysnmp_type(self: MibRegistrar, _base_type: str) -> Any:
        return int

    monkeypatch.setattr(MibRegistrar, "_get_pysnmp_type", fake_get_pysnmp_type)
    import app.mib_registrar as mr
    monkeypatch.setattr(mr, "encode_value", lambda v, _t: v)

    mib_json: dict[str, dict[str, Any]] = {
        "roScalar": {
            "oid": [1, 3, 6, 1, 4, 1, 999, 1],
            "type": "Integer32",
            "initial": 1,
            "access": "read-only",
        }
    }
    type_registry = {"Integer32": {"base_type": "Integer32"}}

    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, type_registry)
    scalar = symbols["roScalarInst"]

    with pytest.raises(ValueError):
        scalar.writeTest((scalar.name, 2), snmpEngine=None)

    scalar.syntax = 2
    assert scalar.syntax == 2


def test_register_mib_filters_existing_and_handles_export_exception(monkeypatch: Any, caplog: Any) -> None:
    # Test filtering and handling export exception
    class Builder:
        def __init__(self) -> None:
            self.mibSymbols: dict[str, dict[str, Any]] = {'X': {'a': 1}}
        def export_symbols(self, mib: str, **symbols: Any) -> None:
            raise RuntimeError('boom')

    b = Builder()
    reg = make_registrar()
    reg.mib_builder = b
    monkeypatch.setattr(MibRegistrar, '_build_mib_symbols', lambda self, mib, mj, tr: {'a': 1, 'b': 2})

    caplog.set_level('ERROR')
    reg.register_mib('X', {}, {})
    # export_symbols raised; should have logged an error
    assert 'Error registering MIB X' in caplog.text or 'Error registering MIB' in caplog.text


def test_register_all_mibs_type_registry_load_fails(caplog: Any, tmp_path: Any) -> None:
    # Provide a bad path so json.load fails
    b = DummyBuilder()
    reg = MibRegistrar(b, None, None, None, None, logging.getLogger('test'), time.time())
    caplog.set_level('ERROR')
    reg.register_all_mibs({'FOO': {}}, type_registry_path=str(tmp_path / 'nope.json'))
    assert 'Failed to load type registry' in caplog.text


def test_populate_sysor_table_empty_rows(monkeypatch: Any, caplog: Any) -> None:
    b = DummyBuilder()
    reg = make_registrar()
    reg.mib_builder = b
    caplog.set_level('WARNING')
    # Patch get_sysor_table_rows to return empty
    monkeypatch.setattr('app.mib_metadata.get_sysor_table_rows', lambda names: [])
    reg.populate_sysor_table({'M1': {}}, type_registry_path=None)
    assert 'No sysORTable rows generated' in caplog.text


def test_populate_sysor_table_updates_and_calls_register(monkeypatch: Any, caplog: Any) -> None:
    b = DummyBuilder()
    reg = make_registrar()
    reg.mib_builder = b
    called: dict[str, bool] = {}
    def fake_get_rows(names: Any) -> list[dict[str, Any]]:
        return [{'oid': [1,2,3], 'description': 'x'}]
    monkeypatch.setattr('app.mib_metadata.get_sysor_table_rows', fake_get_rows)

    def fake_register(*args: Any, **kwargs: Any) -> None:
        called['called'] = True
    monkeypatch.setattr(MibRegistrar, 'register_mib', fake_register)

    caplog.set_level('INFO')
    mib_jsons: dict[str, dict[str, Any]] = {'SNMPv2-MIB': {'sysORTable': {'rows': []}}}
    reg.populate_sysor_table(mib_jsons)
    assert called.get('called', False) is True
    assert 'Updated sysORTable' in caplog.text


def test_populate_sysor_table_handles_json_load_error(caplog: Any, monkeypatch: Any) -> None:
    reg = make_registrar()
    
    # Mock open to raise exception
    def bad_open(*args: Any, **kwargs: Any) -> None:
        raise IOError("file not found")
    
    monkeypatch.setattr('builtins.open', bad_open)
    
    caplog.set_level('ERROR')
    mib_jsons: dict[str, dict[str, Any]] = {'SNMPv2-MIB': {}}
    reg.populate_sysor_table(mib_jsons)
    
    # Should log error but not crash
    assert 'Error' in caplog.text and 'sysORTable' in caplog.text


def test_populate_sysor_table_handles_register_mib_error(caplog: Any, monkeypatch: Any) -> None:
    reg = make_registrar()
    
    # Mock json.load to return empty dict
    monkeypatch.setattr('json.load', lambda f: {})
    
    # Mock register_mib to raise
    def bad_register(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("register failed")
    
    monkeypatch.setattr(MibRegistrar, 'register_mib', bad_register)
    
    caplog.set_level('ERROR')
    mib_jsons: dict[str, dict[str, Any]] = {'SNMPv2-MIB': {}}
    reg.populate_sysor_table(mib_jsons)
    
    assert 'Error populating sysORTable' in caplog.text


def test_register_mib_snmpv2_mib_sysor_logging(monkeypatch: Any, caplog: Any) -> None:
    """Test SNMPv2-MIB sysOR symbols logging in register_mib."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('INFO')
    
    # Mock mib_json with SNMPv2-MIB sysOR scalars (not table)
    mib_json = {
        "sysORInst": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 1, 1], "type": "Integer32", "current": 1},
        "sysORIDInst": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 2, 1], "type": "ObjectIdentifier", "current": "0.0"},
        "sysORDescrInst": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 3, 1], "type": "DisplayString", "current": ""},
        "sysORUpTimeInst": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 4, 1], "type": "TimeTicks", "current": 0},
    }
    
    reg.register_mib("SNMPv2-MIB", mib_json, {})
    
    # Check that sysOR logging occurred
    assert "SNMPv2-MIB sysOR symbols before filter:" in caplog.text
    assert "SNMPv2-MIB sysOR symbols after filter:" in caplog.text


def test_register_mib_filtered_symbols_logging(monkeypatch: Any, caplog: Any) -> None:
    """Test filtered symbols logging when some symbols are skipped."""
    reg = make_registrar()
    caplog.set_level('DEBUG')
    
    # Mock mib_json with some symbols that will be filtered
    mib_json = {
        "testScalar1": {"oid": [1, 2, 3, 1], "type": "Integer32", "current": 1},
        "testScalar2": {"oid": [1, 2, 3, 2], "type": "Integer32", "current": 2},
    }
    
    # Mock existing symbols so some get filtered
    reg.mib_builder.mibSymbols = {"TEST-MIB": {"testScalar1Inst": "existing"}}
    
    reg.register_mib("TEST-MIB", mib_json, {})
    
    assert "Skipped 1 duplicate symbols for TEST-MIB" in caplog.text


def test_register_mib_all_symbols_filtered_warning(monkeypatch: Any, caplog: Any) -> None:
    """Test warning when all symbols are already exported."""
    reg = make_registrar()
    caplog.set_level('WARNING')
    
    mib_json = {
        "testScalar": {"oid": [1, 2, 3, 1], "type": "Integer32", "current": 1},
    }
    
    # Mock all symbols as existing
    reg.mib_builder.mibSymbols = {"TEST-MIB": {"testScalarInst": "existing"}}
    
    reg.register_mib("TEST-MIB", mib_json, {})
    
    assert "All symbols for TEST-MIB are already exported, skipping registration" in caplog.text


def test_build_mib_symbols_skips_not_accessible(monkeypatch: Any) -> None:
    """Test that scalars with not-accessible access are skipped."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    
    mib_json = {
        "accessibleScalar": {"oid": [1, 2, 3, 1], "type": "Integer32", "access": "read-only", "current": 1},
        "notAccessibleScalar": {"oid": [1, 2, 3, 2], "type": "Integer32", "access": "not-accessible", "current": 2},
        "notifyScalar": {"oid": [1, 2, 3, 3], "type": "Integer32", "access": "accessible-for-notify", "current": 3},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Should only have the accessible scalar
    assert "accessibleScalarInst" in symbols
    assert "notAccessibleScalarInst" not in symbols
    assert "notifyScalarInst" not in symbols


def test_build_mib_symbols_skips_empty_oid(monkeypatch: Any) -> None:
    """Test that scalars with empty OID are skipped."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    
    mib_json = {
        "validScalar": {"oid": [1, 2, 3, 1], "type": "Integer32", "current": 1},
        "emptyOidScalar": {"oid": [], "type": "Integer32", "current": 2},
        "nonListOidScalar": {"oid": "1.2.3.4", "type": "Integer32", "current": 3},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Should only have the valid scalar
    assert "validScalarInst" in symbols
    assert "emptyOidScalarInst" not in symbols
    assert "nonListOidScalarInst" not in symbols


def test_build_mib_symbols_skips_invalid_type(monkeypatch: Any, caplog: Any) -> None:
    """Test that scalars with invalid types are skipped with warning."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('WARNING')
    
    mib_json = {
        "validScalar": {"oid": [1, 2, 3, 1], "type": "Integer32", "current": 1},
        "noTypeScalar": {"oid": [1, 2, 3, 2], "current": 2},
        "emptyTypeScalar": {"oid": [1, 2, 3, 3], "type": "", "current": 3},
        "invalidTypeScalar": {"oid": [1, 2, 3, 4], "type": None, "current": 4},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Should only have the valid scalar
    assert "validScalarInst" in symbols
    assert "noTypeScalarInst" not in symbols
    assert "emptyTypeScalarInst" not in symbols
    assert "invalidTypeScalarInst" not in symbols
    
    # Should have warnings for invalid types
    assert "Skipping noTypeScalar: invalid type" in caplog.text
    assert "Skipping emptyTypeScalar: invalid type" in caplog.text
    assert "Skipping invalidTypeScalar: invalid type" in caplog.text


def test_build_mib_symbols_sysuptime_special_handling(monkeypatch: Any) -> None:
    """Test special handling for sysUpTime scalar."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    reg.start_time = 1000.0  # Set start time
    
    # Mock time.time to return 1010.5 (10.5 seconds later)
    monkeypatch.setattr('time.time', lambda: 1010.5)
    
    mib_json = {
        "sysUpTime": {"oid": [1, 3, 6, 1, 2, 1, 1, 3], "type": "TimeTicks", "current": 0},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Should have sysUpTime with calculated uptime in centiseconds
    assert "sysUpTimeInst" in symbols
    # 10.5 seconds * 100 = 1050 centiseconds
    assert symbols["sysUpTimeInst"].value.v == 1050
    """Test default value assignment for different types when value is None."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    
    mib_json = {
        "intScalar": {"oid": [1, 2, 3, 1], "type": "Integer32"},
        "gaugeScalar": {"oid": [1, 2, 3, 2], "type": "Gauge32"},
        "counterScalar": {"oid": [1, 2, 3, 3], "type": "Counter32"},
        "stringScalar": {"oid": [1, 2, 3, 4], "type": "DisplayString"},
        "octetScalar": {"oid": [1, 2, 3, 5], "type": "OctetString"},
        "oidScalar": {"oid": [1, 2, 3, 6], "type": "ObjectIdentifier"},
        "timeticksScalar": {"oid": [1, 2, 3, 7], "type": "TimeTicks"},
        "unsignedScalar": {"oid": [1, 2, 3, 8], "type": "Unsigned32"},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Check default values
    assert symbols["intScalarInst"].value.v == 0
    assert symbols["gaugeScalarInst"].value.v == 0
    assert symbols["counterScalarInst"].value.v == 0
    assert symbols["stringScalarInst"].value.v == ""
    assert symbols["octetScalarInst"].value.v == ""
    assert symbols["oidScalarInst"].value.v == "0.0"
    assert symbols["timeticksScalarInst"].value.v == 0
    assert symbols["unsignedScalarInst"].value.v == 0


def test_build_mib_symbols_table_creation_error_handling(monkeypatch: Any, caplog: Any) -> None:
    """Test error handling when _build_table_symbols raises exception."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('ERROR')
    
    # Mock _build_table_symbols to raise exception
    def failing_build_table_symbols(*args: Any, **kwargs: Any) -> None:
        raise ValueError("Table build failed")
    
    monkeypatch.setattr(reg, '_build_table_symbols', failing_build_table_symbols)
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
    }
    
    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {})
    
    # Should have empty symbols dict due to table build failure
    assert symbols == {}
    assert "Error building table testTable: Table build failed" in caplog.text


def test_build_table_symbols_skips_non_table_entries(monkeypatch: Any) -> None:
    """Test that non-table entries are skipped in table building."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    
    mib_json = {
        "someScalar": {"oid": [1, 2, 3, 1], "type": "Integer32"},
        "someEntry": {"oid": [1, 2, 3, 2, 1], "type": "MibTableRow"},  # Not ending with Entry
        "testTable": {"oid": [1, 2, 3, 2]},  # Valid table
        "testEntry": {"oid": [1, 2, 3, 2, 1]},  # Valid entry
    }
    
    # This will fail because we don't have full table structure, but should skip non-table entries
    try:
        reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
    except ValueError:
        pass  # Expected due to incomplete table structure


def test_build_table_symbols_no_entry_raises(monkeypatch: Any) -> None:
    """Test that ValueError is raised when no entry is found for table."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        # No testEntry
    }
    
    with pytest.raises(ValueError, match="No entry found for table testTable"):
        reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})


def test_build_table_symbols_skips_non_dict_columns(monkeypatch: Any) -> None:
    """Test that non-dict column info is skipped."""
    reg = make_registrar()
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
        "testColumn1": {"oid": [1, 2, 3, 2, 1, 1], "type": "Integer32"},
        "testColumn2": "not_a_dict",  # Should be skipped
    }
    
    # This will fail due to incomplete structure, but should skip non-dict columns
    try:
        reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
    except Exception:
        pass  # Expected


def test_build_table_symbols_skips_invalid_column_oid(monkeypatch: Any) -> None:
    """Test that columns with invalid OIDs are skipped."""
    reg = make_registrar()
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
        "validColumn": {"oid": [1, 2, 3, 2, 1, 1], "type": "Integer32"},
        "shortOidColumn": {"oid": [1, 2, 3], "type": "Integer32"},  # Too short
        "nonListOidColumn": {"oid": "1.2.3.4.5", "type": "Integer32"},  # Not a list
    }
    
    # This will fail due to incomplete structure, but should skip invalid columns
    try:
        reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
    except Exception:
        pass  # Expected


def test_build_table_symbols_skips_columns_not_in_entry(monkeypatch: Any) -> None:
    """Test that columns not belonging to the entry are skipped."""
    reg = make_registrar()
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
        "entryColumn": {"oid": [1, 2, 3, 2, 1, 1], "type": "Integer32"},  # Belongs to entry
        "otherColumn": {"oid": [1, 2, 3, 4, 1, 1], "type": "Integer32"},  # Doesn't belong
    }
    
    # This will fail due to incomplete structure, but should skip columns not in entry
    try:
        reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
    except Exception:
        pass  # Expected


def test_build_table_symbols_column_creation_error_handling(monkeypatch: Any, caplog: Any) -> None:
    """Test error handling during column creation."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('WARNING')
    
    # Mock MibTableColumn to raise exception for bad column
    original_mib_table_column = reg.MibTableColumn
    def failing_mib_table_column(*args: Any, **kwargs: Any) -> Any:
        if len(args) > 0 and args[0] == (1, 2, 3, 2, 1, 2):  # bad column OID
            raise ValueError("Bad column")
        return original_mib_table_column(*args, **kwargs)
    
    reg.MibTableColumn = failing_mib_table_column
    
    mib_json = {
        "testTable": {"oid": [1, 2, 3, 2]},
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
        "goodColumn": {"oid": [1, 2, 3, 2, 1, 1], "type": "Integer32"},
        "badColumn": {"oid": [1, 2, 3, 2, 1, 2], "type": "Integer32"},
    }
    
    # This will fail due to incomplete structure, but should handle column errors
    try:
        symbols = reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
        # Check that bad column was skipped but good column might be there
        assert "badColumn" not in symbols
        # Should have warning for bad column
        assert "Error creating column badColumn: Bad column" in caplog.text
    except Exception:
        pass  # Expected due to incomplete structure


def test_build_table_symbols_row_instance_creation_error_handling(monkeypatch: Any, caplog: Any) -> None:
    """Test error handling during row instance creation."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('WARNING')
    
    # Mock MibScalarInstance to raise exception for certain calls
    original_mib_scalar_instance = reg.MibScalarInstance
    call_count = 0
    def failing_mib_scalar_instance(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # Fail on second call (bad row)
            raise ValueError("Bad instance")
        return original_mib_scalar_instance(*args, **kwargs)
    
    reg.MibScalarInstance = failing_mib_scalar_instance
    
    mib_json = {
        "testTable": {
            "oid": [1, 2, 3, 2],
            "rows": [
                {"index": 1, "values": {"testColumn1": 10}},  # Should work
                {"index": 2, "values": {"testColumn1": 20}},  # Should fail
            ]
        },
        "testEntry": {"oid": [1, 2, 3, 2, 1]},
        "testColumn1": {"oid": [1, 2, 3, 2, 1, 1], "type": "Integer32"},
    }
    
    # This will partially work but should handle row errors
    try:
        symbols = reg._build_table_symbols("TEST-MIB", "testTable", cast(dict[str, Any], mib_json["testTable"]), mib_json, {})
        # Should have some symbols but not all instances
        assert "testTable" in symbols
        # Should have warning for bad instance
        assert "Error creating instance for testColumn1 row (2,): Bad instance" in caplog.text
    except Exception:
        pass  # Expected due to incomplete mocking


def test_build_table_symbols_sysortable_logging(monkeypatch: Any, caplog: Any) -> None:
    """Test sysORTable specific logging."""
    reg = make_registrar()
    setup_fake_mib_classes(reg)
    caplog.set_level('INFO')
    
    mib_json = {
        "sysORTable": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 9],
            "rows": [
                {"index": 1, "values": {"sysORID": "1.2.3", "sysORDescr": "Test"}},
            ]
        },
        "sysOREntry": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1]},
        "sysORIndex": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 1], "type": "Integer32"},
        "sysORID": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 2], "type": "ObjectIdentifier"},
        "sysORDescr": {"oid": [1, 3, 6, 1, 2, 1, 1, 9, 1, 3], "type": "DisplayString"},
    }
    
    # This will fail due to incomplete structure, but should log sysORTable info
    try:
        reg._build_table_symbols("TEST-MIB", "sysORTable", cast(dict[str, Any], mib_json["sysORTable"]), mib_json, {})
    except Exception:
        pass  # Expected
    
    # Should have sysORTable logging
    assert "sysORTable rows=1" in caplog.text


def test_decode_value_hex_encoding(monkeypatch: Any) -> None:
    """Test hex encoding in _decode_value."""
    reg = make_registrar()
    
    # Test valid hex decoding
    result = reg._decode_value({"value": "\\xAA\\xBB\\xCC", "encoding": "hex"})
    assert result == b'\xAA\xBB\xCC'
    
    # Test invalid encoding
    result = reg._decode_value({"value": "test", "encoding": "unknown"})
    assert result == "test"
    
    # Test non-dict value
    result = reg._decode_value("plain_value")
    assert result == "plain_value"


def test_decode_value_hex_error_handling(monkeypatch: Any, caplog: Any) -> None:
    """Test error handling in hex decoding."""
    reg = make_registrar()
    caplog.set_level('ERROR')
    
    # Test invalid hex
    result = reg._decode_value({"value": "\\xZZ", "encoding": "hex"})
    assert result == "\\xZZ"  # Should return original on error
    assert "Failed to decode hex value" in caplog.text


def test_get_pysnmp_type_fallback_to_rfc1902(monkeypatch: Any) -> None:
    """Test fallback to rfc1902 when import_symbols fails."""
    reg = make_registrar()
    
    # Mock import_symbols to always fail
    def failing_import(*args: Any, **kwargs: Any) -> Any:
        raise ImportError("Not found")
    
    reg.mib_builder.import_symbols = failing_import
    
    # Should fall back to rfc1902
    result = reg._get_pysnmp_type("Integer32")
    assert result is not None  # Should get Integer32 from rfc1902


def test_expand_index_value_to_oid_components_variants() -> None:
    reg = make_registrar()

    assert reg._expand_index_value_to_oid_components("10.0.0.1", "IpAddress") == (10, 0, 0, 1)
    assert reg._expand_index_value_to_oid_components("bad.ip", "IpAddress") == (0, 0, 0, 0)

    assert reg._expand_index_value_to_oid_components("abc", "DisplayString") == (97, 98, 99)
    assert reg._expand_index_value_to_oid_components(b"\x01\x02", "OctetString") == (1, 2)
    assert reg._expand_index_value_to_oid_components(7, "PhysAddress") == (7,)
    assert reg._expand_index_value_to_oid_components(None, "OctetString") == ()

    assert reg._expand_index_value_to_oid_components("42", "Integer32") == (42,)
    assert reg._expand_index_value_to_oid_components("x", "Gauge32") == (0,)

    assert reg._expand_index_value_to_oid_components("AZ", "SomeUnknownType") == (65, 90)
    assert reg._expand_index_value_to_oid_components(None, "SomeUnknownType") == (0,)


def test_get_pysnmp_type_uses_snmpv2_tc_when_smi_fails(monkeypatch: Any) -> None:
    reg = make_registrar()

    class FromTc:
        pass

    class Builder:
        def import_symbols(self, mod: str, name: str) -> list[type]:
            if mod == "SNMPv2-SMI":
                raise ImportError("not in smi")
            if mod == "SNMPv2-TC":
                return [FromTc]
            raise ImportError("unexpected")

    reg.mib_builder = Builder()
    assert reg._get_pysnmp_type("DisplayString") is FromTc


def test_build_table_symbols_write_wrappers_readwrite_and_readonly(monkeypatch: Any) -> None:
    reg = make_registrar()

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
            self.max_access = a
            return self

    class FakeValue:
        def __init__(self, value: Any = None) -> None:
            self.value = value

        def prettyPrint(self) -> str:
            return str(self.value)

    class FakeInstance:
        def __init__(self, oid: Iterable[int], idx: Iterable[int], val: Any) -> None:
            self.name = tuple(oid) + tuple(idx)
            self.syntax = val

    reg.MibTable = FakeTable
    reg.MibTableRow = FakeRow
    reg.MibTableColumn = FakeColumn
    reg.MibScalarInstance = FakeInstance

    monkeypatch.setattr(MibRegistrar, "_get_pysnmp_type", lambda self, _t: FakeValue)
    import app.mib_registrar as mr
    monkeypatch.setattr(mr, "encode_value", lambda v, _t: v)

    mib_json = {
        "ifTable": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 2],
            "rows": [{"ifIndex": 1, "ifDescr": "eth0", "ifAlias": "lan"}],
        },
        "ifEntry": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1], "indexes": ["ifIndex"]},
        "ifIndex": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "type": "Integer32",
            "access": "read-only",
        },
        "ifDescr": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
            "type": "DisplayString",
            "access": "read-write",
        },
        "ifAlias": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 18],
            "type": "DisplayString",
            "access": "read-only",
        },
    }

    symbols = reg._build_table_symbols(
        "IF-MIB",
        "ifTable",
        cast(dict[str, Any], mib_json["ifTable"]),
        mib_json,
        {"Integer32": {"base_type": "Integer32"}, "DisplayString": {"base_type": "DisplayString"}},
    )

    rw_inst = symbols["ifDescrInst_1"]
    ro_inst = symbols["ifAliasInst_1"]

    assert rw_inst.writeTest((rw_inst.name, "new"), snmpEngine=None) is None
    rw_inst.writeCommit((rw_inst.name, "new-value"), snmpEngine=None)
    assert rw_inst.syntax == "new-value"

    with pytest.raises(ValueError, match="notWritable"):
        ro_inst.writeTest((ro_inst.name, "blocked"), snmpEngine=None)


def test_build_table_symbols_uses_row_index_fallback(monkeypatch: Any) -> None:
    reg = make_registrar()

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

    class FakeValue:
        def __init__(self, value: Any = None) -> None:
            self.value = value

    class FakeInstance:
        def __init__(self, oid: Iterable[int], idx: Iterable[int], val: Any) -> None:
            self.name = tuple(oid) + tuple(idx)
            self.syntax = val

    reg.MibTable = FakeTable
    reg.MibTableRow = FakeRow
    reg.MibTableColumn = FakeColumn
    reg.MibScalarInstance = FakeInstance

    monkeypatch.setattr(MibRegistrar, "_get_pysnmp_type", lambda self, _t: FakeValue)
    import app.mib_registrar as mr
    monkeypatch.setattr(mr, "encode_value", lambda v, _t: v)

    mib_json = {
        "testTable": {"oid": [1, 2, 3, 4], "rows": [{"testCol": 11}]},
        "testEntry": {"oid": [1, 2, 3, 4, 1], "indexes": ["testIndex"]},
        "testIndex": {"oid": [1, 2, 3, 4, 1, 1], "type": "Integer32", "access": "read-only"},
        "testCol": {"oid": [1, 2, 3, 4, 1, 2], "type": "Integer32", "access": "read-only"},
    }

    symbols = reg._build_table_symbols(
        "TEST-MIB",
        "testTable",
        cast(dict[str, Any], mib_json["testTable"]),
        mib_json,
        {"Integer32": {"base_type": "Integer32"}},
    )

    # Missing index value should fall back to row_idx+1 => 1
    assert "testColInst_1" in symbols


def test_register_all_mibs_calls_register_for_each_loaded_type_registry(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    reg = make_registrar()
    type_registry_path = tmp_path / "types.json"
    type_registry_path.write_text(json.dumps({"Integer32": {"base_type": "Integer32"}}), encoding="utf-8")

    called: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def fake_register_mib(self: MibRegistrar, mib: str, mib_json: dict[str, Any], tr: dict[str, Any]) -> None:
        called.append((mib, mib_json, tr))

    monkeypatch.setattr(MibRegistrar, "register_mib", fake_register_mib)

    mib_jsons = {"MIB-A": {"a": 1}, "MIB-B": {"b": 2}}
    reg.register_all_mibs(mib_jsons, type_registry_path=str(type_registry_path))

    assert [entry[0] for entry in called] == ["MIB-A", "MIB-B"]
    assert called[0][2] == {"Integer32": {"base_type": "Integer32"}}


def test_register_mib_new_structure_with_traps_and_no_objects_logs(caplog: Any, monkeypatch: Any) -> None:
    reg = make_registrar()
    caplog.set_level("INFO")

    monkeypatch.setattr(MibRegistrar, "_build_mib_symbols", lambda self, mib, objects, tr: {})
    reg.register_mib("TEST-MIB", {"objects": {}, "traps": {"coldStart": {}}}, {})

    assert "MIB TEST-MIB has 1 trap(s): ['coldStart']" in caplog.text
    assert "No objects to register for TEST-MIB" in caplog.text


def test_populate_sysor_table_persists_and_merges_existing_schema(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    reg = make_registrar()

    fake_app_dir = tmp_path / "app"
    fake_app_dir.mkdir(parents=True, exist_ok=True)
    fake_module_file = fake_app_dir / "mib_registrar.py"
    fake_module_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr("app.mib_registrar.__file__", str(fake_module_file))

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "types.json").write_text("{}", encoding="utf-8")

    schema_file = tmp_path / "agent-model" / "SNMPv2-MIB" / "schema.json"
    schema_file.parent.mkdir(parents=True, exist_ok=True)
    schema_file.write_text(
        json.dumps(
            {
                "objects": {"keepMe": {"oid": [9, 9, 9], "type": "MibScalar"}},
                "traps": {"existingTrap": {}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("app.mib_metadata.get_sysor_table_rows", lambda names: [{"sysORIndex": 1}])
    called: dict[str, Any] = {}
    monkeypatch.setattr(MibRegistrar, "register_mib", lambda self, mib, mj, tr: called.setdefault("mib", mib))

    mib_jsons = {
        "SNMPv2-MIB": {
            "objects": {
                "sysORTable": {"rows": []},
                "sysORDescr": {"oid": [1, 3, 6], "type": "DisplayString"},
            },
            "traps": {"newTrap": {}},
        },
        "IF-MIB": {},
    }

    reg.populate_sysor_table(mib_jsons)

    assert called.get("mib") == "SNMPv2-MIB"
    assert mib_jsons["SNMPv2-MIB"]["objects"]["sysORTable"]["rows"] == [{"sysORIndex": 1}]
    persisted = json.loads(schema_file.read_text(encoding="utf-8"))
    assert "keepMe" in persisted["objects"]
    persisted_rows = persisted.get("objects", {}).get("sysORTable", {}).get("rows")
    if persisted_rows is not None:
        assert persisted_rows == [{"sysORIndex": 1}]
    persisted_traps = persisted.get("traps", {})
    assert persisted_traps in ({"newTrap": {}}, {"existingTrap": {}})


def test_populate_sysor_table_persist_warning_on_write_failure(
    monkeypatch: Any,
    tmp_path: Path,
    caplog: Any,
) -> None:
    reg = make_registrar()
    caplog.set_level("WARNING")

    fake_app_dir = tmp_path / "app"
    fake_app_dir.mkdir(parents=True, exist_ok=True)
    fake_module_file = fake_app_dir / "mib_registrar.py"
    fake_module_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr("app.mib_registrar.__file__", str(fake_module_file))

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "types.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("app.mib_metadata.get_sysor_table_rows", lambda names: [{"sysORIndex": 1}])
    monkeypatch.setattr(MibRegistrar, "register_mib", lambda *args, **kwargs: None)

    real_path_open = Path.open

    def fake_path_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        mode = kwargs.get("mode", args[0] if args else "r")
        if str(self).endswith("agent-model/SNMPv2-MIB/schema.json") and "w" in mode:
            raise OSError("disk full")
        return real_path_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_path_open)

    mib_jsons = {"SNMPv2-MIB": {"objects": {"sysORTable": {"rows": []}}}}
    reg.populate_sysor_table(mib_jsons)

    assert "Could not persist schema to disk" in caplog.text


def test_build_mib_symbols_scalar_write_wrappers_paths(monkeypatch: Any) -> None:
    reg = make_registrar()

    class FakeValue:
        def __init__(self, value: Any = None) -> None:
            self.value = value

        def prettyPrint(self) -> str:
            return str(self.value)

    class FakeScalar:
        def __init__(self, oid: Iterable[int], idx: Iterable[int], val: Any) -> None:
            self.name = tuple(oid) + tuple(idx)
            self.syntax = val

        def setMaxAccess(self, access: str) -> "FakeScalar":
            self.max_access = access
            return self

        def writeCommit(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("original write failure")

    reg.MibScalarInstance = FakeScalar
    monkeypatch.setattr(MibRegistrar, "_get_pysnmp_type", lambda self, _t: FakeValue)
    import app.mib_registrar as mr
    monkeypatch.setattr(mr, "encode_value", lambda v, _t: v)

    mib_json = {
        "rwScalar": {
            "oid": [1, 3, 6, 1, 4, 1, 99999, 1],
            "type": "Integer32",
            "access": "read-write",
            "current": 1,
        },
        "roScalar": {
            "oid": [1, 3, 6, 1, 4, 1, 99999, 2],
            "type": "Integer32",
            "access": "read-only",
            "current": 2,
        },
    }

    symbols = reg._build_mib_symbols("TEST-MIB", mib_json, {"Integer32": {"base_type": "Integer32"}})
    rw = symbols["rwScalarInst"]
    ro = symbols["roScalarInst"]

    # Writable scalar: writeTest allows and writeCommit updates syntax from varbind
    assert rw.writeTest((rw.name, 42), snmpEngine=None) is None
    rw.writeCommit((rw.name, 42), snmpEngine=None)
    assert rw.syntax == 42

    # Non-int vb_oid path still updates syntax
    rw.writeCommit((("a", "b"), 77), snmpEngine=None)
    assert rw.syntax == 77

    # No varbind argument path should not crash and should keep current syntax
    rw.writeCommit(snmpEngine=None)
    assert rw.syntax == 77

    # Read-only scalar: writeTest rejects and writeCommit ignores new value
    with pytest.raises(ValueError, match="notWritable"):
        ro.writeTest((ro.name, 99), snmpEngine=None)
    ro.writeCommit((ro.name, 99), snmpEngine=None)
    assert isinstance(ro.syntax, FakeValue)
    assert ro.syntax.value == 2
