"""Table Registrar: Handles registration of SNMP tables in the MIB.

Separates table registration logic from SNMPAgent, improving testability
and making table registration behavior clearer and more maintainable.
"""

# pylint: disable=invalid-name,too-many-arguments

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from pysnmp.proto import rfc1902
from pysnmp_type_wrapper.interfaces import (
    SnmpTypeFactory,
    SupportsMibBuilder,
    SupportsSnmpTypeResolver,
)
from pysnmp_type_wrapper.pysnmp_type_resolver import PysnmpTypeResolver

from app.base_type_handler import BaseTypeHandler
from app.interface_types import (
    ColumnMeta,
    InterfaceObject,
    MibJsonMap,
    MibJsonObject,
    TableData,
)
from app.types import TypeInfo, TypeRegistry

if TYPE_CHECKING:
    from app.interface_types import EntryMeta, TableMeta


class TableRegistrar:
    """Manages the discovery and registration of SNMP tables from MIB JSON data."""

    def __init__(
        self,
        mib_builder: SupportsMibBuilder | None,
        mib_scalar_instance: Callable[[], InterfaceObject] | None,
        mib_table: Callable[[tuple[int, ...]], InterfaceObject] | None,
        mib_table_row: Callable[[tuple[int, ...]], InterfaceObject] | None,
        mib_table_column: Callable[[tuple[int, ...], InterfaceObject], InterfaceObject] | None,
        logger: logging.Logger,
        type_registry: TypeRegistry | None = None,
        snmp_type_resolver: SupportsSnmpTypeResolver | None = None,
    ) -> None:
        """Initialize the TableRegistrar.

        Args:
            mib_builder: PySNMP MIB builder instance
            mib_scalar_instance: PySNMP MibScalarInstance class
            mib_table: PySNMP MibTable class
            mib_table_row: PySNMP MibTableRow class
            mib_table_column: PySNMP MibTableColumn class
            logger: Logger instance for debug/error messages
            type_registry: Type registry dict mapping type names to type info
            snmp_type_resolver: Adapter for dynamic PySNMP type resolution

        """
        if type_registry is None:
            type_registry = {}
        self.mib_builder = mib_builder
        self.mib_scalar_instance = mib_scalar_instance
        self.mib_table = mib_table
        self.mib_table_row = mib_table_row
        self.mib_table_column = mib_table_column
        self.logger = logger
        self.snmp_type_resolver = snmp_type_resolver or PysnmpTypeResolver()
        self.type_handler = BaseTypeHandler(type_registry=type_registry, logger=logger)

    def find_table_related_objects(self, mib_json: MibJsonObject) -> set[str]:
        """Return set of table-related object names (tables, entries, columns).

        Identifies all objects in the MIB JSON that are part of table structures,
        allowing scalars to be registered separately.

        Args:
            mib_json: MIB dictionary with object definitions

        Returns:
            Set of object names that are table-related (tables, entries, columns)

        """
        table_related_objects: set[str] = set()
        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue
            if name.endswith(("Table", "Entry")):
                table_related_objects.add(name)
                if name.endswith("Entry"):
                    entry_oid = self._oid_tuple(info.get("oid"))
                    if entry_oid is None:
                        continue
                    # Find all columns that are children of this entry
                    for col_name, col_info in mib_json.items():
                        if not isinstance(col_info, dict):
                            continue
                        col_oid = self._oid_tuple(col_info.get("oid"))
                        if col_oid is None:
                            continue
                        if (
                            len(col_oid) == len(entry_oid) + 1
                            and col_oid[: len(entry_oid)] == entry_oid
                        ):
                            table_related_objects.add(col_name)
        return table_related_objects

    @staticmethod
    def _is_table_candidate(info: object) -> bool:
        if not isinstance(info, dict):
            return False
        return info.get("type") == "MibTable" and info.get("access") == "not-accessible"

    def _find_table_entry(
        self,
        mib_json: MibJsonObject,
        table_oid: tuple[int, ...],
    ) -> tuple[str, tuple[int, ...], "EntryMeta"] | None:
        expected_entry_oid = [*table_oid, 1]
        for other_name, other_data in mib_json.items():
            if not isinstance(other_data, dict):
                continue
            if other_data.get("type") != "MibTableRow":
                continue
            if list(other_data.get("oid", [])) != expected_entry_oid:
                continue
            entry_oid = self._oid_tuple(other_data.get("oid"))
            if entry_oid is None:
                return None
            return other_name, entry_oid, cast("EntryMeta", other_data)
        return None

    def _collect_table_columns(
        self,
        mib_json: MibJsonObject,
        table_name: str,
        entry_name: str,
        entry_oid: tuple[int, ...],
    ) -> dict[str, ColumnMeta]:
        columns: dict[str, ColumnMeta] = {}
        for col_name, col_info in mib_json.items():
            if col_name in {table_name, entry_name}:
                continue
            if not isinstance(col_info, dict):
                continue
            col_oid = self._oid_tuple(col_info.get("oid"))
            if col_oid is None:
                continue
            is_child_column = len(col_oid) == len(entry_oid) + 1
            if not is_child_column:
                continue
            if col_oid[: len(entry_oid)] != entry_oid:
                continue
            columns[col_name] = cast("ColumnMeta", col_info)
        return columns

    def register_tables(
        self,
        mib: str,
        mib_json: MibJsonObject,
        type_registry: TypeRegistry,
        mib_jsons: MibJsonMap,
    ) -> None:
        """Detect and register all tables in the MIB.

        Note: Currently tables are NOT registered in pysnmp to avoid index/unregister errors.
        Table structures are tracked in JSON but not exported to pysnmp.

        Args:
            mib: MIB name
            mib_json: MIB dictionary with object definitions
            type_registry: Type registry for resolving column types
            mib_jsons: Full collection of loaded MIBs (updated with table rows)

        """
        if not (self.mib_table and self.mib_table_row and self.mib_table_column):
            self.logger.warning(
                "Skipping table registration for %s: MIB table classes not available", mib
            )
            return

        tables: dict[str, TableData] = {}

        for name, info in mib_json.items():
            if not self._is_table_candidate(info):
                continue
            table_info = cast("dict[str, object]", info)
            table_oid = self._oid_tuple(table_info.get("oid"))
            if table_oid is None:
                continue

            entry_match = self._find_table_entry(mib_json, table_oid)
            if entry_match is None:
                continue
            entry_name, entry_oid, entry_meta = entry_match

            columns = self._collect_table_columns(mib_json, name, entry_name, entry_oid)
            if not columns:
                continue

            tables[name] = {
                "table": cast("TableMeta", info),
                "entry": entry_meta,
                "columns": columns,
            }

        # Register each table in the JSON model (but NOT in pysnmp to avoid index errors)
        for table_name, table_data in tables.items():
            self.logger.debug(
                "%s",
                f"Processing table: {table_name} (entry: {table_data['entry']})",
            )
            try:
                self.register_single_table(mib, table_name, table_data, type_registry, mib_jsons)
            except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError) as e:
                self.logger.warning(
                    "Could not register table %s: %s",
                    table_name,
                    e,
                    exc_info=True,
                )

    def register_single_table(
        self,
        mib: str,
        table_name: str,
        table_data: TableData,
        type_registry: TypeRegistry,
        mib_jsons: MibJsonMap,
    ) -> None:
        """Register a single table by adding a row to the JSON model and PySNMP MIB tree.

        Args:
            mib: MIB name
            table_name: Name of the table to register
            table_data: Table structure (table, entry, columns)
            type_registry: Type registry for resolving column types
            mib_jsons: Full collection of MIBs (to update with table rows)

        """
        mib_json = mib_jsons.get(mib)
        if not mib_json:
            self.logger.error("No in-memory JSON found for MIB %s", mib)
            return

        # Check if this is an augmented table (has index_from in entry)
        # Augmented tables should not have rows created here - they use parent table rows
        entry = table_data["entry"]
        if entry.get("index_from"):
            self.logger.debug(
                "Skipping row creation for augmented table %s - it uses index_from", table_name
            )
            # Still need to ensure the table JSON exists, but don't add rows
            table_json = mib_json.get(table_name)
            if table_json is None or not isinstance(table_json, dict):
                table_json = {"rows": []}
                mib_json[table_name] = table_json
            if "rows" not in table_json:
                table_json["rows"] = []
            return

        table_json = mib_json.get(table_name)
        if table_json is None or not isinstance(table_json, dict):
            table_json = {"rows": []}
            mib_json[table_name] = table_json
        if "rows" not in table_json:
            table_json["rows"] = []

        # Build a new row with initial values for all columns (including index columns)
        new_row: MibJsonObject = {}
        columns = table_data["columns"]
        for col_name, col_info in columns.items():
            type_name = col_info.get("type", "")
            type_info = type_registry.get(type_name, {}) if type_name else {}
            base_type = type_info.get("base_type") or type_name
            value = self._get_default_value_for_type(col_info, type_name, type_info, base_type)
            new_row[col_name] = value

        # Set index columns to 1 (or suitable value)
        index_names = entry.get("indexes", [])
        for idx_col in index_names:
            if idx_col in new_row:
                new_row[idx_col] = 1

        # Add the row to the table JSON
        rows: object = table_json.get("rows")
        if not isinstance(rows, list):
            table_json["rows"] = []
            rows = table_json["rows"]
        if isinstance(rows, list):
            rows.append(new_row)
        self.logger.info(
            "%s",
            f"Created row in {table_name} for MIB {mib} with {len(new_row)} columns: {new_row}",
        )

        # --- PySNMP Table/Row/Column Registration ---
        self._register_pysnmp_table(mib, table_name, table_data, type_registry, new_row)

    def _register_pysnmp_table(
        self,
        mib: str,
        table_name: str,
        table_data: TableData,
        type_registry: TypeRegistry,
        new_row: MibJsonObject,
    ) -> None:
        """Register table structures in PySNMP.

        Args:
            mib: MIB name
            table_name: Table name
            table_data: Table structure
            type_registry: Type registry
            new_row: Row data to register

        """
        mib_builder = self.mib_builder
        if not mib_builder:
            self.logger.warning("mib_builder not available for table %s", table_name)
            return

        table_obj = table_data["table"]
        entry_obj = table_data["entry"]
        columns = table_data["columns"]

        table_oid = self._oid_tuple(table_obj.get("oid"))
        entry_oid = self._oid_tuple(entry_obj.get("oid"))
        if table_oid is None or entry_oid is None:
            self.logger.warning("Table OID metadata invalid for %s", table_name)
            return

        if self.mib_table is None or self.mib_table_row is None or self.mib_table_column is None:
            self.logger.warning("MIB table factories missing for table %s", table_name)
            return

        # Create Table, Row, and Column objects
        self.mib_table(table_oid)
        self.mib_table_row(entry_oid)
        col_syms = []
        col_names = []
        debug_oid_list = []
        self.logger.debug("Registering table: %s OID=%s", table_name, table_oid)
        self.logger.debug("Registering row: %sEntry OID=%s", table_name, entry_oid)
        for col_name, col_info in columns.items():
            col_oid = self._oid_tuple(col_info.get("oid"))
            if col_oid is None:
                continue
            # Resolve SNMP type for the column
            type_name = col_info.get("type", "")
            type_info = type_registry.get(type_name, {}) if type_name else {}
            base_type = type_info.get("base_type") or type_name
            pysnmp_type = self._resolve_snmp_type(base_type, col_name, table_name)
            if pysnmp_type is None:
                continue
            col_syms.append(self.mib_table_column(col_oid, pysnmp_type()))
            self.logger.debug(
                "Registering column: %s OID=%s type=%s",
                col_name,
                col_oid,
                base_type,
            )
            debug_oid_list.append(col_oid)
            col_names.append(col_name)

        self.logger.info(
            "About to export table %s with OIDs: table=%s, row=%s, columns=%s",
            table_name,
            table_oid,
            entry_oid,
            debug_oid_list,
        )

        # DISABLED: Dynamic table registration doesn't fully work with pysnmp's responder
        # Use compiled MIBs with proper table definitions instead
        self.logger.info("Skipped exporting table %s to pysnmp (JSON-only for now)", table_name)

        # Register row instances (best-effort)
        self._register_row_instances(
            mib,
            table_name,
            table_data,
            type_registry,
            col_names,
            new_row,
            suppress_export=True,
        )

    def _try_export_row_symbols(self) -> None:
        if not self.mib_builder:
            return
        self.mib_builder.export_symbols("SNMPv2-SMI")

    def _register_single_column_instance(
        self,
        table_name: str,
        col_name: str,
        columns: dict[str, ColumnMeta],
        type_registry: TypeRegistry,
        new_row: MibJsonObject,
    ) -> bool:
        col_info = columns.get(col_name)
        if not col_info:
            raise KeyError(col_name)

        type_name = col_info.get("type", "")
        type_info = type_registry.get(type_name, {}) if type_name else {}
        base_type = type_info.get("base_type") or type_name
        pysnmp_type = self._resolve_snmp_type(base_type, col_name, table_name)
        if pysnmp_type is None:
            return False

        raw_val = new_row.get(col_name)
        if raw_val is None:
            raw_val = self._get_default_value_for_type(col_info, type_name, type_info, base_type)
        pysnmp_type(raw_val)

        if self.mib_scalar_instance is None:
            return False
        self.mib_scalar_instance()
        return True

    def _register_row_instances(
        self,
        _mib: str,
        table_name: str,
        table_data: TableData,
        type_registry: TypeRegistry,
        col_names: list[str],
        new_row: MibJsonObject,
        *,
        suppress_export: bool = False,
    ) -> None:
        """Register individual row instances in PySNMP.

        Minimal implementation for unit tests: attempts to export symbols and create
        scalar instances for each column name. Errors are logged, but registration
        remains best-effort (complete table support requires compiled MIBs).
        """
        try:
            if not col_names:
                self.logger.warning("No row instances registered")
                return

            if not suppress_export:
                try:
                    self._try_export_row_symbols()
                except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                    self.logger.exception("Error exporting")

            if self.mib_scalar_instance is None:
                self.logger.warning("No scalar instance factory available for %s", table_name)
                return

            created_any = False

            missing_column: str | None = None
            columns = table_data["columns"]
            for col_name in col_names:
                try:
                    created_any = self._register_single_column_instance(
                        table_name,
                        col_name,
                        columns,
                        type_registry,
                        new_row,
                    ) or created_any
                except KeyError:
                    missing_column = col_name
                    break
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                    Exception,
                ):
                    self.logger.exception("Error registering row instance")

            if missing_column is not None:
                self.logger.error("Missing column %s", missing_column)
                return

            if not created_any:
                self.logger.warning("No row instances registered")

        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("Error registering row instances")
            return

    def _resolve_snmp_type(
        self, base_type: str, _col_name: str, _table_name: str
    ) -> SnmpTypeFactory | None:
        """Resolve an SNMP type class from its base type name.

        Args:
            base_type: Base type name (e.g., 'Integer32', 'OctetString')
            col_name: Column name (for error reporting)
            table_name: Table name (for error reporting)

        Returns:
            The SNMP type class, or None if resolution failed

        """
        if not base_type:
            return None
        try:
            resolved = self.snmp_type_resolver.resolve_type_factory(base_type, self.mib_builder)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            resolved = None

        if resolved is not None:
            return resolved

        try:
            fallback = getattr(rfc1902, base_type, None)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            return None

        return fallback if callable(fallback) else None

    @staticmethod
    def _oid_tuple(value: InterfaceObject) -> tuple[int, ...] | None:
        if isinstance(value, tuple) and all(isinstance(part, int) for part in value):
            return value
        if isinstance(value, list) and all(isinstance(part, int) for part in value):
            return tuple(value)
        return None

    def _get_default_value_for_type(
        self,
        col_info: ColumnMeta,
        type_name: str,
        type_info: TypeInfo,
        _base_type: str,
    ) -> InterfaceObject:
        """Determine a sensible default value for a type using BaseTypeHandler.

        Args:
            col_info: Column information dictionary
            type_name: Type name
            type_info: Type information from registry
            base_type: Base type name (kept for backward compatibility)

        Returns:
            A sensible default value for the type

        """
        # Use BaseTypeHandler which only knows about 3 base ASN.1 types
        # and resolves everything else from the type registry
        context = {"initial": col_info.get("initial")} if "initial" in col_info else {}
        # Allow caller-provided type_info to be considered by BaseTypeHandler
        if isinstance(type_info, dict) and type_info:
            context["type_info"] = type_info
        return self.type_handler.get_default_value(type_name, context)
