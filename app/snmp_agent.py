"""SNMPAgent: Main orchestrator for the SNMP agent (initial workflow)."""

# pyright: reportAbstractUsage=false

from __future__ import annotations

# pylint: disable=invalid-name,line-too-long,too-many-lines,missing-class-docstring
# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-branches
# pylint: disable=too-many-statements,too-many-nested-blocks,too-many-return-statements
# ruff: noqa: B007,C901,D101,D107,E501,EM101,EM102,FBT001,FBT002,I001,N806
# ruff: noqa: PERF102,PERF203,PERF401,PERF403,PLC0415,PLR0911,PLR0912,PLR0914
# ruff: noqa: PLR0915,PLR2004,PLW2901,PTH103,PTH120,PTH123,PTH204,RET504,RUF005
# ruff: noqa: RUF059,RUF100,S101,S104,SIM102,SLF001,T201,TC002,TC003,TC006,TRY003
# ruff: noqa: TRY300,TRY400,TRY401,UP037,UP045

import json
import logging
import os
import signal
import sys
import time
import traceback
import contextlib
from types import FrameType
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

from pysnmp import debug as pysnmp_debug
from pysnmp.entity.engine import SnmpEngine
from pysnmp.entity.rfc3413.context import SnmpContext
from pysnmp.smi.builder import MibBuilder
from pysnmp_type_wrapper.mib_registrar_runtime_adapter import (
    ADAPTER_EXCEPTIONS as RUNTIME_ADAPTER_EXCEPTIONS,
    RuntimeSnmpContextArgs,
    create_runtime_mib_registrar,
    decode_value_with_runtime_registrar,
)
from pysnmp_type_wrapper.pysnmp_mib_symbols_adapter import PysnmpMibSymbolsAdapter

# Load type converter plugins
from app.app_config import AppConfig
from app.app_logger import AppLogger
from app.snmp_agent_augments_mixin import SNMPAgentAugmentsMixin
from app.snmp_agent_runtime_workflow_mixin import SNMPAgentRuntimeWorkflowMixin
from app.snmp_agent_state_loading_mixin import SNMPAgentStateLoadingMixin
from app.snmp_agent_table_mutation_mixin import SNMPAgentTableMutationMixin
from app.snmp_agent_table_state_mixin import SNMPAgentTableStateMixin
from app.value_links import get_link_manager

if TYPE_CHECKING:
    from pysnmp_type_wrapper.interfaces import (
        SupportsMibSymbolsAdapter,
    )
    from pysnmp_type_wrapper.raw_boundary_types import SupportsBoundaryMibBuilder

    class SupportsClone(Protocol):
        """Protocol for values exposing a clone operation."""

        def clone(self, value: object) -> object: ...  # noqa: D102

    class MutableScalarInstance(Protocol):
        syntax: object

    type MibScalarClass = type[object]
    type MibScalarInstanceClass = type[object]
    type MibTableClass = type[object]
    type MibTableRowClass = type[object]
    type MibTableColumnClass = type[object]


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type DecodedValue = JsonValue | bytes | bytearray


class TableInstance(TypedDict, total=False):
    column_values: dict[str, JsonValue]
    index_values: dict[str, JsonValue]


