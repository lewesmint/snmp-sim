import importlib
import types
import logging
import pytest
from typing import Any, Tuple

from app.base_type_handler import BaseTypeHandler
from app.types import TypeRegistry
from pytest_mock import MockerFixture


@pytest.fixture
def handler() -> BaseTypeHandler:
    registry: TypeRegistry = {
        "OctetString": {"base_type": "OCTET STRING"},
        "Integer32": {"base_type": "INTEGER"},
        "ObjectIdentifier": {"base_type": "OBJECT IDENTIFIER"},
    }
    return BaseTypeHandler(type_registry=registry)


def test_resolve_to_base_type_recursive_lookup() -> None:
    registry: TypeRegistry = {
        "MyTC": {"base_type": "DisplayString"},
        "DisplayString": {"base_type": "OctetString"},
        "OctetString": {"base_type": "OCTET STRING"},
    }
    h = BaseTypeHandler(type_registry=registry)

    assert h.resolve_to_base_type("MyTC") == "OCTET STRING"


def test_resolve_to_base_type_fallback_logs(
    caplog: pytest.LogCaptureFixture, handler: BaseTypeHandler
) -> None:
    caplog.set_level(logging.WARNING)
    # Unknown type - should warn and default to INTEGER
    assert handler.resolve_to_base_type("CompletelyUnknown") == "INTEGER"
    assert any("Could not resolve base type" in r.message for r in caplog.records)


