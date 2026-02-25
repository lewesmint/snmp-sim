"""SNMP trap/inform sender utilities built on top of PySNMP async HLAPI."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    NotificationType,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.smi import builder as snmp_builder
from pysnmp.smi import error as snmp_error

OidIndex: TypeAlias = int | str | tuple[int, ...]
VarBindValue: TypeAlias = Any
VarBindSpec: TypeAlias = (
    ObjectType
    | tuple[str, str, VarBindValue]
    | tuple[str, str, VarBindValue, OidIndex]
)


class TrapSender:
    """Encapsulates SNMP notification sending using PySNMP."""

    def __init__(
        self,
        dest: tuple[str, int] = ("localhost", 162),
        community: str = "public",
        logger: logging.Logger | None = None,
        snmp_engine: SnmpEngine | None = None,
    ) -> None:
        """Initialize destination, credentials, logger, and SNMP engine state."""
        self._uses_external_engine = snmp_engine is not None
        self.snmp_engine: SnmpEngine = snmp_engine if snmp_engine is not None else SnmpEngine()
        self.dest = dest
        self.community = community
        self.logger = logger or logging.getLogger(__name__)
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._configure_mib_sources(self.snmp_engine)

    def _configure_mib_sources(self, engine: SnmpEngine) -> None:
        try:
            mib_builder = engine.get_mib_builder()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        compiled_dir = Path(__file__).resolve().parent.parent / "compiled-mibs"
        if not compiled_dir.exists():
            return

        mib_source = snmp_builder.DirMibSource(str(compiled_dir))

        add_sources = getattr(mib_builder, "add_mib_sources", None)
        if callable(add_sources):
            with suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                add_sources(mib_source)
                return

        add_sources_alt = getattr(mib_builder, "addMibSources", None)
        if callable(add_sources_alt):
            with suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                add_sources_alt(mib_source)

    @staticmethod
    def _coerce_varbind(spec: VarBindSpec) -> ObjectType:
        if isinstance(spec, ObjectType):
            return spec

        if (
            spec.__class__.__name__ == "ObjectType"
            and spec.__class__.__module__.startswith("pysnmp")
            and hasattr(spec, "resolveWithMib")
        ):
            return cast("ObjectType", spec)

        if not isinstance(spec, tuple):
            msg = (
                "extra_varbinds entries must be ObjectType or tuple, got "
                f"{type(spec).__name__}: {spec!r}"
            )
            raise TypeError(msg)

        mib, symbol, value, *rest = spec

        if not rest:
            return ObjectType(ObjectIdentity(mib, symbol, 0), cast("VarBindValue", value))

        if len(rest) == 1:
            index = rest[0]
            if isinstance(index, tuple):
                return ObjectType(
                    ObjectIdentity(mib, symbol, *index), cast("VarBindValue", value)
                )
            return ObjectType(ObjectIdentity(mib, symbol, index), cast("VarBindValue", value))

        msg = (
            "Unsupported varbind tuple. Expected (mib, symbol, value) or "
            f"(mib, symbol, value, index). Got: {spec!r}"
        )
        raise ValueError(msg)

    async def send_mib_notification_async(
        self,
        mib: str,
        notification: str,
        trap_type: Literal["trap", "inform"] = "inform",
        extra_varbinds: Sequence[VarBindSpec] | None = None,
    ) -> None:
        """Send a MIB-defined notification to the configured destination."""
        engine = self.snmp_engine
        notif = NotificationType(ObjectIdentity(mib, notification))

        if extra_varbinds:
            coerced = [self._coerce_varbind(vb) for vb in extra_varbinds]
            notif = notif.add_var_binds(*coerced)

        async def _send_with(target_engine: SnmpEngine) -> tuple[object, object, object, object]:
            result = await send_notification(
                target_engine,
                CommunityData(self.community),
                await UdpTransportTarget.create(self.dest),
                ContextData(),
                trap_type,
                notif,
            )
            return cast("tuple[object, object, object, object]", result)

        try:
            error_indication, error_status, error_index, _ = await _send_with(engine)
        except snmp_error.NoSuchInstanceError:
            if self._uses_external_engine:
                raise
            self.logger.warning(
                "Notification send hit NoSuchInstanceError; "
                "resetting internal SnmpEngine and retrying once"
            )
            self.snmp_engine = SnmpEngine()
            self._configure_mib_sources(self.snmp_engine)
            error_indication, error_status, error_index, _ = await _send_with(self.snmp_engine)

        if error_indication:
            self.logger.error("Notification send error: %s", error_indication)
            return

        if error_status:
            self.logger.error(
                "Notification send error: %s at %s",
                error_status,
                error_index,
            )
            return

        self.logger.info(
            "Notification sent to %s:%s %s::%s",
            self.dest[0],
            self.dest[1],
            mib,
            notification,
        )

    def send_mib_notification(
        self,
        mib: str,
        notification: str,
        trap_type: Literal["trap", "inform"] = "inform",
        extra_varbinds: Sequence[VarBindSpec] | None = None,
    ) -> None:
        """Send notification from synchronous code."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                self.send_mib_notification_async(
                    mib=mib,
                    notification=notification,
                    trap_type=trap_type,
                    extra_varbinds=extra_varbinds,
                )
            )
            return

        task = loop.create_task(
            self.send_mib_notification_async(
                mib=mib,
                notification=notification,
                trap_type=trap_type,
                extra_varbinds=extra_varbinds,
            )
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
