"""Tests for test value links."""

from __future__ import annotations

from app.value_links import ValueLinkEndpoint, ValueLinkManager


def test_add_link_rejects_single_endpoint() -> None:
    """Test case for test_add_link_rejects_single_endpoint."""
    manager = ValueLinkManager()
    manager.add_link("only", [ValueLinkEndpoint(None, "ifDescr")])
    assert manager.export_links() == []


def test_add_and_remove_link_updates_indexes() -> None:
    """Test case for test_add_and_remove_link_updates_indexes."""
    manager = ValueLinkManager()
    endpoints = [
        ValueLinkEndpoint("1.2.3", "ifDescr"),
        ValueLinkEndpoint("1.2.3", "ifName"),
    ]
    manager.add_link("link1", endpoints)

    targets = manager.get_linked_targets("ifDescr", "1.2.3")
    assert [(t.table_oid, t.column_name) for t in targets] == [("1.2.3", "ifName")]

    assert manager.remove_link("link1") is True
    assert manager.get_linked_targets("ifDescr", "1.2.3") == []
    assert manager.remove_link("missing") is False


def test_parse_link_config_endpoints_and_columns() -> None:
    """Test case for test_parse_link_config_endpoints_and_columns."""
    manager = ValueLinkManager()
    objects = {
        "ifDescr": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2]},
        "ifName": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 3]},
    }

    link_id, endpoints, scope, match, source, description, create_missing = (
        manager._parse_link_config(
            {
                "id": "link-x",
                "scope": "per-instance",
                "match": "shared-index",
                "source": "schema",
                "description": "desc",
                "create_missing": True,
                "columns": ["ifDescr", "ifName"],
            },
            objects,
        )
    )

    assert link_id == "link-x"
    assert scope == "per-instance"
    assert match == "shared-index"
    assert source == "schema"
    assert description == "desc"
    assert create_missing is True
    assert [(e.table_oid, e.column_name) for e in endpoints] == [
        ("1.3.6.1.2.1.2.2", "ifDescr"),
        ("1.3.6.1.2.1.2.2", "ifName"),
    ]

    link_id2, endpoints2, *_rest = manager._parse_link_config(
        {
            "id": "link-y",
            "endpoints": [
                {"table_oid": "1.2.3", "column": "ifDescr"},
                {"table_oid": "1.2.3", "column": "ifName"},
            ],
        },
        None,
    )

    assert link_id2 == "link-y"
    assert [(e.table_oid, e.column_name) for e in endpoints2] == [
        ("1.2.3", "ifDescr"),
        ("1.2.3", "ifName"),
    ]


def test_load_links_from_schema_and_state_and_export() -> None:
    """Test case for test_load_links_from_schema_and_state_and_export."""
    manager = ValueLinkManager()

    schema = {
        "objects": {
            "ifDescr": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2]},
            "ifName": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 3]},
        },
        "links": [
            {"columns": ["ifDescr", "ifName"], "description": "schema-link"},
            "bad-entry",
        ],
    }
    manager.load_links_from_schema(schema)

    state_links = [
        {
            "id": "state-1",
            "scope": "global",
            "match": "shared-index",
            "description": "state-link",
            "endpoints": [
                {"table_oid": "1.2.3", "column": "ifDescr"},
                {"table_oid": "1.2.3", "column": "ifName"},
            ],
        }
    ]
    manager.load_links_from_state(state_links)

    exported_all = manager.export_links()
    assert len(exported_all) == 2
    exported_state = manager.export_state_links()
    assert len(exported_state) == 1
    assert exported_state[0]["id"] == "state-1"


def test_get_linked_targets_dedupes_and_filters_scope() -> None:
    """Test case for test_get_linked_targets_dedupes_and_filters_scope."""
    manager = ValueLinkManager()
    endpoints = [
        ValueLinkEndpoint("1.2.3", "ifDescr"),
        ValueLinkEndpoint("1.2.3", "ifName"),
        ValueLinkEndpoint("1.2.3", "ifName"),
        ValueLinkEndpoint("9.9.9", "ifAlias"),
    ]
    manager.add_link("link1", endpoints, scope="per-instance")

    targets = manager.get_linked_targets("ifDescr", "1.2.3")
    assert [(t.table_oid, t.column_name) for t in targets] == [
        ("1.2.3", "ifName"),
        ("9.9.9", "ifAlias"),
    ]

    targets_other = manager.get_linked_targets("ifDescr", "9.9.9")
    assert targets_other == []


def test_update_tracking_and_clear() -> None:
    """Test case for test_update_tracking_and_clear."""
    manager = ValueLinkManager()
    assert manager.should_propagate("ifDescr", "1") is True

    manager.begin_update("ifDescr", "1")
    assert manager.should_propagate("ifDescr", "1") is False

    manager.end_update("ifDescr", "1")
    assert manager.should_propagate("ifDescr", "1") is True

    manager.add_link(
        "link", [ValueLinkEndpoint(None, "ifDescr"), ValueLinkEndpoint(None, "ifName")]
    )
    manager.clear()
    assert manager.export_links() == []
