"""
Table Registrar: Handles registration of SNMP tables in the MIB.

Separates table registration logic from SNMPAgent, improving testability
and making table registration behavior clearer and more maintainable.
"""

import logging
from typing import Any, Dict, Set, Optional


class TableRegistrar:
    """Manages the discovery and registration of SNMP tables from MIB JSON data."""

    def __init__(
        self,
        mib_builder: Any,
        mib_scalar_instance: Any,
        mib_table: Any,
        mib_table_row: Any,
        mib_table_column: Any,
        logger: logging.Logger,
    ):
        """
        Initialize the TableRegistrar.

        Args:
            mib_builder: PySNMP MIB builder instance
            mib_scalar_instance: PySNMP MibScalarInstance class
            mib_table: PySNMP MibTable class
            mib_table_row: PySNMP MibTableRow class
            mib_table_column: PySNMP MibTableColumn class
            logger: Logger instance for debug/error messages
        """
        self.mib_builder = mib_builder
        self.mib_scalar_instance = mib_scalar_instance
        self.mib_table = mib_table
        self.mib_table_row = mib_table_row
        self.mib_table_column = mib_table_column
        self.logger = logger

    def find_table_related_objects(self, mib_json: Dict[str, Any]) -> Set[str]:
        """
        Return set of table-related object names (tables, entries, columns).

        Identifies all objects in the MIB JSON that are part of table structures,
        allowing scalars to be registered separately.

        Args:
            mib_json: MIB dictionary with object definitions

        Returns:
            Set of object names that are table-related (tables, entries, columns)
        """
        table_related_objects: Set[str] = set()
        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue
            if name.endswith('Table') or name.endswith('Entry'):
                table_related_objects.add(name)
                if name.endswith('Entry'):
                    entry_oid = tuple(info.get('oid', []))
                    # Find all columns that are children of this entry
                    for col_name, col_info in mib_json.items():
                        if not isinstance(col_info, dict):
                            continue
                        col_oid = tuple(col_info.get('oid', []))
                        if (len(col_oid) == len(entry_oid) + 1 and
                            col_oid[:len(entry_oid)] == entry_oid):
                            table_related_objects.add(col_name)
        return table_related_objects

    def register_tables(
        self,
        mib: str,
        mib_json: Dict[str, Any],
        type_registry: Dict[str, Any],
        mib_jsons: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Detect and register all tables in the MIB.

        Note: Currently tables are NOT registered in pysnmp to avoid index/unregister errors.
        Table structures are tracked in JSON but not exported to pysnmp.

        Args:
            mib: MIB name
            mib_json: MIB dictionary with object definitions
            type_registry: Type registry for resolving column types
            mib_jsons: Full collection of loaded MIBs (updated with table rows)
        """
        if not (self.mib_table and self.mib_table_row and self.mib_table_column):
            self.logger.debug(f"Skipping table registration for {mib}: MIB table classes not available")
            return

        # Find all tables by looking for objects ending in "Table"
        tables: Dict[str, Dict[str, Any]] = {}

        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue
            if name.endswith('Table') and info.get('access') == 'not-accessible':
                # Found a table, now find its entry and columns
                table_prefix = name[:-5]  # Remove "Table" suffix
                entry_name = f"{table_prefix}Entry"

                # Check if entry exists
                if entry_name not in mib_json:
                    continue

                entry_oid = tuple(mib_json[entry_name]['oid'])

                # Collect all columns for this table by checking OID hierarchy
                # Columns must be direct children of the entry OID
                columns = {}
                for col_name, col_info in mib_json.items():
                    if not isinstance(col_info, dict):
                        continue
                    if col_name in [name, entry_name]:
                        continue
                    col_oid = tuple(col_info.get('oid', []))
                    # Check if column OID is a child of entry OID
                    if (len(col_oid) == len(entry_oid) + 1 and
                        col_oid[:len(entry_oid)] == entry_oid):
                        columns[col_name] = col_info

                if columns:
                    tables[name] = {
                        'table': info,
                        'entry': mib_json[entry_name],
                        'columns': columns,
                        'prefix': table_prefix
                    }

        # Register each table in the JSON model (but NOT in pysnmp to avoid index errors)
        for table_name, table_data in tables.items():
            self.logger.debug(f"Processing table: {table_name} (entry: {table_data['entry']})")
            try:
                self.register_single_table(mib, table_name, table_data, type_registry, mib_jsons)
            except Exception as e:
                self.logger.warning(f"Could not register table {table_name}: {e}", exc_info=True)

    def register_single_table(
        self,
        mib: str,
        table_name: str,
        table_data: Dict[str, Any],
        type_registry: Dict[str, Any],
        mib_jsons: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Register a single table by adding a row to the JSON model and PySNMP MIB tree.

        Args:
            mib: MIB name
            table_name: Name of the table to register
            table_data: Table structure (table, entry, columns, prefix)
            type_registry: Type registry for resolving column types
            mib_jsons: Full collection of MIBs (to update with table rows)
        """
        mib_json = mib_jsons.get(mib)
        if not mib_json:
            self.logger.error(f"No in-memory JSON found for MIB {mib}")
            return

        table_json = mib_json.get(table_name)
        if table_json is None:
            table_json = {'rows': []}
            mib_json[table_name] = table_json
        if 'rows' not in table_json:
            table_json['rows'] = []

        # Build a new row with initial values for all columns (including index columns)
        new_row = {}
        for col_name, col_info in table_data['columns'].items():
            type_name = col_info.get('type', '')
            type_info = type_registry.get(type_name, {}) if type_name else {}
            base_type = type_info.get('base_type') or type_name
            value = self._get_default_value_for_type(col_info, type_name, type_info, base_type)
            new_row[col_name] = value

        # Set index columns to 1 (or suitable value)
        entry = table_data['entry']
        index_names = entry.get('indexes', [])
        for idx_col in index_names:
            if idx_col in new_row:
                new_row[idx_col] = 1

        # Add the row to the table JSON
        table_json['rows'].append(new_row)
        self.logger.info(f"Created row in {table_name} for MIB {mib} with {len(new_row)} columns: {new_row}")

        # --- PySNMP Table/Row/Column Registration ---
        self._register_pysnmp_table(mib, table_name, table_data, type_registry, new_row)

    def _register_pysnmp_table(
        self,
        mib: str,
        table_name: str,
        table_data: Dict[str, Any],
        type_registry: Dict[str, Any],
        new_row: Dict[str, Any],
    ) -> None:
        """
        Register table structures in PySNMP.

        Args:
            mib: MIB name
            table_name: Table name
            table_data: Table structure
            type_registry: Type registry
            new_row: Row data to register
        """
        mib_builder = self.mib_builder
        if not mib_builder:
            self.logger.warning(f"mib_builder not available for table {table_name}")
            return

        table_oid = tuple(table_data['table']['oid'])
        entry_oid = tuple(table_data['entry']['oid'])
        columns = table_data['columns']

        # Create Table, Row, and Column objects
        table_sym = self.mib_table(table_oid)
        row_sym = self.mib_table_row(entry_oid)
        col_syms = []
        col_names = []
        debug_oid_list = []
        self.logger.debug(f"Registering table: {table_name} OID={table_oid}")
        self.logger.debug(f"Registering row: {table_name}Entry OID={entry_oid}")
        for col_name, col_info in columns.items():
            col_oid = tuple(col_info['oid'])
            # Resolve SNMP type for the column
            type_name = col_info.get('type', '')
            type_info = type_registry.get(type_name, {}) if type_name else {}
            base_type = type_info.get('base_type') or type_name
            pysnmp_type = self._resolve_snmp_type(base_type, col_name, table_name)
            if pysnmp_type is None:
                continue
            col_syms.append(self.mib_table_column(col_oid, pysnmp_type()))
            self.logger.debug(f"Registering column: {col_name} OID={col_oid} type={base_type}")
            debug_oid_list.append(col_oid)
            col_names.append(col_name)

        self.logger.info(f"About to export table {table_name} with OIDs: table={table_oid}, row={entry_oid}, columns={debug_oid_list}")
        # DISABLED: Dynamic table registration doesn't work with pysnmp's responder
        # Use compiled MIBs with proper table definitions instead
        self.logger.info(f"Skipped exporting table {table_name} to pysnmp (JSON-only for now)")

        # Register row instances (stub - table support via proper MIB compilation)
        self._register_row_instances(mib, table_name, table_data, type_registry, col_names, new_row)

    def _register_row_instances(
        self,
        mib: str,
        table_name: str,
        table_data: Dict[str, Any],
        type_registry: Dict[str, Any],
        col_names: list[str],
        new_row: Dict[str, Any],
    ) -> None:
        """
        Register individual row instances in PySNMP.

        Stub: Table support requires properly compiled MIBs with table definitions.
        """
        pass

    def _resolve_snmp_type(self, base_type: str, col_name: str, table_name: str) -> Optional[Any]:
        """
        Resolve an SNMP type class from its base type name.

        Args:
            base_type: Base type name (e.g., 'Integer32', 'OctetString')
            col_name: Column name (for error reporting)
            table_name: Table name (for error reporting)

        Returns:
            The SNMP type class, or None if resolution failed
        """
        try:
            if base_type:
                try:
                    return self.mib_builder.import_symbols('SNMPv2-SMI', base_type)[0]
                except Exception:
                    try:
                        return self.mib_builder.import_symbols('SNMPv2-TC', base_type)[0]
                    except Exception:
                        from pysnmp.proto import rfc1902
                        return getattr(rfc1902, base_type, None)
            return None
        except Exception as e:
            self.logger.error(f"Error resolving SNMP type {base_type} for column {col_name} in {table_name}: {e}", exc_info=True)
            return None

    def _get_default_value_for_type(
        self,
        col_info: Dict[str, Any],
        type_name: str,
        type_info: Dict[str, Any],
        base_type: str
    ) -> Any:
        """
        Determine a sensible default value for a type based on type registry information.

        Uses a generic approach that works for any SNMP type.

        Args:
            col_info: Column information dictionary
            type_name: Type name
            type_info: Type information from registry
            base_type: Base type name

        Returns:
            A sensible default value for the type
        """
        # 1. Use explicit initial value if present and not None
        if 'initial' in col_info and col_info['initial'] is not None:
            return col_info['initial']

        # 2. For enumerated types, use the first enum value
        if type_info.get('enums'):
            enums = type_info.get('enums', [])
            if enums and isinstance(enums, list) and len(enums) > 0:
                return enums[0].get('value', 0)
            return 0

        # 3. If base_type is set, use it to determine the default
        if base_type and base_type != type_name:
            if base_type in ('Integer32', 'Integer', 'Counter32', 'Gauge32', 'Unsigned32', 'TimeTicks'):
                return 0
            elif base_type in ('OctetString', 'DisplayString'):
                return ''
            elif base_type == 'ObjectIdentifier':
                return (0, 0)  # Return a tuple instead of string for ObjectIdentifier

        # 4. For types with null base_type, infer from constraints
        constraints = type_info.get('constraints', [])
        if constraints:
            for constraint in constraints:
                constraint_type = constraint.get('type', '')

                # ValueRangeConstraint suggests numeric type
                if constraint_type == 'ValueRangeConstraint':
                    return 0

                # ValueSizeConstraint suggests octet string or similar
                elif constraint_type == 'ValueSizeConstraint':
                    min_size = constraint.get('min', 0)
                    max_size = constraint.get('max', 0)
                    if min_size == 4 and max_size == 4:
                        return '0.0.0.0'
                    return ''

        # 5. Check size field as fallback
        size = type_info.get('size')
        if size:
            if isinstance(size, dict):
                size_type = size.get('type')
                if size_type == 'set':
                    allowed = size.get('allowed', [])
                    if allowed == [4]:
                        return '0.0.0.0'  # IpAddress
                    return ''  # OctetString
                elif size_type == 'range':
                    return ''  # OctetString

        # 6. Default fallback: use 0 for unknown types
        return 0
