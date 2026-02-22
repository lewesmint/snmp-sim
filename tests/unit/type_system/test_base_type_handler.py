"""Tests for test base type handler."""

import pytest
from app.base_type_handler import BaseTypeHandler
from typing import Any
from app.types import TypeRegistry, TypeInfo


@pytest.fixture
def handler() -> BaseTypeHandler:
    """Test case for handler."""
    # Provide a minimal registry for tests; tests can pass explicit type_info too
    registry: TypeRegistry = {
        "OctetString": {"base_type": "OCTET STRING"},
        "Integer32": {
            "base_type": "INTEGER",
            "constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 100}],
        },
        "ObjectIdentifier": {"base_type": "OBJECT IDENTIFIER"},
    }
    return BaseTypeHandler(type_registry=registry)


def test_initial_in_context_overrides(handler: BaseTypeHandler) -> None:
    """Test case for test_initial_in_context_overrides."""
    ctx = {"initial": 42}
    assert handler.get_default_value("Integer32", ctx) == 42


def test_string_display_hint_unset(handler: BaseTypeHandler) -> None:
    """Test case for test_string_display_hint_unset."""
    type_info: TypeInfo = {"base_type": "OctetString", "display_hint": "t"}
    val = handler.get_default_value("DisplayString", {"type_info": type_info})
    assert val == "Unset"


def test_string_type_info_by_name_returns_unset(handler: BaseTypeHandler) -> None:
    """Test case for test_string_type_info_by_name_returns_unset."""
    # If caller provides type_info with base_type OctetString we should return Unset
    type_info: TypeInfo = {"base_type": "OctetString"}
    val = handler.get_default_value("SomeName", {"type_info": type_info})
    assert val == "Unset"


def test_enum_prefers_common_default(handler: BaseTypeHandler) -> None:
    """Test case for test_enum_prefers_common_default."""
    type_info: TypeInfo = {
        "base_type": "Integer32",
        "enums": [{"name": "unknown", "value": 99}, {"name": "up", "value": 1}],
    }
    assert handler.get_default_value("InterfaceStatus", {"type_info": type_info}) == 99


def test_enum_first_value_fallback(handler: BaseTypeHandler) -> None:
    """Test case for test_enum_first_value_fallback."""
    type_info: TypeInfo = {
        "base_type": "Integer32",
        "enums": [{"name": "up", "value": 1}, {"name": "down", "value": 2}],
    }
    assert handler.get_default_value("IfState", {"type_info": type_info}) == 1


def test_integer_constraints_choose_zero_or_min(handler: BaseTypeHandler) -> None:
    """Test case for test_integer_constraints_choose_zero_or_min."""
    # 0 in range
    type_info: TypeInfo = {
        "base_type": "Integer32",
        "constraints": [{"type": "ValueRangeConstraint", "min": -5, "max": 5}],
    }
    assert handler.get_default_value("RangeType", {"type_info": type_info}) == 0
    # 0 not in range -> min
    type_info2: TypeInfo = {
        "base_type": "Integer32",
        "constraints": [{"type": "ValueRangeConstraint", "min": 10, "max": 20}],
    }
    assert handler.get_default_value("RangeType", {"type_info": type_info2}) == 10


def test_octet_ip_and_mac_and_bits_and_default_bytes(handler: BaseTypeHandler) -> None:
    """Test case for test_octet_ip_and_mac_and_bits_and_default_bytes."""
    # IpAddress special case
    assert handler.get_default_value("IpAddress", {}) == "0.0.0.0"

    # Mac-like name
    val = handler.get_default_value(
        "EthernetMacAddress", {"type_info": {"base_type": "OctetString"}}
    )
    assert val == "00:00:00:00:00:00"

    # Bits syntax
    type_info: TypeInfo = {"base_type": "OctetString", "syntax": "BITS"}
    assert handler.get_default_value("SomeBits", {"type_info": type_info}) == ""

    # Default octet fallback returns bytes when not human-readable
    type_info2: TypeInfo = {"base_type": "OctetString"}
    assert isinstance(
        handler.get_default_value("OpaqueValue", {"type_info": type_info2}),
        (bytes, bytearray),
    )


def test_object_identifier_default(handler: BaseTypeHandler) -> None:
    """Test case for test_object_identifier_default."""
    type_info: TypeInfo = {"base_type": "ObjectIdentifier"}
    val = handler.get_default_value("MyOid", {"type_info": type_info})
    assert val == (0, 0)


class DummyClass:
    """Test helper class for DummyClass."""

    def __init__(self, v: Any) -> None:
        self.v = v


class DummyBuilder:
    """Test helper class for DummyBuilder."""

    def __init__(self, cls: Any) -> None:
        self._cls = cls

    def import_symbols(self, module: str, name: str) -> tuple[Any, ...]:
        """Test case for import_symbols."""
        return (self._cls,)


def test_create_pysnmp_value_uses_mib_builder_class(handler: BaseTypeHandler) -> None:
    """Test case for test_create_pysnmp_value_uses_mib_builder_class."""
    dummy = DummyClass
    mb = DummyBuilder(dummy)
    out = handler.create_pysnmp_value("SomeType", 123, mib_builder=mb)
    assert isinstance(out, DummyClass) and out.v == 123


def test_create_pysnmp_value_returns_raw_when_no_builder(
    handler: BaseTypeHandler,
) -> None:
    """Test case for test_create_pysnmp_value_returns_raw_when_no_builder."""
    assert handler.create_pysnmp_value("SomeType", 7, mib_builder=None) == 7


def test_validate_value_integer_and_octets_and_oid(handler: BaseTypeHandler) -> None:
    """Test case for test_validate_value_integer_and_octets_and_oid."""
    assert handler.validate_value("Integer32", 5)
    assert handler.validate_value("Integer32", True)
    assert not handler.validate_value("Integer32", "x")

    assert handler.validate_value("OctetString", b"\x01\x02")
    assert handler.validate_value("OctetString", "abc")
    assert not handler.validate_value("OctetString", 123)

    assert not handler.validate_value("ObjectIdentifier", "1.2.3")
    assert handler.validate_value("ObjectIdentifier", (1, 2, 3))


def test_get_default_value_prefers_context_type_info(handler: BaseTypeHandler) -> None:
    """Test case for test_get_default_value_prefers_context_type_info."""
    # If caller provides full type_info including constraints, it should be used
    type_info: TypeInfo = {
        "base_type": "Integer32",
        "constraints": [{"type": "ValueRangeConstraint", "min": 10, "max": 20}],
    }
    assert handler.get_default_value("Integer32", {"type_info": type_info}) == 10
