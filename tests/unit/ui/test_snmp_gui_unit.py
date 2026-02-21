from __future__ import annotations

from typing import Any

import ui.snmp_gui as sg


class _DummyVar:
    def __init__(self, value: Any):
        self._value = value

    def get(self) -> Any:
        return self._value


class _DummyEntry:
    def __init__(self, value: str):
        self._value = value

    def get(self) -> str:
        return self._value


class _DummyText:
    def __init__(self):
        self.insert_calls: list[tuple[str, str]] = []
        self.see_calls: list[str] = []

    def insert(self, where: str, text: str) -> None:
        self.insert_calls.append((where, text))

    def see(self, where: str) -> None:
        self.see_calls.append(where)


class _Resp:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


def _mk_gui() -> sg.SNMPControllerGUI:
    gui = sg.SNMPControllerGUI.__new__(sg.SNMPControllerGUI)
    gui.api_url = "http://test"
    gui.oid_metadata = {}
    gui.table_schemas = {}
    gui._log = lambda *args, **kwargs: None
    return gui


def test_oid_list_to_str_formats_list_tuple_and_scalar() -> None:
    assert sg._oid_list_to_str([1, 3, 6]) == "1.3.6"
    assert sg._oid_list_to_str((1, 3, 6, 1)) == "1.3.6.1"
    assert sg._oid_list_to_str("1.3.6.1") == "1.3.6.1"


def test_links_helpers_format_and_parse_endpoints() -> None:
    gui = _mk_gui()
    formatted = gui._format_link_endpoints(
        [
            {"table_oid": "1.2.3", "column": "ifDescr"},
            {"table_oid": None, "column": "sysName"},
        ]
    )
    assert formatted == "1.2.3:ifDescr | sysName"

    parsed = gui._parse_endpoints_text(
        "\n1.3.6.1.2.1.2.2.1 ifDescr\n1.3.6.1.2.1.2.2:ifType\nsysName\n"
    )
    assert parsed == [
        {"table_oid": "1.3.6.1.2.1.2.2.1", "column": "ifDescr"},
        {"table_oid": "1.3.6.1.2.1.2.2", "column": "ifType"},
        {"table_oid": None, "column": "sysName"},
    ]


def test_varbind_detection_index_and_sysuptime() -> None:
    gui = _mk_gui()
    assert gui._is_index_varbind("IF-MIB::ifIndex.7") is True
    assert gui._is_index_varbind("IF-MIB::ifDescr.7") is False
    assert gui._is_sysuptime_varbind("SNMPv2-MIB::sysUpTime.0") is True
    assert gui._is_sysuptime_varbind("SNMPv2-MIB::sysName.0") is False


def test_oid_metadata_and_table_oid_resolution_paths() -> None:
    gui = _mk_gui()
    gui.oid_metadata = {
        "1.3.6.1.2.1.1.5": {
            "mib": "SNMPv2-MIB",
            "name": "sysName",
            "type": "MibScalar",
            "access": "read-write",
        },
        "1.3.6.1.2.1.2.2": {
            "mib": "IF-MIB",
            "name": "ifTable",
            "type": "MibTable",
            "access": "not-accessible",
        },
        "1.3.6.1.2.1.2.2.1": {
            "mib": "IF-MIB",
            "name": "ifEntry",
            "type": "MibTableRow",
            "access": "not-accessible",
        },
        "1.3.6.1.2.1.2.2.1.7": {
            "mib": "IF-MIB",
            "name": "ifAdminStatus",
            "type": "Integer32",
            "access": "read-write",
        },
    }

    assert gui._get_oid_metadata_by_name("SNMPv2-MIB::sysName")["name"] == "sysName"
    assert gui._resolve_table_oid("SNMPv2-MIB::sysName") == "1.3.6.1.2.1.1.5.0"
    assert gui._resolve_table_oid("IF-MIB::ifAdminStatus") is None
    assert gui._resolve_table_oid("IF-MIB::ifAdminStatus.9") == "1.3.6.1.2.1.2.2.1.7.9"


def test_enum_and_selected_info_helpers() -> None:
    gui = _mk_gui()
    enums = {"up": 1, "down": 2}

    assert gui._format_enum_display("1", enums) == "1 (up)"
    assert gui._format_enum_display("unset", enums) == "unset"
    assert gui._extract_enum_value("2 (down)", enums) == "2"
    assert gui._extract_enum_value("down", enums) == "2"

    gui.oid_metadata = {".1.3.6.1.2.1.2.2.1.8": {"enums": enums}}
    text = gui._format_selected_info("1.3.6.1.2.1.2.2.1.8.4", "Integer", "2")
    assert text.startswith(".1.3.6.1.2.1.2.2.1.8.4 = Integer: 2")
    assert "(down)" in text


def test_index_encode_decode_helpers_with_ipaddress() -> None:
    gui = _mk_gui()
    columns_meta = {"addr": {"type": "IpAddress"}, "idx": {"type": "Integer"}}
    index_columns = ["addr", "idx"]

    decoded = gui._extract_index_values("192.168.1.2.7", index_columns, columns_meta)
    assert decoded == {"addr": "192.168.1.2", "idx": "7"}

    encoded = gui._build_instance_from_index_values(
        decoded, index_columns, columns_meta
    )
    assert encoded == "192.168.1.2.7"


