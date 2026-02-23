"""MIB Registrar: Handles registration of MIB objects (scalars and tables) in the SNMP agent.

Separates MIB registration logic from SNMPAgent, improving testability
and making MIB registration behavior clearer and more maintainable.
"""

# pylint: disable=broad-exception-caught,logging-fstring-interpolation
# pylint: disable=redefined-builtin,invalid-name

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from pysnmp.proto import rfc1902

from app import mib_metadata
from app.json_format import write_json_with_horizontal_oid_lists
from app.mib_registrar_helpers import (
    RegistrarCommonDeps,
    RegistrarScalarBuilder,
    RegistrarScalarDeps,
    RegistrarTableBuilder,
    RegistrarTableDeps,
    RegistrarValueDecoder,
    RegistrarWriteHooks,
)
from app.model_paths import AGENT_MODEL_DIR
from plugins.type_encoders import encode_value

ObjectType: TypeAlias = Any


@dataclass
class SNMPContext:
    """Container for PySNMP objects required for MIB registration.

    Groups all pysnmp-related dependencies (MibBuilder and MIB type classes)
    into a single context object for cleaner dependency injection.
    """

    mib_builder: ObjectType
    """PySNMP MIB builder instance"""
    mib_scalar_instance: ObjectType
    """MibScalarInstance class from SNMPv2-SMI"""
    mib_table: ObjectType
    """MibTable class from SNMPv2-SMI"""
    mib_table_row: ObjectType
    """MibTableRow class from SNMPv2-SMI"""
    mib_table_column: ObjectType
    """MibTableColumn class from SNMPv2-SMI"""