class SNMPAgent(
    SNMPAgentRuntimeWorkflowMixin,
    SNMPAgentTableMutationMixin,
    SNMPAgentAugmentsMixin,
    SNMPAgentStateLoadingMixin,
    SNMPAgentTableStateMixin,
):
    """SNMP agent implementation for responding to SNMP requests."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 11161,
        config_path: str = "agent_config.yaml",
        preloaded_model: dict[str, dict[str, JsonValue]] | None = None,
    ) -> None:
        # Set up logging and config
        if not AppLogger._configured:
            self.app_config = AppConfig(config_path)
            AppLogger.configure(self.app_config)
        else:
            self.app_config = AppConfig(config_path)
        self.logger = AppLogger.get(__name__)
        pysnmp_debug.Debug("all")
        self.logger.info("PySNMP debugging enabled")

        self.config_path = config_path
        self.host = host
        self.port = port
        self.snmp_engine: SnmpEngine | None = None
        self.snmp_context: SnmpContext | None = None
        self.mib_builder: MibBuilder | None = None
        self.mib_registrar = None
        self.MibScalar: MibScalarClass | None = None
        self.MibScalarInstance: MibScalarInstanceClass | None = None
        self.MibTable: MibTableClass | None = None
        self.MibTableRow: MibTableRowClass | None = None
        self.MibTableColumn: MibTableColumnClass | None = None
        self.mib_symbols_adapter = None
        self._mib_symbols_adapter_builder: object | None = None
        self.mib_jsons: dict[str, dict[str, JsonValue]] = {}
        # Track agent start time for sysUpTime
        self.start_time = time.time()
        self.preloaded_model = preloaded_model
        self._shutdown_requested = False
        # Overrides: dotted OID -> JSON-serializable value
        self.overrides: dict[str, JsonValue] = {}
        # Table instances: table_oid -> {index_str -> {column_values}}
        self.table_instances: dict[str, dict[str, TableInstance]] = {}
        # Deleted instances: list of instance OIDs marked for deletion
        self.deleted_instances: list[str] = []
        # Map of initial values captured after registration: dotted OID -> JSON-serializable value
        self._initial_values: dict[str, JsonValue] = {}
        # Set of dotted OIDs that are writable (read-write)
        self._writable_oids: set[str] = set()
        # Augmented table metadata (parent table oid -> child table metadata)
        self._augmented_parents: dict[str, list[Any]] = {}
        # Default column values for tables (used when auto-creating augmented rows)
        self._table_defaults: dict[str, dict[str, JsonValue]] = {}

        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum: int, _frame: FrameType | None) -> None:
            # Get signal name; use fallback on Windows where signal.Signals may not have all signals
            try:
                sig_name = signal.Signals(signum).name
            except (ValueError, AttributeError):
                sig_name = f"SIGNAL({signum})"
            self.logger.info(
                "Received signal %s (%s), terminating immediately...",
                sig_name,
                signum,
            )
            # Force immediate exit - don't wait for event loop
            os._exit(0)

        # Register handlers for common termination signals
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # On Unix systems, also handle SIGHUP (not available on Windows)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal_handler)

    def _shutdown(self) -> None:
        """Perform graceful shutdown of the SNMP agent."""
        self.logger.info("Starting graceful shutdown...")

        try:
            if self.snmp_engine is not None:
                self.logger.info("Closing SNMP transport dispatcher...")
                # Close the dispatcher to stop accepting new requests
                if hasattr(self.snmp_engine, "transport_dispatcher"):
                    dispatcher = self.snmp_engine.transport_dispatcher
                    dispatcher.close_dispatcher()
                    self.logger.info("Transport dispatcher closed successfully")

            # Flush and close log handlers
            self.logger.info("Flushing log handlers...")
            for handler in logging.getLogger().handlers:
                handler.flush()

            self.logger.info("Shutdown complete")
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError) as e:
            self.logger.exception("Error during shutdown: %s", e)
        finally:
            # Exit cleanly - use os._exit to ensure termination
            os._exit(0)

    def _register_mib_objects(self) -> None:
        """Register all MIB objects using the MibRegistrar."""
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Create MibRegistrar lazily if it does not exist (tests may call this directly)
        registrar = getattr(self, "mib_registrar", None)
        if registrar is None:
            try:
                runtime_registrar = create_runtime_mib_registrar(
                    logger=self.logger,
                    start_time=self.start_time,
                    context_args=RuntimeSnmpContextArgs(
                        mib_builder=self.mib_builder,
                        mib_scalar_instance=self.MibScalarInstance,
                        mib_table=self.MibTable,
                        mib_table_row=self.MibTableRow,
                        mib_table_column=self.MibTableColumn,
                    ),
                )
                self.mib_registrar = cast("Any", runtime_registrar)
            except RUNTIME_ADAPTER_EXCEPTIONS:
                self.logger.exception("Failed to create MibRegistrar")
                return
            registrar = self.mib_registrar

        if registrar is None:
            self.logger.error("mib_registrar is unexpectedly None after initialization")
            return

        registrar.register_all_mibs(cast("dict[str, dict[str, object]]", self.mib_jsons))

    def _populate_sysor_table(self) -> None:
        """Populate sysORTable with the MIBs being served by this agent.

        This is called after all MIBs are registered to dynamically generate
        sysORTable rows based on the actual MIBs that have been loaded.
        """
        # Use the MibRegistrar to populate sysORTable
        registrar = self.mib_registrar
        if registrar is None:
            self.logger.warning("Cannot populate sysORTable: mib_registrar is not initialized")
            return
        assert registrar is not None
        registrar.populate_sysor_table(self.mib_jsons)

    def _decode_value(self, value: DecodedValue) -> DecodedValue:
        """Compatibility wrapper: delegate decoding to MibRegistrar._decode_value.

        Historically this was a method on SNMPAgent; tests and some external
        callers expect it to exist. It simply delegates to a temporary
        MibRegistrar instance which implements the decoding logic.
        """
        try:
            decoded = decode_value_with_runtime_registrar(
                value,
                logger=self.logger,
                start_time=self.start_time,
            )
            if isinstance(decoded, (str, int, float, bool, list, dict, bytes, bytearray)):
                return cast("DecodedValue", decoded)
            if decoded is None:
                return None
            return value
        except RUNTIME_ADAPTER_EXCEPTIONS:
            # As a last resort, return the value unchanged
            return value

    def _get_mib_symbols_adapter(self) -> SupportsMibSymbolsAdapter:
        """Return symbols adapter bound to the current MIB builder."""
        if self.mib_builder is None:
            raise RuntimeError("MIB builder not initialized")
        if (
            self.mib_symbols_adapter is None
            or self._mib_symbols_adapter_builder is not self.mib_builder
        ):
            self.mib_symbols_adapter = PysnmpMibSymbolsAdapter(
                cast("SupportsBoundaryMibBuilder", self.mib_builder)
            )
            self._mib_symbols_adapter_builder = self.mib_builder
        return cast("SupportsMibSymbolsAdapter", self.mib_symbols_adapter)

    def _get_mib_scalar_instance_cls(self) -> type[object] | None:
        """Return SNMPv2-SMI ``MibScalarInstance`` class when available."""
        return self._get_mib_symbols_adapter().load_symbol_class(
            "SNMPv2-SMI",
            "MibScalarInstance",
        )

    def get_scalar_value(self, oid: tuple[int, ...]) -> DecodedValue:
        """Get the value of a scalar MIB object by OID.

        Args:
            oid: The OID of the scalar object (including instance index, e.g., (1,3,6,1,2,1,1,1,0))

        Returns:
            The current value of the scalar

        Raises:
            ValueError: If the OID is not found or is not a scalar

        """
        if self.mib_builder is None:
            raise RuntimeError("MIB builder not initialized")

        symbols_adapter = self._get_mib_symbols_adapter()
        mib_scalar_instance_cls = self._get_mib_scalar_instance_cls()
        if mib_scalar_instance_cls is None:
            raise RuntimeError("MibScalarInstance class unavailable")
        symbol_obj = symbols_adapter.find_scalar_instance_by_oid(
            oid,
            mib_scalar_instance_cls,
        )
        if symbol_obj is not None:
            return cast(DecodedValue, symbol_obj.syntax)

        raise ValueError(f"Scalar OID {oid} not found")

    def set_scalar_value(self, oid: tuple[int, ...], value: DecodedValue) -> None:
        """Set the value of a scalar MIB object by OID.

        Args:
            oid: The OID of the scalar object (including instance index, e.g., (1,3,6,1,2,1,1,1,0))
            value: The new value to set

        Raises:
            ValueError: If the OID is not found or is not a scalar

        """
        if self.mib_builder is None:
            raise RuntimeError("MIB builder not initialized")

        symbol_obj = self._find_scalar_symbol_or_raise(oid)
        self._try_update_scalar_symbol_value(oid, value, symbol_obj)

        dotted = ".".join(str(x) for x in oid)
        new_serial = self._serialize_value(symbol_obj.syntax)
        initial = self._initial_values.get(dotted)

        self._log_set_scalar_operation(dotted, initial, new_serial)
        self._persist_scalar_set_state(oid, dotted, new_serial, initial)

    def _find_scalar_symbol_or_raise(self, oid: tuple[int, ...]) -> MutableScalarInstance:
        symbols_adapter = self._get_mib_symbols_adapter()
        mib_scalar_instance_cls = self._get_mib_scalar_instance_cls()
        if mib_scalar_instance_cls is None:
            raise RuntimeError("MibScalarInstance class unavailable")

        symbol_obj = symbols_adapter.find_scalar_instance_by_oid(
            oid,
            mib_scalar_instance_cls,
        )
        if symbol_obj is None:
            raise ValueError(f"Scalar OID {oid} not found")
        return symbol_obj

    def _try_update_scalar_symbol_value(
        self,
        oid: tuple[int, ...],
        value: DecodedValue,
        symbol_obj: MutableScalarInstance,
    ) -> None:
        try:
            new_syntax = cast("SupportsClone", symbol_obj.syntax).clone(value)
            symbol_obj.syntax = new_syntax
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.error(
                "%s", f"Failed to update scalar {oid} with value {value!r} "
                f"(type: {type(value).__name__}): {e}"
            )

    def _log_set_scalar_operation(
        self,
        dotted: str,
        initial: JsonValue | None,
        new_serial: JsonValue,
    ) -> None:
        try:
            mod, sym = self._lookup_symbol_for_dotted(dotted)
            name = f"{mod}:{sym}" if mod and sym else dotted
            self.logger.info(
                "SNMP SET received for %s (%s): initial=%r new=%r",
                dotted,
                name,
                initial,
                new_serial,
            )
            self.logger.debug(
                "(debug) SNMP SET for %s (%s): initial=%r new=%r",
                dotted,
                name,
                initial,
                new_serial,
            )
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

    @staticmethod
    def _parse_instance_parts(instance_str: str) -> list[str]:
        return [part for part in instance_str.split(".") if part]

    @staticmethod
    def _index_part_to_json_value(idx_part: str) -> JsonValue:
        return int(idx_part) if idx_part.isdigit() else idx_part

    def _populate_missing_row_index_values(
        self,
        row_values: dict[str, JsonValue],
        instance_str: str,
        index_columns: list[str],
    ) -> None:
        parts = self._parse_instance_parts(instance_str)
        if not parts or len(index_columns) != len(parts):
            return

        for idx_name, idx_part in zip(index_columns, parts, strict=True):
            if idx_name in row_values:
                continue
            row_values[idx_name] = self._index_part_to_json_value(idx_part)

    @staticmethod
    def _rowstatus_action(value: JsonValue) -> str | None:
        """Interpret a RowStatus value as a lifecycle action."""
        if isinstance(value, int):
            numeric = value
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered.isdigit():
                numeric = int(lowered)
            else:
                if "createandgo" in lowered:
                    return "create-and-go"
                if "createandwait" in lowered:
                    return "create-and-wait"
                if lowered == "active":
                    return "active"
                if lowered == "destroy":
                    return "destroy"
                return None
        else:
            return None

        if numeric == 4:
            return "create-and-go"
        if numeric == 5:
            return "create-and-wait"
        if numeric == 1:
            return "active"
        if numeric == 6:
            return "destroy"
        return None

    @staticmethod
    def _canonical_rowstatus_value(action: str, original: JsonValue) -> JsonValue:
        """Convert transient RowStatus verbs into persisted row states."""
        if action == "create-and-go":
            return 1
        if action == "create-and-wait":
            return 2
        return original

    @staticmethod
    def _instance_index_values(
        instance_str: str,
        index_columns: list[str],
    ) -> dict[str, JsonValue]:
        parts = [part for part in instance_str.split(".") if part]
        if not parts:
            return {"__index__": "1"}

        if index_columns and len(index_columns) == len(parts):
            return {
                name: (int(part) if part.isdigit() else part)
                for name, part in zip(index_columns, parts, strict=True)
            }

        values: dict[str, JsonValue] = {}
        for idx, part in enumerate(parts, start=1):
            key = "__index__" if idx == 1 else f"__index_{idx}__"
            values[key] = int(part) if part.isdigit() else part
        return values

    def _table_default_row_for_oid(self, table_oid: str) -> dict[str, JsonValue]:
        if table_oid in self._table_defaults:
            return dict(self._table_defaults[table_oid])

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)
            table_obj, _table_oid_list = self._find_table_object_for_oid(objects, table_oid)
            if table_obj is None:
                continue

            default_row = dict(self._extract_default_row_dict(table_obj))
            if default_row:
                self._table_defaults[table_oid] = dict(default_row)
                return default_row

            # RowStatus tables now start with rows=[] by design. Build a
            # fallback default map from column metadata (e.g. enum first value).
            table_oid_list = self._oid_list_parts(table_obj.get("oid"))
            if not table_oid_list:
                return {}

            fallback_row = self._build_default_row_from_schema_columns(objects, table_oid_list)
            if fallback_row:
                self._table_defaults[table_oid] = dict(fallback_row)
            return fallback_row
        return {}

    def _column_default_from_schema(
        self,
        column_obj: dict[str, JsonValue],
    ) -> JsonValue | None:
        initial = column_obj.get("initial")
        if initial is not None and not (
            isinstance(initial, str) and initial.strip().lower() == "unset"
        ):
            return initial

        enums = column_obj.get("enums")
        if isinstance(enums, dict):
            enum_values = [value for value in enums.values() if isinstance(value, int)]
            if enum_values:
                return min(enum_values)

        return None

    def _build_default_row_from_schema_columns(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid_list: list[int | str],
    ) -> dict[str, JsonValue]:
        entry_obj = self._find_table_entry_object(objects, table_oid_list)
        if entry_obj is None:
            return {}

        entry_oid = self._oid_tuple(entry_obj.get("oid"))
        if entry_oid is None:
            return {}

        index_columns = set(self._string_list(entry_obj.get("indexes")))
        defaults: dict[str, JsonValue] = {}

        for column_name, column_obj in objects.items():
            if column_name in index_columns:
                continue

            col_oid = self._oid_tuple(column_obj.get("oid"))
            if col_oid is None or len(col_oid) != len(entry_oid) + 1:
                continue
            if col_oid[:-1] != entry_oid:
                continue

            default_value = self._column_default_from_schema(column_obj)
            if default_value is None:
                continue
            defaults[column_name] = default_value

        return defaults

    def _is_rowstatus_column(self, table_oid: str, column_name: str) -> bool:
        table_oid_parts = tuple(int(part) for part in table_oid.split("."))

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)
            column_obj = objects.get(column_name)
            if not isinstance(column_obj, dict):
                continue

            col_oid = self._oid_tuple(column_obj.get("oid"))
            if col_oid is None or len(col_oid) <= len(table_oid_parts) + 1:
                continue
            if col_oid[: len(table_oid_parts)] != table_oid_parts:
                continue
            if col_oid[len(table_oid_parts)] != 1:
                continue

            col_type = column_obj.get("type")
            return isinstance(col_type, str) and col_type.lower() == "rowstatus"

        return False

    def _resolve_table_cell_context_from_schema(
        self,
        oid: tuple[int, ...],
    ) -> tuple[str, str, str, list[str]] | None:
        """Resolve table/cell context directly from loaded schema objects."""
        if not self.mib_jsons:
            return None

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            for candidate_name, candidate in objects.items():
                if candidate.get("type") in {"MibTable", "MibTableRow"}:
                    continue

                col_oid = self._oid_tuple(candidate.get("oid"))
                if col_oid is None or len(oid) <= len(col_oid):
                    continue
                if oid[: len(col_oid)] != col_oid:
                    continue

                entry_oid = col_oid[:-1]
                table_oid = col_oid[:-2]
                if not table_oid:
                    continue

                table_obj = None
                entry_obj = None
                for obj in objects.values():
                    parsed_oid = self._oid_tuple(obj.get("oid"))
                    if obj.get("type") == "MibTable" and parsed_oid == table_oid:
                        table_obj = obj
                    if obj.get("type") == "MibTableRow" and parsed_oid == entry_oid:
                        entry_obj = obj

                if table_obj is None or entry_obj is None:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))
                instance_parts = oid[len(col_oid) :]
                instance_str = ".".join(str(part) for part in instance_parts) if instance_parts else "1"

                return (
                    ".".join(str(part) for part in table_oid),
                    instance_str,
                    candidate_name,
                    index_columns,
                )

        return None

    def _handle_rowstatus_lifecycle_set(
        self,
        *,
        table_oid: str,
        instance_str: str,
        index_columns: list[str],
        column_name: str,
        action: str,
        persisted_status: JsonValue,
    ) -> bool:
        index_values = self._instance_index_values(instance_str, index_columns)

        if action == "destroy":
            deleted = self.delete_table_instance(table_oid, index_values)
            self._remove_runtime_table_cell_instances(table_oid, instance_str)
            return deleted

        if instance_str in self.table_instances.get(table_oid, {}):
            return False

        default_row = self._table_default_row_for_oid(table_oid)
        column_values = {
            key: value
            for key, value in default_row.items()
            if key not in index_columns
        }
        column_values[column_name] = persisted_status
        self.add_table_instance(table_oid, index_values, column_values)
        return True

    def _remove_runtime_table_cell_instances(self, table_oid: str, instance_str: str) -> int:
        """Remove MibTableColumn._vars entries for a table row instance.

        pysnmp stores dynamically-created row instances inside each
        ``MibTableColumn._vars`` dict (keyed by the full cell OID).  A
        RowStatus destroy(6) SET only removes the RowStatus column entry;
        this method cascades the cleanup to all other columns so they don't
        ghost after the row is gone.
        """
        if self.mib_builder is None:
            return 0

        try:
            table_oid_tuple = tuple(int(part) for part in table_oid.split("."))
            instance_parts = tuple(int(part) for part in instance_str.split(".") if part)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return 0

        if not instance_parts:
            return 0

        entry_oid_prefix = table_oid_tuple + (1,)

        try:
            (mib_table_column_cls,) = self.mib_builder.import_symbols(
                "SNMPv2-SMI", "MibTableColumn"
            )
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return 0

        symbols = cast("dict[str, dict[str, object]]", getattr(self.mib_builder, "mibSymbols", {}))
        removed = 0

        for module_symbols in symbols.values():
            for symbol_obj in module_symbols.values():
                if not isinstance(symbol_obj, mib_table_column_cls):
                    continue

                raw_col_name = getattr(symbol_obj, "name", None)
                if raw_col_name is None:
                    continue
                try:
                    col_oid_tuple = tuple(int(x) for x in raw_col_name)
                except (TypeError, ValueError):
                    continue

                # Only columns that belong to this table's entry row
                if (
                    len(col_oid_tuple) <= len(entry_oid_prefix)
                    or col_oid_tuple[: len(entry_oid_prefix)] != entry_oid_prefix
                ):
                    continue

                # The cell key is: col_oid + instance_parts
                cell_oid = col_oid_tuple + instance_parts

                vars_dict = getattr(symbol_obj, "_vars", None)
                if not vars_dict:
                    continue

                keys_to_remove = []
                for k in list(vars_dict.keys()):
                    try:
                        if tuple(int(x) for x in k) == cell_oid:
                            keys_to_remove.append(k)
                    except (TypeError, ValueError):
                        continue

                for key in keys_to_remove:
                    del vars_dict[key]
                    removed += 1

                if keys_to_remove:
                    try:
                        dynamic_symbol = cast("Any", symbol_obj)
                        dynamic_symbol.branchVersionId += 1
                    except (AttributeError, TypeError):
                        pass

        if removed:
            self.logger.info(
                "Removed %s runtime table cell instance(s) for %s.%s",
                removed,
                table_oid,
                instance_str,
            )

        return removed

    def _set_existing_runtime_table_cell_value(
        self,
        *,
        table_oid: str,
        column_name: str,
        instance_str: str,
        value: JsonValue,
    ) -> bool:
        """Set value on an existing runtime table cell without creating symbols."""
        if self.mib_builder is None:
            return False

        try:
            table_oid_tuple = tuple(int(part) for part in table_oid.split("."))
            instance_parts = tuple(int(part) for part in instance_str.split(".") if part)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return False

        if not instance_parts:
            return False

        entry_oid = table_oid_tuple + (1,)
        adapter = self._get_mib_symbols_adapter()
        column_oid = adapter.find_column_oid_for_entry(column_name, entry_oid)
        if not column_oid:
            return False

        cell_oid = column_oid + instance_parts

        try:
            (mib_table_column_cls,) = self.mib_builder.import_symbols(
                "SNMPv2-SMI", "MibTableColumn"
            )
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return False

        symbols = cast("dict[str, dict[str, object]]", getattr(self.mib_builder, "mibSymbols", {}))
        for module_symbols in symbols.values():
            for symbol_obj in module_symbols.values():
                if not isinstance(symbol_obj, mib_table_column_cls):
                    continue
                raw_col_name = getattr(symbol_obj, "name", None)
                if raw_col_name is None:
                    continue
                try:
                    col_oid_tuple = tuple(int(x) for x in raw_col_name)
                except (TypeError, ValueError):
                    continue
                if col_oid_tuple != column_oid:
                    continue

                vars_dict = getattr(symbol_obj, "_vars", None)
                if not vars_dict:
                    return False

                inst = None
                for key, value_obj in vars_dict.items():
                    try:
                        if tuple(int(x) for x in key) == cell_oid:
                            inst = value_obj
                            break
                    except (TypeError, ValueError):
                        continue
                if inst is None:
                    return False

                syntax_obj = getattr(inst, "syntax", None)
                if syntax_obj is None:
                    return False

                try:
                    inst.syntax = cast("SupportsClone", syntax_obj).clone(value)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    return False
                return True

        return False

    def _materialize_rowstatus_defaults_after_set(
        self,
        var_binds: tuple[object, ...],
    ) -> None:
        """Handle RowStatus lifecycle after live SNMP SET requests.

        This catches index-only createAndGo/createAndWait operations that come
        through pysnmp instrumentation and materializes schema-default column
        values for the new row.
        """
        row_updates: dict[tuple[str, str], dict[str, object]] = {}

        for var_bind in var_binds:
            try:
                raw_value = var_bind[1]  # type: ignore[index]
            except (AttributeError, LookupError, OSError, TypeError, ValueError, IndexError):
                continue

            oid_text = self._format_request_oid(var_bind)
            try:
                oid = tuple(int(part) for part in oid_text.split("."))
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                continue

            table_cell = self._resolve_table_cell_context_from_schema(oid)
            if table_cell is None:
                continue

            table_oid, instance_str, column_name, index_columns = table_cell
            key = (table_oid, instance_str)
            row_ctx = row_updates.setdefault(
                key,
                {
                    "index_columns": index_columns,
                    "columns": set(),
                    "rowstatus_column": None,
                    "rowstatus_action": None,
                    "rowstatus_value": None,
                },
            )

            columns = cast("set[str]", row_ctx["columns"])
            columns.add(column_name)

            if not self._is_rowstatus_column(table_oid, column_name):
                # Collect actual SET value so multi-column creates can be tracked.
                set_col_vals = cast(
                    "dict[str, JsonValue]",
                    row_ctx.setdefault("set_column_values", {}),
                )
                try:
                    set_col_vals[column_name] = int(raw_value)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                        set_col_vals[column_name] = str(raw_value)
                continue

            action: str | None = None
            numeric_value: int | None = None
            if isinstance(raw_value, int):
                numeric_value = raw_value
                action = self._rowstatus_action(raw_value)
                rowstatus_value: JsonValue = raw_value
            else:
                try:
                    numeric_value = int(raw_value)
                    action = self._rowstatus_action(numeric_value)
                    rowstatus_value = numeric_value
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    rowstatus_value = str(raw_value)
                    action = self._rowstatus_action(rowstatus_value)

            if action is None:
                # Some failed RowStatus destroy requests can leave a transient
                # runtime cell at notExists(0). Mark it for orphan cleanup.
                if numeric_value == 0:
                    row_ctx["rowstatus_column"] = column_name
                    row_ctx["rowstatus_value"] = 0
                continue

            row_ctx["rowstatus_column"] = column_name
            row_ctx["rowstatus_action"] = action
            row_ctx["rowstatus_value"] = self._canonical_rowstatus_value(action, rowstatus_value)

        for (table_oid, instance_str), row_ctx in row_updates.items():
            action = cast("str | None", row_ctx.get("rowstatus_action"))
            rowstatus_column = row_ctx.get("rowstatus_column")
            rowstatus_value = cast("JsonValue", row_ctx.get("rowstatus_value"))
            if not isinstance(action, str):
                if (
                    isinstance(rowstatus_column, str)
                    and rowstatus_value == 0
                    and instance_str not in self.table_instances.get(table_oid, {})
                ):
                    self._remove_runtime_table_cell_instances(table_oid, instance_str)
                continue

            index_columns = cast("list[str]", row_ctx["index_columns"])
            index_values = self._instance_index_values(instance_str, index_columns)

            if action == "destroy":
                self.delete_table_instance(table_oid, index_values)
                self._remove_runtime_table_cell_instances(table_oid, instance_str)
                continue

            columns = cast("set[str]", row_ctx["columns"])

            # Only synthesize default columns for index-only RowStatus creation.
            if not (
                isinstance(rowstatus_column, str)
                and action in {"create-and-go", "create-and-wait", "active"}
            ):
                continue

            if instance_str in self.table_instances.get(table_oid, {}):
                self._set_existing_runtime_table_cell_value(
                    table_oid=table_oid,
                    column_name=rowstatus_column,
                    instance_str=instance_str,
                    value=rowstatus_value,
                )
                existing_row = self.table_instances[table_oid].setdefault(
                    instance_str,
                    {"column_values": {}},
                )
                row_values = existing_row.setdefault("column_values", {})
                row_values[rowstatus_column] = rowstatus_value
                self._save_state_safely()
                continue

            if columns == {rowstatus_column}:
                # Index-only create: synthesise schema default columns.
                default_row = self._table_default_row_for_oid(table_oid)
                column_values = {
                    key: value
                    for key, value in default_row.items()
                    if key not in index_columns
                }
                column_values[rowstatus_column] = rowstatus_value
                # Keep runtime symbols as materialized by pysnmp write_variables
                # and persist only row metadata. Mutating symbol maps here via
                # add_table_instance can destabilize __index_mib re-indexing.
                self._set_existing_runtime_table_cell_value(
                    table_oid=table_oid,
                    column_name=rowstatus_column,
                    instance_str=instance_str,
                    value=rowstatus_value,
                )
                instance_oid = f"{table_oid}.{instance_str}"
                self.table_instances.setdefault(table_oid, {})[instance_str] = {
                    "column_values": dict(column_values),
                }
                if instance_oid in self.deleted_instances:
                    self.deleted_instances.remove(instance_oid)
                default_runtime_values = {
                    key: value
                    for key, value in column_values.items()
                    if key != rowstatus_column
                }
                if default_runtime_values:
                    self.update_table_cell_values(
                        table_oid,
                        instance_str,
                        default_runtime_values,
                    )
                self._save_state_safely()
                self.logger.info(
                    "RowStatus create: registered row %s.%s in table_instances",
                    table_oid,
                    instance_str,
                )
                continue
            # Multi-column create: record exactly what manager set.
            column_values = dict(
                cast(
                    "dict[str, JsonValue]",
                    row_ctx.get("set_column_values", {}),
                )
            )

            # pysnmp write_variables has already materialised runtime instances
            # for createAndGo; only persist row metadata here to avoid duplicate
            # subtree registration in later __index_mib() passes.
            column_values[rowstatus_column] = rowstatus_value
            self._set_existing_runtime_table_cell_value(
                table_oid=table_oid,
                column_name=rowstatus_column,
                instance_str=instance_str,
                value=rowstatus_value,
            )
            instance_oid = f"{table_oid}.{instance_str}"
            self.table_instances.setdefault(table_oid, {})[instance_str] = {
                "column_values": dict(column_values),
            }
            if instance_oid in self.deleted_instances:
                self.deleted_instances.remove(instance_oid)
            self._save_state_safely()
            self.logger.info(
                "RowStatus create: registered row %s.%s in table_instances",
                table_oid,
                instance_str,
            )

    def _persist_table_cell_set(
        self,
        table_cell: tuple[str, str, str, list[str]],
        dotted: str,
        new_serial: JsonValue,
    ) -> None:
        table_oid, instance_str, column_name, index_columns = table_cell
        persisted_value = new_serial

        if self._is_rowstatus_column(table_oid, column_name):
            action = self._rowstatus_action(new_serial)
            if action is not None:
                persisted_value = self._canonical_rowstatus_value(action, new_serial)
                if self._handle_rowstatus_lifecycle_set(
                    table_oid=table_oid,
                    instance_str=instance_str,
                    index_columns=index_columns,
                    column_name=column_name,
                    action=action,
                    persisted_status=persisted_value,
                ):
                    self.overrides.pop(dotted, None)
                    return

        table_data = self.table_instances.setdefault(table_oid, {})
        row_data = table_data.setdefault(instance_str, {"column_values": {}})
        row_values = row_data.setdefault("column_values", {})
        row_values[column_name] = persisted_value
        self._populate_missing_row_index_values(row_values, instance_str, index_columns)
        self.overrides.pop(dotted, None)

    def _save_state_safely(self) -> None:
        try:
            self.save_mib_state()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Failed to save MIB state")

    def _persist_scalar_set_state(
        self,
        oid: tuple[int, ...],
        dotted: str,
        new_serial: JsonValue,
        initial: JsonValue | None,
    ) -> None:
        if initial is None or new_serial != initial:
            table_cell = self._resolve_table_cell_context(oid)
            if table_cell is not None:
                self._persist_table_cell_set(table_cell, dotted, new_serial)
            else:
                self.overrides[dotted] = new_serial
            self._save_state_safely()
            return

        if dotted in self.overrides:
            self.overrides.pop(dotted, None)
            self._save_state_safely()

    def get_all_oids(self) -> dict[str, tuple[int, ...]]:
        """Get all registered OIDs with their names.

        Returns:
            Dict mapping OID names to OID tuples

        """
        if self.mib_builder is None:
            raise RuntimeError("MIB builder not initialized")

        return self._get_mib_symbols_adapter().get_all_named_oids()

    def _lookup_symbol_for_dotted(self, dotted: str) -> tuple[str | None, str | None]:
        """Return (module_name, symbol_name) for a dotted OID string if known.

        This helps produce human-friendly log messages (e.g. SNMPv2-MIB:sysContact).
        """
        if self.mib_builder is None:
            return None, None
        try:
            target_oid = tuple(int(x) for x in dotted.split("."))
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            return None, None

        return self._get_mib_symbols_adapter().lookup_symbol_for_oid(target_oid)

    # ---- Overrides persistence helpers ----

    def _schema_objects(
        self,
        schema: dict[str, JsonValue],
    ) -> dict[str, dict[str, JsonValue]]:
        """Return schema object map as dict[str, dict[str, JsonValue]]."""
        raw_objects = schema.get("objects", schema)
        if not isinstance(raw_objects, dict):
            return {}
        objects: dict[str, dict[str, JsonValue]] = {}
        for name, obj in raw_objects.items():
            if isinstance(name, str) and isinstance(obj, dict):
                objects[name] = obj
        return objects

    def _oid_list_parts(self, value: JsonValue | None) -> list[int | str]:
        """Coerce a JSON value into a list of OID parts (ints/strings)."""
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, (int, str))]

    def _oid_tuple(self, value: JsonValue | None) -> tuple[int, ...] | None:
        """Coerce a JSON value into a strict tuple[int, ...] OID."""
        parts = self._oid_list_parts(value)
        if not parts:
            return None
        normalized: list[int] = []
        for part in parts:
            if isinstance(part, int):
                normalized.append(part)
                continue
            if isinstance(part, str) and part.isdigit():
                normalized.append(int(part))
                continue
            return None
        return tuple(normalized)

    def _string_list(self, value: JsonValue | None) -> list[str]:
        """Coerce a JSON value into list[str] preserving only strings."""
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def _normalize_loaded_table_instances(self) -> None:
        """Normalize loaded table OIDs to canonical string form."""
        normalized: dict[str, dict[str, TableInstance]] = {}
        for table_oid, instances in self.table_instances.items():
            normalized_oid = self._normalize_oid_str(table_oid)
            if not normalized_oid:
                continue
            normalized[normalized_oid] = instances
        self.table_instances = normalized

    def _fill_missing_table_defaults(self) -> None:
        """Fill missing or "unset" values in table instances using schema defaults."""
        if not self.mib_jsons or not self.table_instances:
            return

        updated = False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            for obj_data in objects.values():
                if obj_data.get("type") != "MibTable":
                    continue

                table_oid_list = self._oid_list_parts(obj_data.get("oid"))
                if not table_oid_list:
                    continue

                table_oid = ".".join(str(x) for x in table_oid_list)
                if table_oid not in self.table_instances:
                    continue

                entry_oid_list = [*table_oid_list, 1]
                entry_obj = self._find_table_entry_object(objects, tuple(entry_oid_list))
                if not entry_obj:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))

                default_row = self._extract_default_row_dict(obj_data)
                if not default_row:
                    continue

                if self._apply_default_row_to_instances(table_oid, index_columns, default_row):
                    updated = True

        if updated:
            self.save_mib_state()

    def _materialize_index_columns(self) -> None:
        """Ensure index columns are materialized in all table instances.

        For each table instance row, extracts index values from the instance key
        and stores them as column values, so they're available in SNMP walks.
        """
        if not self.mib_jsons or not self.table_instances:
            return

        updated = False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            for obj_data in objects.values():
                if obj_data.get("type") != "MibTable":
                    continue

                table_oid_list = self._oid_list_parts(obj_data.get("oid"))
                if not table_oid_list:
                    continue

                table_oid = ".".join(str(x) for x in table_oid_list)
                if table_oid not in self.table_instances:
                    continue

                entry_oid_list = [*table_oid_list, 1]
                entry_obj = self._find_table_entry_object(objects, entry_oid_list)
                if not entry_obj:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))
                if not index_columns:
                    continue

                if self._materialize_table_index_columns(table_oid, index_columns):
                    updated = True

        if updated:
            self.save_mib_state()

    def _migrate_legacy_state_files(self) -> None:
        """Migrate legacy overrides.json and table_instances.json to unified format."""
        legacy_overrides = Path(__file__).resolve().parent.parent / "data" / "overrides.json"
        legacy_tables = Path(__file__).resolve().parent.parent / "data" / "table_instances.json"

        mib_state: dict[str, JsonValue] = {
            "scalars": {},
            "tables": {},
            "deleted_instances": [],
        }

        if legacy_overrides.exists():
            try:
                with legacy_overrides.open(encoding="utf-8") as f:
                    mib_state["scalars"] = json.load(f)
                self.logger.info("Migrated scalars from %s", legacy_overrides)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.warning("Failed to migrate %s: %s", legacy_overrides, e)

        if legacy_tables.exists():
            try:
                with legacy_tables.open(encoding="utf-8") as f:
                    mib_state["tables"] = json.load(f)
                self.logger.info("Migrated tables from %s", legacy_tables)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.warning("Failed to migrate %s: %s", legacy_tables, e)

        # Save unified file
        if mib_state["scalars"] or mib_state["tables"]:
            self.save_mib_state()

    def save_mib_state(self) -> None:
        """Save unified MIB state to disk."""
        path = Path(self._state_file_path())
        path.parent.mkdir(parents=True, exist_ok=True)

        link_manager = get_link_manager()
        mib_state = {
            "scalars": self.overrides,
            "tables": self.table_instances,
            "deleted_instances": self.deleted_instances,
            "links": link_manager.export_state_links(),
        }

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(mib_state, f, indent=2, sort_keys=True)
            self.logger.debug("Saved MIB state to %s", path)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.exception("Failed to save MIB state to %s: %s", path, e)

    def _serialize_value(self, value: object) -> JsonValue:
        # Convert pysnmp types and other non-JSON-friendly values into JSON-serializable forms
        try:
            # Primitive types pass-through
            if value is None:
                return None
            if isinstance(value, (int, float, bool, str)):
                return value
            # Bytes -> latin1 string to preserve raw bytes
            if isinstance(value, (bytes, bytearray)):
                try:
                    return value.decode("latin1")
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    return value.hex()
            # pysnmp rfc1902 types often stringify sensibly
            try:
                s = str(value)
                return s
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                return repr(value)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return str(value)

    def _capture_initial_values(self) -> None:
        """Capture the initial scalar values after MIB registration for comparison."""
        self._initial_values = {}
        if self.mib_builder is None:
            return
        symbols_adapter = self._get_mib_symbols_adapter()
        mib_scalar_instance_cls = self._get_mib_scalar_instance_cls()
        if mib_scalar_instance_cls is None:
            return

        for module_name, symbol_name, symbol_obj in symbols_adapter.iter_scalar_instances(
            mib_scalar_instance_cls
        ):
            try:
                dotted = ".".join(str(x) for x in symbol_obj.name)
                self._initial_values[dotted] = self._serialize_value(symbol_obj.syntax)
                # detect writable scalars by consulting loaded mib_jsons when possible
                try:
                    added = False
                    # Prefer schema-based access info if available. The registrar
                    # exports scalar symbols with an "Inst" suffix (e.g. sysContactInst),
                    # whereas the schema keys are the base names (e.g. sysContact).
                    module_json = self.mib_jsons.get(module_name, {})
                    base_name = symbol_name
                    base_name = base_name.removesuffix("Inst")
                    if isinstance(module_json, dict):
                        symbol_meta = module_json.get(base_name)
                        if isinstance(symbol_meta, dict):
                            access_field = symbol_meta.get("access")
                        else:
                            access_field = None
                        if (
                            isinstance(access_field, str)
                            and access_field.lower() == "read-write"
                        ):
                            self._writable_oids.add(dotted)
                            added = True
                            self.logger.debug(
                                "Marked writable via schema: %s -> %s.%s",
                                dotted,
                                module_name,
                                base_name,
                            )
                    if not added:
                        access = symbols_adapter.get_symbol_access(symbol_obj)
                        if access and access.lower().startswith("readwrite"):
                            self._writable_oids.add(dotted)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    pass
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                continue

        self.logger.info("%s", f"Captured {len(self._initial_values)} initial scalar values")

    def _apply_overrides(self) -> None:
        """Apply loaded overrides to the in-memory MIB scalar instances."""
        if not self.overrides:
            return
        if self.mib_builder is None:
            return
        symbols_adapter = self._get_mib_symbols_adapter()
        mib_scalar_instance_cls = self._get_mib_scalar_instance_cls()
        if mib_scalar_instance_cls is None:
            return

        removed_invalid: list[str] = []

        for dotted, stored in list(self.overrides.items()):
            oid = self._parse_override_oid(dotted)
            if oid is None:
                removed_invalid.append(dotted)
                continue

            if self._try_apply_single_override(
                dotted,
                stored,
                oid,
                symbols_adapter,
                mib_scalar_instance_cls,
            ):
                continue

            self.logger.warning(
                "Override for %s found, but no matching scalar instance to apply",
                dotted,
            )
            removed_invalid.append(dotted)

        self._prune_invalid_overrides(removed_invalid)

    def _parse_override_oid(self, dotted: str) -> tuple[int, ...] | None:
        try:
            return tuple(int(x) for x in dotted.split("."))
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.warning("Invalid OID in overrides: %s", dotted)
            return None

    def _candidate_override_oids(self, oid: tuple[int, ...]) -> list[tuple[int, ...]]:
        candidate_oids = [oid]
        try:
            if oid[-1] != 0:
                candidate_oids.append(oid + (0,))
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass
        return candidate_oids

    def _try_apply_single_override(
        self,
        dotted: str,
        stored: DecodedValue,
        oid: tuple[int, ...],
        symbols_adapter: SupportsMibSymbolsAdapter,
        mib_scalar_instance_cls: type,
    ) -> bool:
        symbol_obj = symbols_adapter.find_scalar_instance_by_candidate_oids(
            self._candidate_override_oids(oid),
            mib_scalar_instance_cls,
        )
        if symbol_obj is None:
            return False

        try:
            new_syntax = cast("SupportsClone", symbol_obj.syntax).clone(stored)
            symbol_obj.syntax = new_syntax
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.warning(
                "%s", f"Failed to apply override for {dotted} with value {stored!r}: {e}"
            )
            return False
        return True

    def _prune_invalid_overrides(self, removed_invalid: list[str]) -> None:
        if not removed_invalid:
            return
        for key in removed_invalid:
            self.overrides.pop(key, None)
        try:
            self.save_mib_state()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Failed to save MIB state after pruning invalid entries")
        self.logger.info(
            "Removed %d invalid overrides: %s",
            len(removed_invalid),
            removed_invalid,
        )

    def _apply_table_instances(self) -> None:
        """Apply loaded table instances to the in-memory MIB table cell instances."""
        if not self.table_instances:
            return

        self.logger.info("Applying table instances to MIB...")

        # For each table
        for table_oid, instances in self.table_instances.items():
            # For each instance in that table
            for instance_str, instance_data in instances.items():
                column_values = instance_data.get("column_values", {})
                if column_values:
                    self.update_table_cell_values(table_oid, instance_str, column_values)
                    self.logger.debug("Applied table instance %s.%s", table_oid, instance_str)


if __name__ == "__main__":  # pragma: no cover
    try:
        agent = SNMPAgent()
        agent.run()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
