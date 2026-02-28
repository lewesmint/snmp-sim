"""Runtime adapter for dynamic MibRegistrar module loading.

Keeps importlib/getattr reflection at the boundary so app services can use
simple helper calls.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

ADAPTER_EXCEPTIONS = (
    AttributeError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
    RuntimeError,
)


@dataclass(frozen=True)
class RuntimeSnmpContextArgs:
    """Optional SNMPContext constructor arguments for dynamic registrar init."""

    mib_builder: object | None
    mib_scalar_instance: object | None
    mib_table: object | None
    mib_table_row: object | None
    mib_table_column: object | None


class RuntimeMibRegistrar(Protocol):
    """Minimal runtime registrar capability used by SNMPAgent."""

    def register_all_mibs(self, mib_jsons: Mapping[str, object]) -> None:
        """Register all loaded MIB schemas."""

    def _decode_value(self, value: object) -> object:
        """Decode raw SNMP value payloads."""


def create_runtime_mib_registrar(
    *,
    logger: logging.Logger,
    start_time: float,
    context_args: RuntimeSnmpContextArgs,
) -> RuntimeMibRegistrar:
    """Create registrar instance from dynamic `app.mib_registrar` module.

    Supports modules that expose `MibRegistrar` with optional `SNMPContext`.
    """
    mib_registrar_module = importlib.import_module("app.mib_registrar")
    registrar_cls = mib_registrar_module.MibRegistrar
    snmp_context_cls = None
    try:
        snmp_context_cls = mib_registrar_module.SNMPContext
    except ADAPTER_EXCEPTIONS:
        snmp_context_cls = None

    if snmp_context_cls is not None:
        snmp_context = snmp_context_cls(
            mib_builder=context_args.mib_builder,
            mib_scalar_instance=context_args.mib_scalar_instance,
            mib_table=context_args.mib_table,
            mib_table_row=context_args.mib_table_row,
            mib_table_column=context_args.mib_table_column,
        )
        registrar = registrar_cls(
            snmp_context=snmp_context,
            logger=logger,
            start_time=start_time,
        )
        return cast("RuntimeMibRegistrar", registrar)

    registrar = registrar_cls(
        logger=logger,
        start_time=start_time,
    )
    return cast("RuntimeMibRegistrar", registrar)


def decode_value_with_runtime_registrar(
    value: object,
    *,
    logger: logging.Logger,
    start_time: float,
) -> object:
    """Decode value using a transient dynamically-loaded registrar instance."""
    registrar = create_runtime_mib_registrar(
        logger=logger,
        start_time=start_time,
        context_args=RuntimeSnmpContextArgs(
            mib_builder=None,
            mib_scalar_instance=None,
            mib_table=None,
            mib_table_row=None,
            mib_table_column=None,
        ),
    )
    return registrar._decode_value(value)
