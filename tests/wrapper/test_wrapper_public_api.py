"""Public API smoke tests for the wrapper package."""

from __future__ import annotations

import pysnmp_type_wrapper as wrapper


def test_wrapper_public_exports_present() -> None:
    """Wrapper module should expose the documented public API names."""
    expected_exports = {
        "ColumnMeta",
        "EntryMeta",
        "MibSymbolMap",
        "MibJsonObject",
        "MibNodeLike",
        "MibScalarClass",
        "MibScalarInstanceClass",
        "MibTableClass",
        "MibTableColumnClass",
        "MibTableRowClass",
        "MutableScalarInstance",
        "PysnmpMibSymbolsAdapter",
        "PysnmpRfc1902Adapter",
        "PysnmpTypeResolver",
        "RUNTIME_ADAPTER_EXCEPTIONS",
        "RuntimeSnmpContextArgs",
        "Snmpv2SmiClasses",
        "SnmpTypeFactory",
        "SupportsClone",
        "SupportsMibBuilder",
        "SupportsBoundaryMibBuilder",
        "SupportsBoundarySnmpEngine",
        "SupportsMibSymbolsBuilder",
        "SupportsMibSymbolsAdapter",
        "SupportsSnmpTypeResolver",
        "TableData",
        "TableMeta",
        "create_runtime_mib_registrar",
        "decode_value_with_runtime_registrar",
    }

    exported = set(wrapper.__all__)
    missing = expected_exports - exported
    unexpected = exported - expected_exports
    assert not missing, f"Missing exports: {sorted(missing)}"
    assert not unexpected, f"Unexpected exports: {sorted(unexpected)}"


def test_wrapper_public_classes_are_constructible() -> None:
    """Core adapter classes should be importable and constructible."""
    rfc_adapter = wrapper.PysnmpRfc1902Adapter(object())
    mib_adapter = wrapper.PysnmpMibSymbolsAdapter(object())
    resolver = wrapper.PysnmpTypeResolver()

    assert isinstance(rfc_adapter, wrapper.PysnmpRfc1902Adapter)
    assert isinstance(mib_adapter, wrapper.PysnmpMibSymbolsAdapter)
    assert isinstance(resolver, wrapper.PysnmpTypeResolver)
