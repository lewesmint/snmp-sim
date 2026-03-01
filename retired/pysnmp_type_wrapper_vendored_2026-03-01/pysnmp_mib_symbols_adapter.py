"""PySNMP mibSymbols adapter.

Contains dynamic symbol-map traversal and reflection so app services can consume
stable typed methods instead of direct ``mibSymbols`` manipulation.
"""

from __future__ import annotations

from typing import cast

from ._adapter_exceptions import ADAPTER_EXCEPTIONS
from .interfaces import MutableScalarInstance, MibSymbolMap, SupportsMibSymbolsBuilder


class PysnmpMibSymbolsAdapter:
    """Typed adapter over dynamic ``mib_builder.mibSymbols`` structures."""

    def __init__(self, mib_builder: object) -> None:
        """Bind the adapter to a concrete PySNMP MIB builder instance."""
        self._mib_builder = mib_builder

    @property
    def _symbols(self) -> MibSymbolMap:
        return cast(SupportsMibSymbolsBuilder, self._mib_builder).mibSymbols

    def load_symbol_class(self, module: str, symbol: str) -> type[object] | None:
        """Load class-like symbol from MIB builder imports."""
        builder = cast(SupportsMibSymbolsBuilder, self._mib_builder)
        try:
            symbols = builder.import_symbols(module, symbol)
        except ADAPTER_EXCEPTIONS:
            return None
        if not symbols:
            return None
        loaded_symbol = symbols[0]
        return loaded_symbol if isinstance(loaded_symbol, type) else None

    @staticmethod
    def _oid_from_symbol(symbol_obj: object) -> tuple[int, ...] | None:
        try:
            symbol_name = getattr(symbol_obj, "name", None)
        except ADAPTER_EXCEPTIONS:
            return None
        if not isinstance(symbol_name, tuple):
            return None
        if not all(isinstance(part, int) for part in symbol_name):
            return None
        return cast("tuple[int, ...]", symbol_name)

    def find_scalar_instance_by_oid(
        self,
        oid: tuple[int, ...],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None:
        """Return scalar instance matching `oid`, if present."""
        for module_symbols in self._symbols.values():
            for symbol_obj in module_symbols.values():
                if not isinstance(symbol_obj, scalar_instance_cls):
                    continue
                symbol_oid = self._oid_from_symbol(symbol_obj)
                if symbol_oid == oid:
                    return cast("MutableScalarInstance", symbol_obj)
        return None

    def get_all_named_oids(self) -> dict[str, tuple[int, ...]]:
        """Build a map of symbol name to OID for all symbols exposing tuple OIDs."""
        oid_map: dict[str, tuple[int, ...]] = {}
        for module_symbols in self._symbols.values():
            for symbol_name, symbol_obj in module_symbols.items():
                oid = self._oid_from_symbol(symbol_obj)
                if oid is None:
                    continue
                oid_map[symbol_name] = oid
        return oid_map

    def lookup_symbol_for_oid(self, oid: tuple[int, ...]) -> tuple[str | None, str | None]:
        """Return module/symbol names for exact OID match."""
        for module_name, module_symbols in self._symbols.items():
            for symbol_name, symbol_obj in module_symbols.items():
                symbol_oid = self._oid_from_symbol(symbol_obj)
                if symbol_oid == oid:
                    return module_name, symbol_name
        return None, None

    def iter_scalar_instances(
        self,
        scalar_instance_cls: type[object],
    ) -> list[tuple[str, str, MutableScalarInstance]]:
        """Collect scalar instances with module/symbol names."""
        out: list[tuple[str, str, MutableScalarInstance]] = []
        for module_name, module_symbols in self._symbols.items():
            for symbol_name, symbol_obj in module_symbols.items():
                if not isinstance(symbol_obj, scalar_instance_cls):
                    continue
                if self._oid_from_symbol(symbol_obj) is None:
                    continue
                out.append((module_name, symbol_name, cast("MutableScalarInstance", symbol_obj)))
        return out

    def find_scalar_instance_by_candidate_oids(
        self,
        candidate_oids: list[tuple[int, ...]],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None:
        """Return first scalar instance matching one of the candidate OIDs."""
        candidates = set(candidate_oids)
        for module_symbols in self._symbols.values():
            for symbol_obj in module_symbols.values():
                if not isinstance(symbol_obj, scalar_instance_cls):
                    continue
                symbol_oid = self._oid_from_symbol(symbol_obj)
                if symbol_oid in candidates:
                    return cast("MutableScalarInstance", symbol_obj)
        return None

    def get_symbol_access(self, symbol_obj: object) -> str | None:
        """Read max-access text using PySNMP-like method/attribute conventions."""
        try:
            method = getattr(symbol_obj, "getMaxAccess", None)
        except ADAPTER_EXCEPTIONS:
            method = None
        if callable(method):
            try:
                access = method()
                if access is not None:
                    return str(access)
            except ADAPTER_EXCEPTIONS:
                pass

        try:
            access_attr = getattr(symbol_obj, "maxAccess", None)
        except ADAPTER_EXCEPTIONS:
            access_attr = None
        if access_attr is None:
            return None
        return str(access_attr)

    def find_column_oid_for_entry(
        self,
        column_name: str,
        entry_oid: tuple[int, ...],
    ) -> tuple[int, ...] | None:
        """Resolve a column OID when column belongs to an entry subtree."""
        for module_symbols in self._symbols.values():
            symbol_obj = module_symbols.get(column_name)
            if symbol_obj is None:
                continue
            column_oid = self._oid_from_symbol(symbol_obj)
            if column_oid is None:
                continue
            if len(column_oid) > len(entry_oid) and column_oid[: len(entry_oid)] == entry_oid:
                return column_oid
        return None

    def find_template_instance_for_column(
        self,
        column_name: str,
        scalar_instance_cls: type[object],
    ) -> tuple[str, MutableScalarInstance, tuple[int, ...]] | None:
        """Find existing instance for column and derive reusable column OID prefix."""
        prefix = f"{column_name}Inst_"
        for module_name, module_symbols in self._symbols.items():
            for symbol_name, symbol_obj in module_symbols.items():
                if not isinstance(symbol_obj, scalar_instance_cls):
                    continue
                if not symbol_name.startswith(prefix):
                    continue
                current_name = self._oid_from_symbol(symbol_obj)
                if current_name is None:
                    continue

                suffix = "Inst_"
                current_index_str = symbol_name.split(suffix, 1)[1] if suffix in symbol_name else ""
                current_index_len = len([part for part in current_index_str.split("_") if part])
                if 0 < current_index_len < len(current_name):
                    column_oid = current_name[:-current_index_len]
                else:
                    column_oid = current_name[:-1]

                if not column_oid:
                    continue

                return module_name, cast("MutableScalarInstance", symbol_obj), column_oid

        return None

    def upsert_symbol(self, module_name: str, symbol_name: str, symbol_obj: object) -> bool:
        """Insert/update symbol object in a module symbol map."""
        module_symbols = self._symbols.get(module_name)
        if module_symbols is None:
            return False
        if not isinstance(module_symbols, dict):
            return False
        module_symbols[symbol_name] = symbol_obj
        return True
