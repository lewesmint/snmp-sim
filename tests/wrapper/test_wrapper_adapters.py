"""Behavior tests for wrapper adapters using lightweight fakes."""

from __future__ import annotations

from dataclasses import dataclass

from pysnmp_type_wrapper.pysnmp_mib_symbols_adapter import PysnmpMibSymbolsAdapter
from pysnmp_type_wrapper.pysnmp_type_resolver import PysnmpTypeResolver


@dataclass
class _FakeScalarInstance:
    name: tuple[int, ...]
    syntax: object


class _FakeMibBuilder:
    def __init__(self) -> None:
        self.mibSymbols: dict[str, dict[str, object]] = {
            "TEST-MIB": {
                "myScalarInst_1": _FakeScalarInstance(name=(1, 3, 6, 1, 4, 1, 999, 1), syntax=5),
                "myColumn": _FakeScalarInstance(name=(1, 3, 6, 1, 4, 1, 999, 2, 1), syntax=1),
            }
        }

    def import_symbols(self, module: str, *symbols: str) -> tuple[object, ...]:
        if module == "SNMPv2-SMI" and symbols == ("Integer32",):
            return (int,)
        return ()

    def export_symbols(self, module: str, *symbols: str) -> object:
        return {"module": module, "symbols": symbols}


def test_mib_symbols_adapter_lookup_and_upsert() -> None:
    """Adapter should find, list, and upsert symbols against a fake builder."""
    builder = _FakeMibBuilder()
    adapter = PysnmpMibSymbolsAdapter(builder)

    found = adapter.find_scalar_instance_by_oid((1, 3, 6, 1, 4, 1, 999, 1), _FakeScalarInstance)
    assert found is not None
    assert found.syntax == 5

    all_named = adapter.get_all_named_oids()
    assert "myScalarInst_1" in all_named

    inserted = adapter.upsert_symbol("TEST-MIB", "another", _FakeScalarInstance((1, 2, 3), syntax=7))
    assert inserted


def test_type_resolver_prefers_mib_builder() -> None:
    """Resolver should return builder-provided factories when available."""
    resolver = PysnmpTypeResolver()
    resolved = resolver.resolve_type_factory("Integer32", _FakeMibBuilder())
    assert resolved is int


def test_type_resolver_returns_none_for_unknown_type() -> None:
    """Resolver should return None when nothing resolves."""
    resolver = PysnmpTypeResolver()
    resolved = resolver.resolve_type_factory("DefinitelyNotAType", _FakeMibBuilder())
    assert resolved is None
