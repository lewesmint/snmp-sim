import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

ADAPTER_EXCEPTIONS: tuple[type[Exception], ...]

@dataclass(frozen=True)
class RuntimeSnmpContextArgs:
    mib_builder: object | None
    mib_scalar_instance: object | None
    mib_table: object | None
    mib_table_row: object | None
    mib_table_column: object | None

class RuntimeMibRegistrar(Protocol):
    def register_all_mibs(self, mib_jsons: Mapping[str, object]) -> None: ...
    def _decode_value(self, value: object) -> object: ...

def create_runtime_mib_registrar(
    *,
    logger: logging.Logger,
    start_time: float,
    context_args: RuntimeSnmpContextArgs,
) -> RuntimeMibRegistrar: ...

def decode_value_with_runtime_registrar(
    value: object,
    *,
    logger: logging.Logger,
    start_time: float,
) -> object: ...
