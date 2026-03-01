from collections.abc import Callable, Mapping
from typing import Protocol, TypedDict, runtime_checkable

type MibSymbolMap = Mapping[str, Mapping[str, object]]
type SnmpTypeFactory = Callable[..., object]
type MibJsonObject = dict[str, object]

class ColumnMeta(TypedDict, total=False):
    oid: list[int]
    type: str
    access: str
    initial: object

class EntryMeta(TypedDict, total=False):
    oid: list[int]
    type: str
    indexes: list[str]
    index_from: str | list[str]

class TableMeta(TypedDict, total=False):
    oid: list[int]
    type: str
    access: str
    rows: list[MibJsonObject]

class TableData(TypedDict):
    table: TableMeta
    entry: EntryMeta
    columns: dict[str, ColumnMeta]

@runtime_checkable
class SupportsMibBuilder(Protocol):
    def import_symbols(self, module: str, *symbols: str) -> tuple[object, ...]: ...
    def export_symbols(self, module: str, *symbols: str) -> object: ...

@runtime_checkable
class SupportsMibSymbolsBuilder(SupportsMibBuilder, Protocol):
    mibSymbols: MibSymbolMap  # noqa: N815

@runtime_checkable
class SupportsSnmpTypeResolver(Protocol):
    def resolve_type_factory(
        self,
        base_type: str,
        mib_builder: SupportsMibBuilder | None,
    ) -> SnmpTypeFactory | None: ...

@runtime_checkable
class MutableScalarInstance(Protocol):
    name: tuple[int, ...]
    syntax: object

@runtime_checkable
class SupportsClone(Protocol):
    def clone(self, value: object) -> object: ...

@runtime_checkable
class SupportsMibSymbolsAdapter(Protocol):
    def load_symbol_class(self, module: str, symbol: str) -> type[object] | None: ...
    def find_scalar_instance_by_oid(
        self,
        oid: tuple[int, ...],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None: ...
    def get_all_named_oids(self) -> dict[str, tuple[int, ...]]: ...
    def lookup_symbol_for_oid(self, oid: tuple[int, ...]) -> tuple[str | None, str | None]: ...
    def iter_scalar_instances(
        self,
        scalar_instance_cls: type[object],
    ) -> list[tuple[str, str, MutableScalarInstance]]: ...
    def find_scalar_instance_by_candidate_oids(
        self,
        candidate_oids: list[tuple[int, ...]],
        scalar_instance_cls: type[object],
    ) -> MutableScalarInstance | None: ...
    def get_symbol_access(self, symbol_obj: object) -> str | None: ...
    def find_column_oid_for_entry(
        self,
        column_name: str,
        entry_oid: tuple[int, ...],
    ) -> tuple[int, ...] | None: ...
    def find_template_instance_for_column(
        self,
        column_name: str,
        scalar_instance_cls: type[object],
    ) -> tuple[str, MutableScalarInstance, tuple[int, ...]] | None: ...
    def upsert_symbol(self, module_name: str, symbol_name: str, symbol_obj: object) -> bool: ...
