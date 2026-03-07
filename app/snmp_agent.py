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
        def clone(self, value: object) -> object: ...

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

    def _persist_table_cell_set(
        self,
        table_cell: tuple[str, str, str, list[str]],
        dotted: str,
        new_serial: JsonValue,
    ) -> None:
        table_oid, instance_str, column_name, index_columns = table_cell
        table_data = self.table_instances.setdefault(table_oid, {})
        row_data = table_data.setdefault(instance_str, {"column_values": {}})
        row_values = row_data.setdefault("column_values", {})
        row_values[column_name] = new_serial
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
