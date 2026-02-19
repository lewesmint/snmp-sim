"""
MIB Registrar: Handles registration of MIB objects (scalars and tables) in the SNMP agent.

Separates MIB registration logic from SNMPAgent, improving testability
and making MIB registration behavior clearer and more maintainable.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Set

from plugins.type_encoders import encode_value
import types


class MibRegistrar:
    """Manages the registration of MIB objects (scalars and tables) from MIB JSON data."""

    def __init__(
        self,
        mib_builder: Any,
        mib_scalar_instance: Any,
        mib_table: Any,
        mib_table_row: Any,
        mib_table_column: Any,
        logger: logging.Logger,
        start_time: float,
    ):
        """
        Initialize the MibRegistrar.

        Args:
            mib_builder: PySNMP MIB builder instance
            mib_scalar_instance: MibScalarInstance class from SNMPv2-SMI
            mib_table: MibTable class from SNMPv2-SMI
            mib_table_row: MibTableRow class from SNMPv2-SMI
            mib_table_column: MibTableColumn class from SNMPv2-SMI
            logger: Logger instance
            start_time: Agent start time (for sysUpTime calculation)
        """
        self.mib_builder = mib_builder
        self.MibScalarInstance = mib_scalar_instance
        self.MibTable = mib_table
        self.MibTableRow = mib_table_row
        self.MibTableColumn = mib_table_column
        self.logger = logger
        self.start_time = start_time

    def register_all_mibs(
        self, mib_jsons: Dict[str, Dict[str, Any]], type_registry_path: Optional[str] = None
    ) -> None:
        """
        Register all MIBs with their objects (scalars and tables).

        Args:
            mib_jsons: Dictionary mapping MIB names to their JSON data
            type_registry_path: Optional path to types.json (defaults to data/types.json)
        """
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Load the type registry from the exported JSON file
        from pathlib import Path
        if type_registry_path is None:
            type_registry_path = str(Path(__file__).resolve().parent.parent / "data" / "types.json")

        try:
            with open(type_registry_path, "r") as f:
                type_registry = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load type registry: {e}", exc_info=True)
            type_registry = {}

        # Register each MIB with all its objects (scalars and tables) at once
        for mib, mib_json in mib_jsons.items():
            self.register_mib(mib, mib_json, type_registry)

    def populate_sysor_table(
        self, mib_jsons: Dict[str, Dict[str, Any]], type_registry_path: Optional[str] = None
    ) -> None:
        """
        Populate sysORTable with the MIBs being served by this agent.

        This is called after all MIBs are registered to dynamically generate
        sysORTable rows based on the actual MIBs that have been loaded.

        Args:
            mib_jsons: Dictionary mapping MIB names to their JSON data
            type_registry_path: Optional path to types.json (defaults to data/types.json)
        """
        try:
            from app.mib_metadata import get_sysor_table_rows

            # Get the list of MIB names from config
            mib_names = list(mib_jsons.keys())
            self.logger.debug(f"Populating sysORTable with MIBs: {mib_names}")

            # Generate rows based on the MIBs loaded
            sysor_rows = get_sysor_table_rows(mib_names)

            if not sysor_rows:
                self.logger.warning("No sysORTable rows generated from MIB metadata")
                return

            # Update the SNMPv2-MIB JSON with the generated rows
            if "SNMPv2-MIB" in mib_jsons:
                snmp2 = mib_jsons["SNMPv2-MIB"]
                # Support new schema format {"objects": {...}, "traps": {...}}
                if isinstance(snmp2, dict) and "objects" in snmp2 and isinstance(snmp2["objects"], dict):
                    container = snmp2["objects"]
                else:
                    container = snmp2

                # Ensure sysORTable exists (create minimal structure if absent)
                if "sysORTable" not in container or not isinstance(container.get("sysORTable"), dict):
                    container["sysORTable"] = {"rows": []}
                    self.logger.info("Created missing sysORTable entry in SNMPv2-MIB schema")

                container["sysORTable"]["rows"] = sysor_rows
                self.logger.info(f"Updated sysORTable with {len(sysor_rows)} rows")

                # Re-register SNMPv2-MIB to apply the updated sysORTable
                from pathlib import Path
                type_registry_path_obj: Path
                if type_registry_path is None:
                    type_registry_path_obj = Path(__file__).resolve().parent.parent / "data" / "types.json"
                else:
                    type_registry_path_obj = Path(type_registry_path)
                try:
                    with type_registry_path_obj.open("r", encoding="utf-8") as f:
                        type_registry = json.load(f)
                except Exception:
                    type_registry = {}

                # Update only the sysORTable symbols
                # If the MIB uses new structure, pass the full structured schema so register_mib handles it
                self.register_mib("SNMPv2-MIB", snmp2, type_registry)
                
                # Persist the updated schema back to disk so API calls see the updated rows
                schema_dir = Path(__file__).resolve().parent.parent / "agent-model"
                snmp2_schema_file = schema_dir / "SNMPv2-MIB" / "schema.json"
                try:
                    snmp2_schema_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Load existing schema to preserve all metadata
                    existing_schema = {}
                    if snmp2_schema_file.exists():
                        with snmp2_schema_file.open("r", encoding="utf-8") as f:
                            existing_schema = json.load(f)
                    
                    # Merge updated data into existing schema
                    if "objects" in snmp2:
                        if "objects" not in existing_schema:
                            existing_schema["objects"] = {}
                        # Merge only the modified objects (sysORTable and sysOREntry)
                        for obj_name, obj_data in snmp2["objects"].items():
                            if obj_name in ("sysORTable", "sysOREntry") or obj_name.startswith("sysOR"):
                                existing_schema["objects"][obj_name] = obj_data
                    
                    if "traps" in snmp2:
                        existing_schema["traps"] = snmp2["traps"]
                    
                    with snmp2_schema_file.open("w", encoding="utf-8") as f:
                        json.dump(existing_schema, f, indent=2)
                    self.logger.info(f"Persisted updated sysORTable schema to {snmp2_schema_file}")
                except Exception as e:
                    self.logger.warning(f"Could not persist schema to disk: {e}")
                
                self.logger.info("sysORTable successfully populated with MIB implementations")
        except Exception as e:
            self.logger.error(f"Error populating sysORTable: {e}", exc_info=True)

    def register_mib(
        self, mib: str, mib_json: Dict[str, Any], type_registry: Dict[str, Any]
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
                    self.logger.info(f"MIB {mib} has {len(traps_json)} trap(s): {list(traps_json.keys())}")
            else:
                # Old flat structure - all items are objects
                objects_json = mib_json
                
            export_symbols = self._build_mib_symbols(mib, objects_json, type_registry)
            if export_symbols:
                if mib == "SNMPv2-MIB":
                    sysor_symbols = sorted(
                        k for k in export_symbols if k.startswith("sysOR")
                    )
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
                    self.logger.debug(f"Skipped {skipped} duplicate symbols for {mib}")
                if mib == "SNMPv2-MIB":
                    sysor_filtered = sorted(
                        k for k in filtered_symbols if k.startswith("sysOR")
                    )
                    self.logger.info(
                        "SNMPv2-MIB sysOR symbols after filter: %s",
                        ", ".join(sysor_filtered) if sysor_filtered else "<none>",
                    )

                if filtered_symbols:
                    self.mib_builder.export_symbols(mib, **filtered_symbols)
                    self.logger.info(
                        f"Registered {len(filtered_symbols)} objects for {mib}"
                    )
                else:
                    self.logger.warning(
                        f"All symbols for {mib} are already exported, skipping registration"
                    )
            else:
                self.logger.warning(f"No objects to register for {mib}")
        except Exception as e:
            self.logger.error(f"Error registering MIB {mib}: {e}", exc_info=True)

    def _build_mib_symbols(
        self, mib: str, mib_json: Dict[str, Any], type_registry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build all symbols for a MIB (scalars and tables) as a dictionary."""
        export_symbols = {}

        # Identify table-related objects
        table_related_objects = self._find_table_related_objects(mib_json)

        # Register scalars (skip table-related objects)
        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue

            if name in table_related_objects:
                continue

            access = info.get("access")
            if access in ["not-accessible", "accessible-for-notify"]:
                continue

            oid = info.get("oid")
            oid_value = tuple(oid) if isinstance(oid, list) else ()
            if not oid_value:
                continue

            value = info.get("current") if "current" in info else info.get("initial")
            type_name = info.get("type")
            type_info = type_registry.get(type_name, {}) if type_name else {}
            base_type_raw = type_info.get("base_type") or type_name

            if not base_type_raw or not isinstance(base_type_raw, str):
                self.logger.warning(f"Skipping {name}: invalid type '{type_name}'")
                continue

            # Prefer the explicit type name when it maps to a concrete SNMP type (e.g., Counter32)
            # Include TEXTUAL-CONVENTIONs that have type encoders registered
            preferred_snmp_types = {
                "Counter32",
                "Counter64",
                "Gauge32",
                "Unsigned32",
                "Integer32",
                "TimeTicks",
                "DisplayString",
                "OctetString",
                "DateAndTime",  # TEXTUAL-CONVENTION with type encoder
            }
            snmp_type_name = (
                type_name if type_name in preferred_snmp_types else base_type_raw
            )
            base_type = snmp_type_name

            # Special handling for sysUpTime
            if name == "sysUpTime":
                uptime_seconds = time.time() - self.start_time
                value = int(uptime_seconds * 100)

            # Decode value if it's in encoded format
            value = self._decode_value(value)

            # Apply type converter if one is registered (plugin system)
            value = encode_value(value, base_type)

            # Handle None values with defaults
            if value is None:
                if base_type in [
                    "Integer32",
                    "Integer",
                    "Gauge32",
                    "Counter32",
                    "Counter64",
                    "TimeTicks",
                    "Unsigned32",
                ]:
                    value = 0
                elif base_type in ["OctetString", "DisplayString"]:
                    value = ""
                elif base_type == "ObjectIdentifier":
                    value = "0.0"
                else:
                    self.logger.warning(
                        f"Skipping {name}: no value and no default for type '{base_type}'"
                    )
                    continue

            # Get SNMP type class
            try:
                pysnmp_type = self._get_pysnmp_type(snmp_type_name)
                if pysnmp_type is None:
                    raise ImportError(f"Could not resolve type '{snmp_type_name}'")

                # Create scalar instance
                scalar_inst = self.MibScalarInstance(
                    oid_value, (0,), pysnmp_type(value)
                )

                # Set max access based on schema access field
                access_map = {
                    "read-only": "readonly",
                    "read-write": "readwrite",
                    "read-create": "readcreate",
                    "not-accessible": "noaccess",
                    "accessible-for-notify": "notify",
                }
                max_access = access_map.get(access or "read-only", "readonly")
                scalar_inst.setMaxAccess(max_access)
                is_writable = max_access in ("readwrite", "readcreate")

                # Special handling for sysUpTime: make it dynamic
                if name == "sysUpTime":
                    original_read_get = getattr(scalar_inst, "readGet", None)
                    registrar_start_time = self.start_time

                    def _sysuptime_read_get(
                        inst: Any,
                        *args: Any,
                        _start_time: float = registrar_start_time,
                        _pysnmp_type: Any = pysnmp_type,
                        **kwargs: Any,
                    ) -> Any:
                        # Calculate current uptime
                        uptime_seconds = time.time() - _start_time
                        uptime_centiseconds = int(uptime_seconds * 100)
                        # Update the instance's syntax with the current value
                        inst.syntax = _pysnmp_type(uptime_centiseconds)
                        # Call original readGet if it exists
                        if original_read_get:
                            return original_read_get(*args, **kwargs)
                        return inst.syntax

                    scalar_inst.readGet = types.MethodType(_sysuptime_read_get, scalar_inst)

                export_symbols[f"{name}Inst"] = scalar_inst
                # Attach a small write-commit wrapper so network-originated SNMP SETs
                # are surfaced immediately in the agent logs. pysnmp will call
                # instance.writeCommit(...) during Set processing; we wrap any
                # existing implementation and then emit an INFO log with the
                # dotted OID and friendly MIB:symbol name.
                try:
                    registrar_logger = self.logger
                    try:
                        dotted = ".".join(str(x) for x in scalar_inst.name)
                    except Exception:
                        dotted = ".".join(str(x) for x in oid_value + (0,))
                    friendly = f"{mib}:{name}"
                    original_write = getattr(scalar_inst, "writeCommit", None)

                    def _write_commit_wrapper(
                        inst: Any,
                        *a: Any,
                        _dotted: str = dotted,
                        _friendly: str = friendly,
                        _is_writable: bool = is_writable,
                        _logger: logging.Logger = registrar_logger,
                        **kw: Any,
                    ) -> None:
                        # Call original if present (don't prevent normal behavior)
                        try:
                            if original_write:
                                original_write(*a, **kw)
                        except Exception:
                            pass
                        try:
                            if not _is_writable:
                                _logger.debug(
                                    "Ignoring SET on read-only scalar %s (%s)",
                                    _dotted,
                                    _friendly,
                                )
                                return
                            def _format_value(val: Any) -> str:
                                if val is None:
                                    return "<none>"
                                try:
                                    if hasattr(val, "prettyPrint"):
                                        text = val.prettyPrint()
                                    else:
                                        text = str(val)
                                except Exception:
                                    text = None
                                if not text:
                                    try:
                                        if hasattr(val, "asOctets"):
                                            octs = val.asOctets()
                                            text = (
                                                octs.decode("utf-8", errors="replace")
                                                if octs
                                                else "<empty-octets>"
                                            )
                                        elif hasattr(val, "asNumbers"):
                                            text = str(val.asNumbers())
                                        elif isinstance(val, (bytes, bytearray)):
                                            text = val.decode("utf-8", errors="replace") or "<empty-bytes>"
                                        else:
                                            text = repr(val)
                                    except Exception:
                                        text = repr(val)
                                return text if text else "<empty>"

                            def _serialize_value(val: Any) -> object:
                                try:
                                    if val is None:
                                        return None
                                    if isinstance(val, (int, float, bool, str)):
                                        return val
                                    if isinstance(val, (bytes, bytearray)):
                                        try:
                                            return val.decode("latin1")
                                        except Exception:
                                            return val.hex()
                                    return str(val)
                                except Exception:
                                    return str(val)

                            old_val = getattr(inst, "syntax", None)
                            var_bind = a[0] if a else None
                            new_val = None
                            vb_oid = None
                            if isinstance(var_bind, tuple) and len(var_bind) == 2:
                                vb_oid, new_val = var_bind

                            if new_val is not None:
                                try:
                                    inst.syntax = new_val
                                except Exception:
                                    pass

                            if vb_oid is not None:
                                try:
                                    vb_oid_tuple = tuple(int(x) for x in vb_oid)
                                except Exception:
                                    vb_oid_tuple = None
                            else:
                                vb_oid_tuple = None

                            final_dotted = _dotted
                            if vb_oid_tuple:
                                final_dotted = ".".join(str(x) for x in vb_oid_tuple)

                            _logger.info(
                                "SNMP SET applied to %s (%s): old=%s new=%s",
                                final_dotted,
                                _friendly,
                                _format_value(old_val),
                                _format_value(getattr(inst, "syntax", None)),
                            )

                            # Note: Persistence is handled by the agent's set_scalar_value() method
                            # which saves to mib_state.json. Direct SNMP SET operations via
                            # pysnmp's writeCommit are not automatically persisted.
                        except Exception:
                            pass

                    # Bind wrapper as method on the instance
                    scalar_inst.writeCommit = types.MethodType(_write_commit_wrapper, scalar_inst)
                    # Also override writeTest to accept any value
                    def _write_test_wrapper(
                        self: Any,
                        varBind: Any,
                        _dotted: str = dotted,
                        _friendly: str = friendly,
                        _is_writable: bool = is_writable,
                        _logger: logging.Logger = registrar_logger,
                        **_context: Any,
                    ) -> None:
                        if not _is_writable:
                            _logger.debug(
                                "Rejecting SET (writeTest) on read-only scalar %s (%s)",
                                _dotted,
                                _friendly,
                            )
                            raise ValueError("notWritable")
                        _logger.debug(f"writeTest called for {varBind}")
                        return None
                    scalar_inst.writeTest = types.MethodType(_write_test_wrapper, scalar_inst)
                except Exception:
                    # Don't fail registration if hooking logging fails
                    pass
                self.logger.debug(
                    f"Added scalar {name} (type {snmp_type_name}, access {max_access}, value type {pysnmp_type.__name__})"
                )
            except Exception as e:
                self.logger.error(f"Error creating scalar {name}: {e}")
                continue

        # Register tables
        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue

            if not (name.endswith("Table") or name.endswith("Entry")):
                continue

            if not name.endswith("Table"):
                continue

            try:
                table_symbols = self._build_table_symbols(
                    mib, name, info, mib_json, type_registry
                )
                export_symbols.update(table_symbols)
            except Exception as e:
                self.logger.error(f"Error building table {name}: {e}", exc_info=True)
                continue

        return export_symbols

    def _expand_index_value_to_oid_components(self, value: Any, index_type: str) -> tuple[int, ...]:
        """Expand an index value into OID components based on its type.
        
        For complex types like IpAddress, this expands them into multiple integers.
        For simple integer types, returns a single-element tuple.
        
        Args:
            value: The index value (could be int, string, etc.)
            index_type: The SNMP type of the index (e.g., "IpAddress", "Integer32")
            
        Returns:
            Tuple of integers representing the OID components
        """
        # Handle IpAddress type - convert "a.b.c.d" to (a, b, c, d)
        if index_type == "IpAddress":
            if isinstance(value, str):
                try:
                    parts = [int(x) for x in value.split(".")]
                    if len(parts) == 4:
                        return tuple(parts)
                except (ValueError, AttributeError):
                    pass
            # Fallback: treat as 0.0.0.0
            return (0, 0, 0, 0)
        
        # Handle OctetString and DisplayString - convert to length-prefixed or just octets
        # For now, we'll use IMPLIED encoding (no length prefix) for string indexes
        elif index_type in ("OctetString", "DisplayString", "PhysAddress"):
            if isinstance(value, str):
                return tuple(ord(c) for c in value)
            elif isinstance(value, bytes):
                return tuple(value)
            elif isinstance(value, int):
                return (value,)
            return ()
        
        # Handle integer types - simple single value
        elif index_type in ("Integer32", "Unsigned32", "Integer", "Gauge32", "Counter32", "TimeTicks"):
            try:
                return (int(value),)
            except (ValueError, TypeError):
                return (0,)
        
        # Default: try to convert to int
        try:
            return (int(value),)
        except (ValueError, TypeError):
            # Last resort: if it's a string, use ASCII values
            if isinstance(value, str):
                return tuple(ord(c) for c in value)
            return (0,)

    def _build_table_symbols(
        self,
        mib: str,
        table_name: str,
        table_info: Dict[str, Any],
        mib_json: Dict[str, Any],
        type_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build symbols for a single table (table, entry, columns, instances)."""
        symbols = {}

        # Get table OID
        table_oid = tuple(table_info.get("oid", []))
        if not table_oid:
            raise ValueError(f"Table {table_name} has no OID")

        # Find entry object (ends with "Entry")
        entry_name = None
        entry_info = None
        entry_oid = None

        for obj_name, obj_info in mib_json.items():
            if isinstance(obj_info, dict) and obj_name.endswith("Entry"):
                obj_table_name = obj_name[:-5]  # Remove "Entry" suffix
                if obj_table_name + "Table" == table_name:
                    entry_name = obj_name
                    entry_info = obj_info
                    entry_oid = tuple(obj_info.get("oid", []))
                    break

        if not entry_name or not entry_oid:
            raise ValueError(f"No entry found for table {table_name}")

        # Create table and entry objects
        table_obj = self.MibTable(table_oid)
        symbols[table_name] = table_obj

        # Get index information from entry
        if not entry_info:
            raise ValueError(f"Entry {entry_name} has no info")

        index_names = entry_info.get("indexes", [])
        if not index_names:
            index_names = [entry_info.get("index")] if entry_info.get("index") else []

        # Create entry with index specs
        index_specs = tuple((0, mib, idx_name) for idx_name in index_names)
        entry_obj = self.MibTableRow(entry_oid).setIndexNames(*index_specs)
        symbols[entry_name] = entry_obj

        # Find and create column objects
        columns_by_name = {}
        for col_name, col_info in mib_json.items():
            if not isinstance(col_info, dict):
                continue

            col_oid = tuple(col_info.get("oid", []))
            if not col_oid or len(col_oid) < len(entry_oid) + 1:
                continue

            # Check if this column belongs to this entry
            if col_oid[: len(entry_oid)] != entry_oid:
                continue

            col_type_name = col_info.get("type")
            if not col_type_name:
                continue

            type_info = type_registry.get(col_type_name, {})
            base_type_raw = type_info.get("base_type") or col_type_name

            # Prefer explicit SNMP type names for table columns (same as scalars)
            # Include TEXTUAL-CONVENTIONs that have type encoders registered
            preferred_snmp_types = {
                "Counter32",
                "Counter64",
                "Gauge32",
                "Unsigned32",
                "Integer32",
                "TimeTicks",
                "DisplayString",
                "OctetString",
                "DateAndTime",  # TEXTUAL-CONVENTION with type encoder
            }
            base_type = (
                col_type_name
                if col_type_name in preferred_snmp_types
                else base_type_raw
            )

            try:
                pysnmp_type = self._get_pysnmp_type(base_type)
                if pysnmp_type is None:
                    continue

                col_access_raw = col_info.get("access", "read-only")
                access_map = {
                    "read-only": "readonly",
                    "read-write": "readwrite",
                    "read-create": "readcreate",
                    "not-accessible": "noaccess",
                    "accessible-for-notify": "notify",
                }
                col_access = access_map.get(col_access_raw, col_access_raw)
                col_obj = self.MibTableColumn(col_oid, pysnmp_type()).setMaxAccess(
                    col_access
                )
                col_is_writable = col_access in ("readwrite", "readcreate")
                symbols[col_name] = col_obj
                # Store writable flag alongside oid and *declared* type so it's available when creating instances
                # Use the declared column type name (col_type_name) for index handling (e.g., IpAddress)
                columns_by_name[col_name] = (col_oid, col_type_name, col_is_writable)
            except Exception as e:
                self.logger.warning(f"Error creating column {col_name}: {e}")
                continue

        # Create row instances
        rows_data = table_info.get("rows", [])
        if not isinstance(rows_data, list):
            rows_data = []

        if table_name == "sysORTable":
            self.logger.info(
                "sysORTable rows=%d index_names=%s columns=%s",
                len(rows_data),
                index_names,
                list(columns_by_name.keys()),
            )

        for row_idx, row_data in enumerate(rows_data):
            if not isinstance(row_data, dict):
                continue

            # Build index tuple from the index column values in row_data
            # For multi-field indexes or complex types like IpAddress, expand properly
            index_components: list[int] = []
            for i, idx_name in enumerate(index_names):
                idx_value = row_data.get(idx_name, row_idx + 1 if i == 0 else 0)
                
                # Get the type of this index column
                idx_type = "Integer32"  # default
                if idx_name in columns_by_name:
                    _, idx_type, _ = columns_by_name[idx_name]

                # Log what we're expanding for diagnostics
                self.logger.info(f"Expanding index: {idx_name} value={idx_value} type={idx_type}")
                # Expand the value into OID components
                components = self._expand_index_value_to_oid_components(idx_value, idx_type)
                self.logger.info(f"Expanded components for {idx_name}: {components}")
                index_components.extend(components)
            
            index_tuple = tuple(index_components)

            if table_name == "sysORTable":
                self.logger.info(
                    "sysORTable row %d raw=%s index_tuple=%s",
                    row_idx,
                    row_data,
                    index_tuple,
                )

            # Create instances for each column
            if "values" in row_data and isinstance(row_data.get("values"), dict):
                row_values = row_data.get("values", {})
            else:
                row_values = row_data

            for col_name, (col_oid, base_type, col_is_writable) in columns_by_name.items():
                # Get value for this cell
                if col_name in row_values:
                    value = row_values[col_name]
                elif col_name in index_names:
                    # Use index value for index columns
                    idx_pos = index_names.index(col_name)
                    value = index_tuple[idx_pos]
                else:
                    continue

                # Decode value if it's in encoded format
                value = self._decode_value(value)

                # Apply type converter if one is registered (plugin system)
                value = encode_value(value, base_type)

                try:
                    pysnmp_type = self._get_pysnmp_type(base_type)
                    if pysnmp_type is None:
                        continue

                    inst = self.MibScalarInstance(
                        col_oid, index_tuple, pysnmp_type(value)
                    )

                    inst_name = f"{col_name}Inst_{'_'.join(map(str, index_tuple))}"
                    symbols[inst_name] = inst

                    try:
                        # Log instance OID for diagnostics
                        try:
                            inst_name_tuple = tuple(inst.name)
                        except Exception:
                            inst_name_tuple = tuple(col_oid + index_tuple)
                        self.logger.info(f"Registered instance {inst_name} -> {inst_name_tuple}")
                    except Exception:
                        pass

                    # Attach writeCommit/writeTest wrappers for table column instances
                    try:
                        registrar_logger = self.logger
                        try:
                            dotted = ".".join(str(x) for x in inst.name)
                        except Exception:
                            dotted = ".".join(str(x) for x in col_oid + index_tuple)
                        friendly = f"{mib}:{col_name}"
                        original_write = getattr(inst, "writeCommit", None)

                        def _write_commit_wrapper(
                            inst_ref: Any,
                            *a: Any,
                            _dotted: str = dotted,
                            _friendly: str = friendly,
                            _is_writable: bool = col_is_writable,
                            _logger: logging.Logger = registrar_logger,
                            **kw: Any,
                        ) -> None:
                            try:
                                if original_write:
                                    original_write(*a, **kw)
                            except Exception:
                                pass
                            try:
                                if not _is_writable:
                                    _logger.debug(
                                        "Ignoring SET on read-only column %s (%s)",
                                        _dotted,
                                        _friendly,
                                    )
                                    return
                                def _format_value(val: Any) -> str:
                                    if val is None:
                                        return "<none>"
                                    try:
                                        if hasattr(val, "prettyPrint"):
                                            text = val.prettyPrint()
                                        else:
                                            text = str(val)
                                    except Exception:
                                        text = None
                                    if not text:
                                        try:
                                            if hasattr(val, "asOctets"):
                                                octs = val.asOctets()
                                                text = (
                                                    octs.decode("utf-8", errors="replace")
                                                    if octs
                                                    else "<empty-octets>"
                                                )
                                            elif hasattr(val, "asNumbers"):
                                                text = str(val.asNumbers())
                                            elif isinstance(val, (bytes, bytearray)):
                                                text = val.decode("utf-8", errors="replace") or "<empty-bytes>"
                                            else:
                                                text = repr(val)
                                        except Exception:
                                            text = repr(val)
                                    return text if text else "<empty>"

                                def _serialize_value(val: Any) -> object:
                                    try:
                                        if val is None:
                                            return None
                                        if isinstance(val, (int, float, bool, str)):
                                            return val
                                        if isinstance(val, (bytes, bytearray)):
                                            try:
                                                return val.decode("latin1")
                                            except Exception:
                                                return val.hex()
                                        return str(val)
                                    except Exception:
                                        return str(val)

                                old_val = getattr(inst_ref, "syntax", None)
                                var_bind = a[0] if a else None
                                new_val = None
                                vb_oid = None
                                if isinstance(var_bind, tuple) and len(var_bind) == 2:
                                    vb_oid, new_val = var_bind

                                if new_val is not None:
                                    try:
                                        inst_ref.syntax = new_val
                                    except Exception:
                                        pass

                                if vb_oid is not None:
                                    try:
                                        vb_oid_tuple = tuple(int(x) for x in vb_oid)
                                    except Exception:
                                        vb_oid_tuple = None
                                else:
                                    vb_oid_tuple = None

                                final_dotted = _dotted
                                if vb_oid_tuple:
                                    final_dotted = ".".join(str(x) for x in vb_oid_tuple)

                                _logger.info(
                                    "SNMP SET applied to %s (%s): old=%s new=%s",
                                    final_dotted,
                                    _friendly,
                                    _format_value(old_val),
                                    _format_value(getattr(inst_ref, "syntax", None)),
                                )

                                # Note: Persistence is handled by the agent's set_scalar_value() method
                                # which saves to mib_state.json. Direct SNMP SET operations via
                                # pysnmp's writeCommit are not automatically persisted.
                            except Exception:
                                pass

                        inst.writeCommit = types.MethodType(_write_commit_wrapper, inst)

                        def _write_test_wrapper(
                            self: Any,
                            varBind: Any,
                            _dotted: str = dotted,
                            _friendly: str = friendly,
                            _col_is_writable: bool = col_is_writable,
                            _logger: logging.Logger = registrar_logger,
                            **context: Any,
                        ) -> None:
                            if not _col_is_writable:
                                _logger.debug(
                                    "Rejecting SET (writeTest) on read-only column %s (%s)",
                                    _dotted,
                                    _friendly,
                                )
                                raise ValueError("notWritable")
                            _logger.debug(f"writeTest called for {varBind}")
                            return None

                        inst.writeTest = types.MethodType(_write_test_wrapper, inst)
                    except Exception:
                        pass

                    if table_name == "sysORTable":
                        self.logger.info(
                            "sysORTable cell %s[%s]=%r (type %s)",
                            col_name,
                            index_tuple,
                            value,
                            pysnmp_type.__name__,
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Error creating instance for {col_name} row {index_tuple}: {e}"
                    )
                    continue

        return symbols

    def _find_table_related_objects(self, mib_json: Dict[str, Any]) -> Set[str]:
        """Find all table-related object names."""
        table_related = set()

        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue

            if name.endswith("Table") or name.endswith("Entry"):
                table_related.add(name)

                # Also mark columns as table-related
                if name.endswith("Entry"):
                    entry_oid = tuple(info.get("oid", []))
                    for col_name, col_info in mib_json.items():
                        if isinstance(col_info, dict):
                            col_oid = tuple(col_info.get("oid", []))
                            if col_oid and len(col_oid) > len(entry_oid):
                                if col_oid[: len(entry_oid)] == entry_oid:
                                    table_related.add(col_name)

        return table_related

    def _decode_value(self, value: Any) -> Any:
        """Decode a value that may be in encoded format.

        Values can be either:
        - Direct values (strings, integers, etc.)
        - Dictionaries with {"value": "...", "encoding": "hex"} format

        Args:
            value: The value to decode (can be any type)

        Returns:
            The decoded value
        """
        # If value is not a dict, return as-is
        if not isinstance(value, dict):
            return value

        # Check if it has the encoded format structure
        if "value" not in value or "encoding" not in value:
            return value

        encoded_value = value["value"]
        encoding = value["encoding"]

        # Handle different encodings
        if encoding == "hex":
            # Decode hex-encoded string (e.g., "\\xAA\\xBB\\xCC")
            # The value is stored as a string with escape sequences
            try:
                # Use encode().decode('unicode_escape') to convert escape sequences
                # Then encode to bytes
                if isinstance(encoded_value, str):
                    # Convert string with \x escape sequences to bytes
                    decoded = (
                        encoded_value.encode("utf-8")
                        .decode("unicode_escape")
                        .encode("latin1")
                    )
                    return decoded
                else:
                    self.logger.warning(
                        f"Hex encoding expects string value, got {type(encoded_value)}"
                    )
                    return encoded_value
            except Exception as e:
                self.logger.error(f"Failed to decode hex value '{encoded_value}': {e}")
                return encoded_value
        else:
            self.logger.warning(f"Unknown encoding '{encoding}', returning raw value")
            return encoded_value

    def _get_pysnmp_type(self, base_type: str) -> Any:
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
        except Exception:
            try:
                return self.mib_builder.import_symbols("SNMPv2-TC", pysnmp_name)[0]
            except Exception:
                from pysnmp.proto import rfc1902

                return getattr(rfc1902, pysnmp_name, None)