def test_decompose_table_oid_returns_table_column_and_instance() -> None:
    gui = _mk_gui()
    gui.table_schemas = {
        "ifTable": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 2],
            "entry_oid": [1, 3, 6, 1, 2, 1, 2, 2, 1],
            "index_columns": ["ifIndex"],
            "columns": {
                "ifDescr": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2]},
                "ifAdminStatus": {"oid": [1, 3, 6, 1, 2, 1, 2, 2, 1, 7]},
            },
        }
    }
    result = gui._decompose_table_oid("1.3.6.1.2.1.2.2.1.7.3")
    assert result == ("1.3.6.1.2.1.2.2", "ifAdminStatus", "3")


def test_collect_trap_overrides_skips_index_and_sysuptime() -> None:
    gui = _mk_gui()
    gui.oid_rows = [
        {
            "oid_name": "IF-MIB::ifDescr.1",
            "is_sysuptime": False,
            "is_index": False,
            "use_override_var": _DummyVar(True),
            "override_entry": _DummyEntry("  up  "),
        },
        {
            "oid_name": "SNMPv2-MIB::sysUpTime.0",
            "is_sysuptime": True,
            "is_index": False,
            "use_override_var": _DummyVar(True),
            "override_entry": _DummyEntry("123"),
        },
        {
            "oid_name": "IF-MIB::ifIndex.1",
            "is_sysuptime": False,
            "is_index": True,
            "use_override_var": _DummyVar(True),
            "override_entry": _DummyEntry("1"),
        },
    ]

    assert gui._collect_trap_overrides() == {"IF-MIB::ifDescr.1": "up"}


def test_resolve_apply_overrides_and_payload(monkeypatch: Any) -> None:
    gui = _mk_gui()
    logs: list[tuple[str, str]] = []
    gui._log = lambda message, level="INFO": logs.append((level, message))
    gui._resolve_oid_str_to_actual_oid = lambda oid_str: {
        "ok": "1.3.6.1.2.1.1.5.0",
        "ok2": "1.3.6.1.2.1.1.6.0",
    }.get(oid_str)

    post_calls: list[tuple[str, dict[str, Any], int]] = []

    def fake_post(url: str, json: dict[str, Any], timeout: int) -> _Resp:
        post_calls.append((url, json, timeout))
        if json["value"] == "bad":
            return _Resp(status_code=500, text="boom")
        return _Resp(status_code=200)

    monkeypatch.setattr(sg.requests, "post", fake_post)

    applied = gui._apply_trap_overrides({"ok": "value", "missing": "x", "ok2": "bad"})
    assert applied == 1
    assert len(post_calls) == 2

    payload = gui._build_send_trap_payload("coldStart", "127.0.0.1", 162)
    assert payload == {
        "trap_name": "coldStart",
        "trap_type": "trap",
        "dest_host": "127.0.0.1",
        "dest_port": 162,
        "community": "public",
    }


def test_log_send_helpers_write_text_widget() -> None:
    gui = _mk_gui()
    gui.log_text = _DummyText()

    gui._log_send_result("127.0.0.1", 162, "coldStart", {"trap_oid": [1, 3, 6, 1]})
    gui._log_send_failure("127.0.0.1", 162, "coldStart", Exception("net down"))

    assert len(gui.log_text.insert_calls) == 2
    combined = "\n".join(text for _, text in gui.log_text.insert_calls)
    assert "Sent to 127.0.0.1:162: coldStart" in combined
    assert "OID: 1.3.6.1" in combined
    assert "Failed to 127.0.0.1:162: coldStart - net down" in combined
    assert gui.log_text.see_calls == ["end", "end"]


def test_trap_index_helpers_and_interface_indices(monkeypatch: Any) -> None:
    gui = _mk_gui()

    assert gui._trap_has_index_objects({"objects": [{"name": "ifIndex"}]}) is True
    assert gui._trap_has_index_objects({"objects": [{"name": "sysName"}]}) is False

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]):
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    def fake_get(
        url: str, params: dict[str, Any] | None = None, timeout: int = 0
    ) -> _Resp:
        if url.endswith("/table-schema"):
            return _Resp(200, {"instances": ["3", "1", "2"]})
        return _Resp(500, {})

    monkeypatch.setattr(sg.requests, "get", fake_get)

    indices = gui._get_interface_indices()
    assert indices == ["1", "2", "3"]

    trap_indices = gui._get_trap_indices({"objects": [{"name": "ifIndex"}]})
    assert trap_indices == ["1", "2", "3"]


def test_interface_indices_fallback_to_ifnumber(monkeypatch: Any) -> None:
    gui = _mk_gui()

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]):
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    def fake_get(
        url: str, params: dict[str, Any] | None = None, timeout: int = 0
    ) -> _Resp:
        if url.endswith("/table-schema"):
            return _Resp(404, {})
        if url.endswith("/value"):
            return _Resp(200, {"value": 2})
        return _Resp(500, {})

    monkeypatch.setattr(sg.requests, "get", fake_get)

    indices = gui._get_interface_indices()
    assert indices == ["1", "2"]


def test_interface_indices_probe_fallback(monkeypatch: Any) -> None:
    gui = _mk_gui()

    class _Resp:
        def __init__(self, status_code: int):
            self.status_code = status_code

        def json(self) -> dict[str, Any]:
            return {}

    def fake_get(
        url: str, params: dict[str, Any] | None = None, timeout: int = 0
    ) -> _Resp:
        if url.endswith("/table-schema"):
            return _Resp(500)
        if url.endswith("/value") and "1.3.6.1.2.1.2.1.0" in url:
            return _Resp(500)
        if url.endswith(".1"):
            return _Resp(200)
        return _Resp(404)

    monkeypatch.setattr(sg.requests, "get", fake_get)

    indices = gui._get_interface_indices()
    assert indices == ["1"]