def test_create_pysnmp_value_handles_type_class_exception(
    monkeypatch: pytest.MonkeyPatch,
    handler: BaseTypeHandler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BadCls:
        def __init__(self, _v: Any) -> None:
            raise ValueError("boom")

    class BadBuilder:
        def import_symbols(self, module: str, name: str) -> Tuple[Any, ...]:
            return (BadCls,)

    caplog.set_level(logging.WARNING)
    out = handler.create_pysnmp_value("SomeType", 5, mib_builder=BadBuilder())
    # Should return raw value on construction failure
    assert out == 5
    assert any("Failed to create SomeType" in r.message for r in caplog.records)


def test_create_pysnmp_value_fallback_to_rfc1902(
    monkeypatch: pytest.MonkeyPatch, handler: BaseTypeHandler
) -> None:
    # Simulate missing MIB type and patch rfc1902
    class FakeInt:
        def __init__(self, v: Any) -> None:
            self.v = int(v)

    fake_rfc = types.SimpleNamespace(
        Integer32=FakeInt,
        OctetString=lambda x: x if isinstance(x, bytes) else x.encode("utf-8"),
        ObjectIdentifier=lambda x: tuple(x),
    )
    # Ensure we patch the already-imported pysnmp.proto package (if present)
    proto_mod = importlib.import_module("pysnmp.proto")
    monkeypatch.setattr(proto_mod, "rfc1902", fake_rfc, raising=False)

    # Use a builder that raises to force fallback
    class RaisingBuilder:
        def import_symbols(self, module: str, name: str) -> Tuple[Any, ...]:
            raise RuntimeError("nope")

    out = handler.create_pysnmp_value("Integer32", 42, mib_builder=RaisingBuilder())
    assert hasattr(out, "v") and out.v == 42

    out2 = handler.create_pysnmp_value("OctetString", "foo", mib_builder=RaisingBuilder())
    assert isinstance(out2, bytes)

    out3 = handler.create_pysnmp_value("ObjectIdentifier", (1, 2, 3), mib_builder=RaisingBuilder())
    assert out3 == (1, 2, 3)


def test_get_pysnmp_type_class_prefers_mib_builder_then_rfc1902(
    monkeypatch: pytest.MonkeyPatch, handler: BaseTypeHandler
) -> None:
    class MyClass:
        pass

    class Builder:
        def import_symbols(self, module: str, name: str) -> Tuple[Any, ...]:
            if module == "SNMPv2-SMI":
                return (MyClass,)
            raise RuntimeError

    mb = Builder()
    got = handler._get_pysnmp_type_class("SomeName", mb)
    assert got is MyClass

    # Now simulate import_symbols failing and rfc1902 providing class
    class FailBuilder:
        def import_symbols(self, module: str, name: str) -> Tuple[Any, ...]:
            raise RuntimeError

    class RfcCls:
        pass

    # Patch the existing pysnmp.proto.rfc1902 if the package is loaded
    proto_mod = importlib.import_module("pysnmp.proto")
    monkeypatch.setattr(proto_mod, "rfc1902", types.SimpleNamespace(SomeName=RfcCls), raising=False)

    got2 = handler._get_pysnmp_type_class("SomeName", FailBuilder())
    assert got2 is RfcCls


def test_validate_value_integer_range_and_octet_size(handler: BaseTypeHandler) -> None:
    # Integer range check using constraints['range'] format
    type_info = {"base_type": "Integer32", "constraints": {"range": [5, 10]}}
    h = BaseTypeHandler(type_registry={"Foo": type_info})
    assert not h.validate_value("Foo", 4)
    assert h.validate_value("Foo", 6)

    # Octet string exact size
    type_info2 = {"base_type": "OctetString", "constraints": {"size": 3}}
    h2 = BaseTypeHandler(type_registry={"Bar": type_info2})
    assert not h2.validate_value("Bar", b"aa")
    assert h2.validate_value("Bar", b"abc")

    # Octet string size range
    type_info3 = {"base_type": "OctetString", "constraints": {"size": [2, 4]}}
    h3 = BaseTypeHandler(type_registry={"Baz": type_info3})
    assert not h3.validate_value("Baz", b"a")
    assert h3.validate_value("Baz", b"abc")


def test_validate_oid_element_types(handler: BaseTypeHandler) -> None:
    assert not handler.validate_value("ObjectIdentifier", ["1", 2])
    assert not handler.validate_value("ObjectIdentifier", (1, "2"))


def test_resolve_to_base_type_already_base_type(handler: BaseTypeHandler) -> None:
    """Test that base ASN.1 types are returned as-is."""
    assert handler.resolve_to_base_type("INTEGER") == "INTEGER"
    assert handler.resolve_to_base_type("OCTET STRING") == "OCTET STRING"
    assert handler.resolve_to_base_type("OBJECT IDENTIFIER") == "OBJECT IDENTIFIER"


def test_get_default_value_integer_no_constraints_returns_zero(
    handler: BaseTypeHandler,
) -> None:
    """Test that INTEGER types without constraints default to 0."""
    type_info = {"base_type": "INTEGER"}
    result = handler.get_default_value("SomeInteger", {"type_info": type_info})
    assert result == 0


def test_get_default_value_unexpected_base_type_logs_warning(
    caplog: pytest.LogCaptureFixture, handler: BaseTypeHandler, mocker: MockerFixture
) -> None:
    """Test that unexpected base types log a warning and return 0."""
    caplog.set_level(logging.WARNING)

    # Mock resolve_to_base_type to return an unexpected base type
    mocker.patch.object(handler, "resolve_to_base_type", return_value="UNKNOWN_BASE_TYPE")

    type_info = {"base_type": "SomeType"}
    result = handler.get_default_value("SomeType", {"type_info": type_info})
    assert result == 0
    assert any(
        "Unexpected base type 'UNKNOWN_BASE_TYPE'" in record.message for record in caplog.records
    )


def test_create_pysnmp_value_rfc1902_fallback_exception(
    caplog: pytest.LogCaptureFixture, handler: BaseTypeHandler, mocker: MockerFixture
) -> None:
    """Test that rfc1902 fallback logs errors on exception."""
    caplog.set_level(logging.ERROR)

    # Mock _get_pysnmp_type_class to return None so it goes to fallback
    mocker.patch.object(handler, "_get_pysnmp_type_class", return_value=None)

    # Mock the rfc1902 import to raise an exception in the fallback
    mock_rfc1902 = mocker.MagicMock()
    mock_rfc1902.Integer32.side_effect = ValueError("rfc1902 error")
    mocker.patch("pysnmp.proto.rfc1902", mock_rfc1902)

    # Pass a dummy mib_builder so it doesn't return early
    result = handler.create_pysnmp_value("Integer32", 42, mib_builder=mocker.MagicMock())
    assert result == 42  # Should return raw value
    assert any("Failed to create PySNMP value" in record.message for record in caplog.records)


def test_get_pysnmp_type_class_rfc1902_exception(
    caplog: pytest.LogCaptureFixture, handler: BaseTypeHandler
) -> None:
    """Test that _get_pysnmp_type_class handles rfc1902 exceptions gracefully."""
    caplog.set_level(logging.ERROR)

    # Mock rfc1902 to raise an exception
    class FakeRfc:
        def __getattr__(self, name: str) -> Any:
            raise AttributeError(f"no such type: {name}")

    fake_rfc = FakeRfc()

    # Patch the rfc1902 import
    import importlib

    proto_mod = importlib.import_module("pysnmp.proto")
    original_rfc1902 = getattr(proto_mod, "rfc1902", None)
    setattr(proto_mod, "rfc1902", fake_rfc)

    try:
        # Test with a builder that fails
        class FailingBuilder:
            def import_symbols(self, module: str, name: str) -> Tuple[Any, ...]:
                raise RuntimeError("builder failed")

        result = handler._get_pysnmp_type_class("SomeType", FailingBuilder())
        assert result is None  # Should return None on exception
    finally:
        # Restore original
        if original_rfc1902 is not None:
            setattr(proto_mod, "rfc1902", original_rfc1902)
