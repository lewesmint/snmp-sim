from typing import Any, Dict

import pytest

from app.snmp_table_responder import SNMPTableResponder


def make_basic_behavior() -> Dict[str, Dict[str, Any]]:
    # Simple MIB describing a table with one column and two rows
    return {
        "TEST-MIB": {
            "MyTable": {
                "type": "MibTable",
                "oid": [1, 2],
                "rows": [
                    {"index": "1", "col1": "x"},
                    {"index": "2", "col1": "y"},
                ],
            },
            "MyTableEntry": {
                "type": "MibTableRow",
                "oid": [1, 2, 3],
                "indexes": ["index"],
                "columns": {"col1": {"oid": [1, 2, 3, 1]}},
            },
            "col1": {"oid": [1, 2, 3, 1], "type": "Integer32"},
        }
    }


def test_table_map_and_detection() -> None:
    behavior = make_basic_behavior()
    r = SNMPTableResponder(behavior, mib_builder=None)

    # Direct table OID
    assert r.is_table_oid((1, 2)) is True
    # Inside table (entry/row/column)
    assert r.is_table_oid((1, 2, 3, 1)) is True
    # Not a table
    assert r.is_table_oid((9, 9, 9)) is False


def test_get_table_info_direct_and_within() -> None:
    behavior = make_basic_behavior()
    r = SNMPTableResponder(behavior, mib_builder=None)

    info_direct = r.get_table_info((1, 2))
    assert info_direct is not None
    mib_name, table_name, table_data, table_oid = info_direct
    assert mib_name == "TEST-MIB"
    assert table_name == "MyTable"
    assert table_oid == (1, 2)

    info_inner = r.get_table_info((1, 2, 3, 1))
    assert info_inner is not None
    assert info_inner[0] == "TEST-MIB"

    assert r.get_table_info((9, 9, 9)) is None


def test_all_oids_and_get_oid_value_and_getnext() -> None:
    behavior = make_basic_behavior()
    r = SNMPTableResponder(behavior, mib_builder=None)

    all_oids = r._get_all_table_oids()
    assert (1, 2, 3, 1) in all_oids
    assert (1, 2, 3, 2) in all_oids

    # Known value
    v1 = r._get_oid_value((1, 2, 3, 1))
    assert v1 == "x"

    # Unknown row
    assert r._get_oid_value((1, 2, 3, 3)) is None

    # get_next_oid returns next available
    nxt = r.get_next_oid((1, 2, 3, 1))
    assert nxt is not None
    next_oid, next_val = nxt
    assert next_oid == (1, 2, 3, 2)
    assert next_val == "y"

    # No next
    assert r.get_next_oid((1, 2, 3, 2)) is None


def test_short_oid_and_missing_entry_cases() -> None:
    # Table present but entry definition missing
    behavior = {
        "TEST-MIB": {
            "BrokenTable": {"type": "MibTable", "oid": [10], "initial": {"1": {"c": 1}}}
            # Note: no BrokenTableEntry
        }
    }
    r = SNMPTableResponder(behavior, mib_builder=None)

    # get_table_info for a row belonging to table still returns the table (but _get_oid_value will fail)
    assert r.get_table_info((10, 3, 1)) is not None
    assert r._get_oid_value((10, 3, 1)) is None

    # Short OID (too short to contain column id) returns None
    assert r._get_oid_value((10,)) is None


def test_handle_wrappers() -> None:
    behavior = make_basic_behavior()
    r = SNMPTableResponder(behavior, mib_builder=None)

    assert r.handle_get_request((1, 2, 3, 1)) == "x"

    nxt = r.handle_getnext_request((1, 2, 3, 1))
    assert nxt is not None
    assert nxt[0] == (1, 2, 3, 2)


if __name__ == "__main__":
    pytest.main([__file__])