class MibRegistrar:
    """Manages the registration of MIB objects (scalars and tables) from MIB JSON data."""

    def __init__(
        self,
        snmp_context: SNMPContext,
        logger: logging.Logger,
        start_time: float,
    ) -> None:
        """Initialize the MibRegistrar.

        Args:
            snmp_context: Container with PySNMP MIB builder and type classes
            logger: Logger instance
            start_time: Agent start time (for sysUpTime calculation)

        """
        self.mib_builder = snmp_context.mib_builder
        self.mib_scalar_instance_cls = snmp_context.mib_scalar_instance
        self.mib_table_cls = snmp_context.mib_table
        self.mib_table_row_cls = snmp_context.mib_table_row
        self.mib_table_column_cls = snmp_context.mib_table_column
        self.logger = logger
        self.start_time = start_time
        self._value_decoder = RegistrarValueDecoder(self.logger)
        self._write_hooks = RegistrarWriteHooks(self.logger)
        common_deps = RegistrarCommonDeps(
            logger=self.logger,
            get_pysnmp_type=self._get_pysnmp_type,
            normalize_access=self._normalize_access,
            preferred_snmp_types=self._preferred_snmp_types,
            decode_value=self._value_decoder.decode_value,
            encode_value=encode_value,
            write_hooks=self._write_hooks,
        )
        self._scalar_builder = RegistrarScalarBuilder(
            RegistrarScalarDeps(
                mib_scalar_instance_cls=self.mib_scalar_instance_cls,
                start_time=self.start_time,
                common=common_deps,
            )
        )
        self._table_builder = RegistrarTableBuilder(
            RegistrarTableDeps(
                mib_scalar_instance_cls=self.mib_scalar_instance_cls,
                mib_table_cls=self.mib_table_cls,
                mib_table_row_cls=self.mib_table_row_cls,
                mib_table_column_cls=self.mib_table_column_cls,
                common=common_deps,
            )
        )

    def _sync_builders(self) -> None:
        common_deps = RegistrarCommonDeps(
            logger=self.logger,
            get_pysnmp_type=self._get_pysnmp_type,
            normalize_access=self._normalize_access,
            preferred_snmp_types=self._preferred_snmp_types,
            decode_value=self._value_decoder.decode_value,
            encode_value=encode_value,
            write_hooks=self._write_hooks,
        )
        self._scalar_builder = RegistrarScalarBuilder(
            RegistrarScalarDeps(
                mib_scalar_instance_cls=self.mib_scalar_instance_cls,
                start_time=self.start_time,
                common=common_deps,
            )
        )
        self._table_builder = RegistrarTableBuilder(
            RegistrarTableDeps(
                mib_scalar_instance_cls=self.mib_scalar_instance_cls,
                mib_table_cls=self.mib_table_cls,
                mib_table_row_cls=self.mib_table_row_cls,
                mib_table_column_cls=self.mib_table_column_cls,
                common=common_deps,
            )
        )

    def register_all_mibs(
        self,
        mib_jsons: dict[str, dict[str, ObjectType]],
        type_registry_path: str | None = None,
    ) -> None:
        """Register all MIBs with their objects (scalars and tables).

        Args:
            mib_jsons: Dictionary mapping MIB names to their JSON data
            type_registry_path: Optional path to types.json (defaults to data/types.json)

        """
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Load the type registry from the exported JSON file
        if type_registry_path is None:
            type_registry_path = str(Path(__file__).resolve().parent.parent / "data" / "types.json")

        try:
            type_registry_path_obj = Path(type_registry_path)
            with type_registry_path_obj.open(encoding="utf-8") as f:
                type_registry = json.load(f)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("Failed to load type registry")
            type_registry = {}

        # Register each MIB with all its objects (scalars and tables) at once
        for mib, mib_json in mib_jsons.items():
            self.register_mib(mib, mib_json, type_registry)

    def _load_type_registry(self, type_registry_path: str | None = None) -> dict[str, ObjectType]:
        """Load type registry from JSON file.

        Args:
            type_registry_path: Optional path to types.json (defaults to data/types.json)

        Returns:
            Type registry dictionary, or empty dict if load fails

        """
        if type_registry_path is None:
            type_registry_path_obj = Path(__file__).resolve().parent.parent / "data" / "types.json"
        else:
            type_registry_path_obj = Path(type_registry_path)

        try:
            with type_registry_path_obj.open("r", encoding="utf-8") as f:
                result = json.load(f)
                return result if isinstance(result, dict) else {}
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            return {}

    def _get_sysor_container(self, snmp2: dict[str, ObjectType]) -> dict[str, ObjectType]:
        """Extract the container for sysOR* objects (supports both schema formats).

        Args:
            snmp2: SNMPv2-MIB JSON data

        Returns:
            Dictionary containing objects (either snmp2["objects"] or snmp2 itself)

        """
        if (
            isinstance(snmp2, dict)
            and "objects" in snmp2
            and isinstance(snmp2["objects"], dict)
        ):
            return snmp2["objects"]
        return snmp2

    def _ensure_sysor_table_exists(self, container: dict[str, ObjectType]) -> None:
        """Ensure sysORTable structure exists in container.

        Args:
            container: Object container to check/update

        """
        if "sysORTable" not in container or not isinstance(container.get("sysORTable"), dict):
            container["sysORTable"] = {
                "oid": [1, 3, 6, 1, 2, 1, 1, 9],
                "type": "MibTable",
                "rows": [],
            }
            self.logger.info("Created missing sysORTable entry in SNMPv2-MIB schema")

    def _persist_sysor_schema(self, snmp2: dict[str, ObjectType]) -> None:
        """Persist updated sysORTable schema to disk.

        Args:
            snmp2: Updated SNMPv2-MIB JSON data

        """
        schema_dir = AGENT_MODEL_DIR
        snmp2_schema_file = schema_dir / "SNMPv2-MIB" / "schema.json"

        try:
            snmp2_schema_file.parent.mkdir(parents=True, exist_ok=True)

            # Load existing schema to preserve all metadata
            existing_schema = {}
            if snmp2_schema_file.exists():
                with snmp2_schema_file.open("r", encoding="utf-8") as f:
                    existing_schema = json.load(f)

            # Merge updated data into existing schema.
            # IMPORTANT: only persist sysORTable rows here. Column metadata such as
            # sysORDescr OID/type/access must remain canonical from generated schema.
            existing_objects = existing_schema.get("objects")
            if not isinstance(existing_objects, dict):
                existing_objects = {}
                existing_schema["objects"] = existing_objects

            incoming_objects = snmp2.get("objects") if isinstance(snmp2.get("objects"), dict) else snmp2
            if isinstance(incoming_objects, dict):
                incoming_table = incoming_objects.get("sysORTable")
                if isinstance(incoming_table, dict):
                    existing_table = existing_objects.get("sysORTable")
                    if not isinstance(existing_table, dict):
                        existing_table = {
                            "oid": [1, 3, 6, 1, 2, 1, 1, 9],
                            "type": "MibTable",
                            "rows": [],
                        }
                        existing_objects["sysORTable"] = existing_table

                    rows = incoming_table.get("rows")
                    if isinstance(rows, list):
                        existing_table["rows"] = rows

            write_json_with_horizontal_oid_lists(snmp2_schema_file, existing_schema)
            self.logger.info("Persisted updated sysORTable schema to %s", snmp2_schema_file)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError) as e:
            self.logger.warning("Could not persist schema to disk: %s", e)

    def populate_sysor_table(
        self,
        mib_jsons: dict[str, dict[str, ObjectType]],
        type_registry_path: str | None = None,
    ) -> None:
        """Populate sysORTable with the MIBs being served by this agent.

        This is called after all MIBs are registered to dynamically generate
        sysORTable rows based on the actual MIBs that have been loaded.

        Args:
            mib_jsons: Dictionary mapping MIB names to their JSON data
            type_registry_path: Optional path to types.json (defaults to data/types.json)

        """
        try:
            # Get the list of MIB names from config
            mib_names = list(mib_jsons.keys())
            self.logger.debug("Populating sysORTable with MIBs: %s", mib_names)

            # Generate rows based on the MIBs loaded
            sysor_rows = mib_metadata.get_sysor_table_rows(mib_names)

            if not sysor_rows:
                self.logger.warning("No sysORTable rows generated from MIB metadata")
                return

            # Update the SNMPv2-MIB JSON with the generated rows
            if "SNMPv2-MIB" not in mib_jsons:
                return

            snmp2 = mib_jsons["SNMPv2-MIB"]
            container = self._get_sysor_container(snmp2)
            self._ensure_sysor_table_exists(container)

            container["sysORTable"]["rows"] = sysor_rows
            self.logger.info("Updated sysORTable with %d rows", len(sysor_rows))

            # Re-register SNMPv2-MIB to apply the updated sysORTable
            type_registry = self._load_type_registry(type_registry_path)
            self.register_mib("SNMPv2-MIB", snmp2, type_registry)

            # Persist the updated schema back to disk
            self._persist_sysor_schema(snmp2)
            self.logger.info("sysORTable successfully populated with MIB implementations")
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("Error populating sysORTable")

    def register_mib(
        self, mib: str, mib_json: dict[str, ObjectType], type_registry: dict[str, ObjectType]
    ) -> None:
        """Register a complete MIB with all its objects (scalars and tables)."""
        try:
            # Handle new schema structure: {"objects": {...}, "traps": {...}}
            # vs old flat structure: {obj1: {...}, obj2: {...}}
            if "objects" in mib_json and isinstance(mib_json["objects"], dict):
                # New structure with separate objects and traps
                objects_json = mib_json["objects"]
                traps_json = mib_json.get("traps", {})
                if traps_json:
                    self.logger.info(
                        "%s", f"MIB {mib} has {len(traps_json)} trap(s): {list(traps_json.keys())}"
                    )
            else:
                # Old flat structure - all items are objects
                objects_json = mib_json

            export_symbols = self._build_mib_symbols(mib, objects_json, type_registry)
            if export_symbols:
                if mib == "SNMPv2-MIB":
                    sysor_symbols = sorted(k for k in export_symbols if k.startswith("sysOR"))
                    if sysor_symbols:
                        self.logger.info(
                            "SNMPv2-MIB sysOR symbols before filter: %s",
                            ", ".join(sysor_symbols),
                        )
                # Filter out symbols that are already exported to avoid SmiError
                existing_symbols = set(self.mib_builder.mibSymbols.get(mib, {}).keys())
                filtered_symbols = {
                    k: v for k, v in export_symbols.items() if k not in existing_symbols
                }
                if len(filtered_symbols) < len(export_symbols):
                    skipped = len(export_symbols) - len(filtered_symbols)
                    self.logger.debug("Skipped %s duplicate symbols for %s", skipped, mib)
                if mib == "SNMPv2-MIB":
                    sysor_filtered = sorted(k for k in filtered_symbols if k.startswith("sysOR"))
                    self.logger.info(
                        "SNMPv2-MIB sysOR symbols after filter: %s",
                        ", ".join(sysor_filtered) if sysor_filtered else "<none>",
                    )

                if filtered_symbols:
                    self.mib_builder.export_symbols(mib, **filtered_symbols)
                    self.logger.info("%s", f"Registered {len(filtered_symbols)} objects for {mib}")
                else:
                    self.logger.warning(
                        "All symbols for %s are already exported, skipping registration", mib
                    )
            else:
                self.logger.warning("No objects to register for %s", mib)
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            self.logger.exception("Error registering MIB %s", mib)

    @staticmethod
    def _preferred_snmp_types() -> set[str]:
        return {
            "Counter32",
            "Counter64",
            "Gauge32",
            "Unsigned32",
            "Integer32",
            "TimeTicks",
            "DisplayString",
            "OctetString",
            "DateAndTime",
        }

    @staticmethod
    def _normalize_access(access_raw: str) -> str:
        access_map = {
            "read-only": "readonly",
            "read-write": "readwrite",
            "read-create": "readcreate",
            "not-accessible": "noaccess",
            "accessible-for-notify": "notify",
        }
        return access_map.get(access_raw, access_raw)

    @staticmethod
    def _format_snmp_value(val: ObjectType) -> str:
        return RegistrarWriteHooks.format_snmp_value(val)

    def _build_write_commit_wrapper(
        self,
        dotted: str,
        friendly: str,
        is_writable: bool,  # noqa: FBT001
        original_write: ObjectType,
    ) -> Callable[..., None]:
        """Build the writeCommit wrapper function.

        Args:
            dotted: Dotted OID notation
            friendly: Friendly name (mib:object)
            is_writable: Whether object is writable
            original_write: Original writeCommit method (if any)

        Returns:
            Wrapper function for writeCommit

        """
        return self._write_hooks.build_write_commit_wrapper(
            dotted=dotted,
            friendly=friendly,
            is_writable=is_writable,
            original_write=original_write,
        )

    def _build_write_test_wrapper(
        self,
        dotted: str,
        friendly: str,
        is_writable: bool,  # noqa: FBT001
    ) -> Callable[..., None]:
        """Build the writeTest wrapper function.

        Args:
            dotted: Dotted OID notation
            friendly: Friendly name (mib:object)
            is_writable: Whether object is writable

        Returns:
            Wrapper function for writeTest

        """
        return self._write_hooks.build_write_test_wrapper(
            dotted=dotted,
            friendly=friendly,
            is_writable=is_writable,
        )

    def _attach_write_hooks(
        self,
        inst: ObjectType,
        dotted: str,
        friendly: str,
        *,
        is_writable: bool,
        original_write: ObjectType,
    ) -> None:
        """Attach write commit and write test hooks to an instance.

        Args:
            inst: MIB instance to attach hooks to
            dotted: Dotted OID notation
            friendly: Friendly name (mib:object)
            is_writable: Whether object is writable
            original_write: Original writeCommit method (if any)

        """
        self._write_hooks.attach_write_hooks(
            inst=inst,
            dotted=dotted,
            friendly=friendly,
            is_writable=is_writable,
            original_write=original_write,
        )

    def _resolve_table_entry(
        self,
        table_name: str,
        mib_json: dict[str, ObjectType],
    ) -> tuple[str, dict[str, ObjectType], tuple[int, ...], list[str]]:
        return self._table_builder.resolve_table_entry(table_name, mib_json)

    def _collect_table_columns(
        self,
        mib_json: dict[str, ObjectType],
        entry_oid: tuple[int, ...],
        type_registry: dict[str, ObjectType],
        symbols: dict[str, ObjectType],
    ) -> dict[str, tuple[tuple[int, ...], str, bool]]:
        return self._table_builder.collect_table_columns(
            mib_json=mib_json,
            entry_oid=entry_oid,
            type_registry=type_registry,
            symbols=symbols,
        )

    def _build_row_index_tuple(
        self,
        row_data: dict[str, ObjectType],
        index_names: list[str],
        columns_by_name: dict[str, tuple[tuple[int, ...], str, bool]],
        row_idx: int,
    ) -> tuple[int, ...]:
        return self._table_builder.build_row_index_tuple(
            row_data=row_data,
            index_names=index_names,
            columns_by_name=columns_by_name,
            row_idx=row_idx,
        )

    @staticmethod
    def _extract_row_values(row_data: dict[str, ObjectType]) -> dict[str, ObjectType]:
        return RegistrarTableBuilder.extract_row_values(row_data)

    @staticmethod
    def _resolve_table_cell_value(
        col_name: str,
        row_values: dict[str, ObjectType],
        index_names: list[str],
        index_tuple: tuple[int, ...],
    ) -> tuple[bool, ObjectType | int]:
        return RegistrarTableBuilder.resolve_table_cell_value(
            col_name=col_name,
            row_values=row_values,
            index_names=index_names,
            index_tuple=index_tuple,
        )

    def _create_table_instance(
        self,
        mib: str,
        col_name: str,
        column_context: tuple[tuple[int, ...], str, bool],
        instance_context: tuple[tuple[int, ...], object],
    ) -> tuple[str, object, str] | None:
        return self._table_builder.create_table_instance(
            mib=mib,
            col_name=col_name,
            column_context=column_context,
            instance_context=instance_context,
        )

    def _iter_scalar_candidates(
        self,
        mib_json: dict[str, ObjectType],
        table_related_objects: set[str],
    ) -> Iterator[tuple[str, dict[str, ObjectType], str, tuple[int, ...]]]:
        return self._scalar_builder.iter_scalar_candidates(mib_json, table_related_objects)

    def _resolve_scalar_type_value(
        self,
        name: str,
        info: dict[str, ObjectType],
        type_registry: dict[str, ObjectType],
    ) -> tuple[str, str, object] | None:
        return self._scalar_builder.resolve_scalar_type_value(name, info, type_registry)

    def _attach_sysuptime_read_hook(self, scalar_inst: ObjectType, pysnmp_type: ObjectType) -> None:
        self._scalar_builder.attach_sysuptime_read_hook(scalar_inst, pysnmp_type)

    def _build_scalar_instance(
        self,
        mib: str,
        name: str,
        scalar_context: tuple[tuple[int, ...], str],
        scalar_payload: tuple[str, ObjectType],
    ) -> tuple[ObjectType, str, str] | None:
        return self._scalar_builder.build_scalar_instance(
            mib=mib,
            name=name,
            scalar_context=scalar_context,
            scalar_payload=scalar_payload,
        )

    def _register_table_symbols(
        self,
        export_symbols: dict[str, ObjectType],
        mib: str,
        mib_json: dict[str, ObjectType],
        type_registry: dict[str, ObjectType],
    ) -> None:
        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue
            if not name.endswith("Table"):
                continue

            try:
                table_symbols = self._build_table_symbols(mib, name, info, mib_json, type_registry)
                export_symbols.update(table_symbols)
            except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError) as e:
                self.logger.exception("Error building table %s: %s", name, e)
                continue

    def _build_mib_symbols(
        self, mib: str, mib_json: dict[str, ObjectType], type_registry: dict[str, ObjectType]
    ) -> dict[str, ObjectType]:
        """Build all symbols for a MIB (scalars and tables) as a dictionary."""
        self._sync_builders()
        export_symbols = {}

        # Identify table-related objects
        table_related_objects = self._find_table_related_objects(mib_json)

        for name, info, access, oid_value in self._iter_scalar_candidates(
            mib_json,
            table_related_objects,
        ):
            resolved = self._resolve_scalar_type_value(name, info, type_registry)
            if not resolved:
                continue

            snmp_type_name, _base_type, value = resolved
            built = self._build_scalar_instance(
                mib=mib,
                name=name,
                scalar_context=(oid_value, access),
                scalar_payload=(snmp_type_name, value),
            )
            if not built:
                continue

            scalar_inst, max_access, value_type_name = built
            export_symbols[f"{name}Inst"] = scalar_inst
            self.logger.debug(
                "Added scalar %s (type %s, access %s, value type %s)",
                name,
                snmp_type_name,
                max_access,
                value_type_name,
            )

        self._register_table_symbols(export_symbols, mib, mib_json, type_registry)

        return export_symbols

    def _expand_ipaddress_components(self, value: ObjectType) -> tuple[int, ...]:
        return self._table_builder.expand_ipaddress_components(value)

    def _expand_string_components(self, value: ObjectType) -> tuple[int, ...]:
        return self._table_builder.expand_string_components(value)

    def _expand_integer_components(self, value: ObjectType) -> tuple[int, ...]:
        return self._table_builder.expand_integer_components(value)

    def _expand_index_value_to_oid_components(
        self,
        value: ObjectType,
        index_type: str,
    ) -> tuple[int, ...]:
        return self._table_builder.expand_index_value_to_oid_components(value, index_type)

    def _process_table_rows(
        self,
        table_name: str,
        rows_data: list[ObjectType],
        index_names: list[str],
        columns_by_name: dict[str, tuple[tuple[int, ...], str, bool]],
        mib: str,
    ) -> dict[str, ObjectType]:
        return self._table_builder.process_table_rows(
            table_name=table_name,
            rows_data=rows_data,
            index_names=index_names,
            columns_by_name=columns_by_name,
            mib=mib,
        )

    def _build_table_symbols(
        self,
        mib: str,
        table_name: str,
        table_info: dict[str, ObjectType],
        mib_json: dict[str, ObjectType],
        type_registry: dict[str, ObjectType],
    ) -> dict[str, ObjectType]:
        self._sync_builders()
        return self._table_builder.build_table_symbols(
            mib=mib,
            table_name=table_name,
            table_info=table_info,
            mib_json=mib_json,
            type_registry=type_registry,
        )

    def _find_table_related_objects(self, mib_json: dict[str, ObjectType]) -> set[str]:
        return self._table_builder.find_table_related_objects(mib_json)

    def _decode_value(self, value: ObjectType) -> ObjectType:
        return self._value_decoder.decode_value(value)

    def _get_pysnmp_type(self, base_type: str) -> ObjectType:
        """Get SNMP type class from base type name.

        Maps MIB type names (e.g., 'INTEGER') to PySNMP class names (e.g., 'Integer')
        due to naming differences between ASN.1 MIB definitions and PySNMP implementation.
        """
        # Map MIB type names to PySNMP class names
        type_map = {
            "INTEGER": "Integer",
            "OCTET STRING": "OctetString",
            "OBJECT IDENTIFIER": "ObjectIdentifier",
            "BITS": "Bits",
            "NULL": "Null",
            "IpAddress": "IpAddress",  # already correct
            "TimeTicks": "TimeTicks",  # already correct
            "Counter32": "Counter32",
            "Counter64": "Counter64",
            "Gauge32": "Gauge32",
            "Unsigned32": "Unsigned32",
            "Integer32": "Integer32",
            "DisplayString": "DisplayString",
            "OctetString": "OctetString",
            # Add more as needed
        }
        pysnmp_name = type_map.get(base_type, base_type)

        try:
            return self.mib_builder.import_symbols("SNMPv2-SMI", pysnmp_name)[0]
        except Exception:  # Broad catch for any import failures (SmiError, etc.)
            try:
                return self.mib_builder.import_symbols("SNMPv2-TC", pysnmp_name)[0]
            except Exception:  # Broad catch for any import failures
                return getattr(rfc1902, pysnmp_name, None)
