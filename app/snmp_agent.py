"""SNMPAgent: Main orchestrator for the SNMP agent (initial workflow)."""

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
import signal
import sys
import time
from types import FrameType
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TypeAlias, TypedDict, cast

from pysnmp import debug as pysnmp_debug
from pysnmp.entity.engine import SnmpEngine
from pysnmp.entity.rfc3413.context import SnmpContext
from pysnmp.smi.builder import MibBuilder

# Load type converter plugins
import plugins.date_and_time  # noqa: F401  # pylint: disable=unused-import
from app.app_config import AppConfig
from app.app_logger import AppLogger
from app.compiler import MibCompiler
from app.mib_registrar import MibRegistrar, SNMPContext
from app.model_paths import TYPE_REGISTRY_FILE, agent_model_dir, compiled_mibs_dir, mib_state_file
from app.value_links import get_link_manager


@dataclass
class AugmentedTableChild:
    """Represents an augmented table child relationship."""

    table_oid: str
    entry_name: str
    indexes: tuple[str, ...]
    inherited_columns: tuple[str, ...]

    default_columns: dict[str, "JsonValue"]


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
DecodedValue: TypeAlias = JsonValue | bytes | bytearray


class TableInstance(TypedDict, total=False):
    column_values: dict[str, JsonValue]
    index_values: dict[str, JsonValue]


class SNMPAgent:
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
        self.mib_registrar: MibRegistrar | None = None
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
        self._augmented_parents: dict[str, list[AugmentedTableChild]] = {}
        # Default column values for tables (used when auto-creating augmented rows)
        self._table_defaults: dict[str, dict[str, JsonValue]] = {}

        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        import os

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
        try:
            signal.signal(signal.SIGHUP, signal_handler)  # type: ignore[attr-defined]
        except AttributeError:
            pass

    def _shutdown(self) -> None:
        """Perform graceful shutdown of the SNMP agent."""
        import os

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
            import logging

            for handler in logging.getLogger().handlers:
                handler.flush()

            self.logger.info("Shutdown complete")
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError) as e:
            self.logger.exception("Error during shutdown: %s", e)
        finally:
            # Exit cleanly - use os._exit to ensure termination
            os._exit(0)

    def _find_source_mib_file(self, mib_name: str) -> Optional["Path"]:
        """Find the source .mib file for a given MIB name.

        Searches in data/mibs and all its subdirectories.
        Returns the Path to the .mib file if found, None otherwise.
        """
        from pathlib import Path

        mib_data_dir = Path(__file__).resolve().parent.parent / "data" / "mibs"
        if not mib_data_dir.exists():
            return None

        # Iterate all files in the tree looking for a matching module
        for candidate in mib_data_dir.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() in (".mib", ".txt", ".my"):
                try:
                    with candidate.open("r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(2000)
                        if f"{mib_name} DEFINITIONS ::= BEGIN" in content:
                            return candidate
                        if candidate.name.upper().startswith(mib_name.upper()):
                            return candidate
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    continue

        return None

    def _should_recompile(self, mib_name: str, compiled_file: "Path | str") -> bool:
        """Check if a MIB should be recompiled based on timestamp comparison.

        Returns True if:
        - The compiled file doesn't exist, OR
        - The source .mib file is newer than the compiled .py file
        """
        from pathlib import Path

        compiled_path = Path(compiled_file)
        if not compiled_path.exists():
            return True

        source_file = self._find_source_mib_file(mib_name)
        if source_file is None:
            # Can't find source, assume compiled version is fine
            return False

        try:
            source_mtime = source_file.stat().st_mtime
            compiled_mtime = compiled_path.stat().st_mtime

            if source_mtime > compiled_mtime:
                self.logger.info(
                    "Source MIB %s is newer than compiled version, will recompile", source_file
                )
                return True
        except OSError as e:
            self.logger.warning("Error comparing timestamps for %s: %s", mib_name, e)
            return False

        return False

    def _repair_loaded_schema(self, mib: str, schema: dict[str, JsonValue]) -> None:
        """Repair known schema metadata gaps in-place after loading from disk."""
        if mib != "SNMPv2-MIB":
            return

        objects = schema.get("objects") if isinstance(schema.get("objects"), dict) else schema
        if not isinstance(objects, dict):
            return

        sysor_table = objects.get("sysORTable")
        if not isinstance(sysor_table, dict):
            return

        changed = False
        if not sysor_table.get("oid"):
            sysor_table["oid"] = [1, 3, 6, 1, 2, 1, 1, 9]
            changed = True
        if not sysor_table.get("type"):
            sysor_table["type"] = "MibTable"
            changed = True
        if "rows" not in sysor_table or not isinstance(sysor_table.get("rows"), list):
            sysor_table["rows"] = []
            changed = True

        expected_sysor_columns: dict[str, list[int]] = {
            "sysORIndex": [1, 3, 6, 1, 2, 1, 1, 9, 1, 1],
            "sysORID": [1, 3, 6, 1, 2, 1, 1, 9, 1, 2],
            "sysORDescr": [1, 3, 6, 1, 2, 1, 1, 9, 1, 3],
            "sysORUpTime": [1, 3, 6, 1, 2, 1, 1, 9, 1, 4],
        }
        expected_sysor_types: dict[str, str] = {
            "sysORIndex": "Integer32",
            "sysORID": "ObjectIdentifier",
            "sysORDescr": "DisplayString",
            "sysORUpTime": "TimeStamp",
        }
        expected_sysor_access: dict[str, str] = {
            "sysORIndex": "not-accessible",
            "sysORID": "read-only",
            "sysORDescr": "read-only",
            "sysORUpTime": "read-only",
        }

        for col_name, expected_oid in expected_sysor_columns.items():
            col_obj = objects.get(col_name)
            if not isinstance(col_obj, dict):
                objects[col_name] = {
                    "oid": cast(JsonValue, expected_oid),
                    "type": expected_sysor_types[col_name],
                    "access": expected_sysor_access[col_name],
                }
                changed = True
                continue

            oid_value = col_obj.get("oid")
            if oid_value != expected_oid:
                col_obj["oid"] = cast(JsonValue, expected_oid)
                changed = True

            if not col_obj.get("type"):
                col_obj["type"] = expected_sysor_types[col_name]
                changed = True

            if not col_obj.get("access"):
                col_obj["access"] = expected_sysor_access[col_name]
                changed = True

        if changed:
            self.logger.info("Repaired SNMPv2-MIB sysORTable metadata in loaded schema")

    def _validate_snmpv2_core_schema(self, mib: str, schema: dict[str, JsonValue]) -> None:
        """Validate critical SNMPv2-MIB sysOR schema metadata and fail on corruption."""
        if mib != "SNMPv2-MIB":
            return

        objects = schema.get("objects") if isinstance(schema.get("objects"), dict) else schema
        if not isinstance(objects, dict):
            msg = "SNMPv2-MIB schema missing objects container"
            raise TypeError(msg)

        required_columns: dict[str, tuple[list[int], str, str]] = {
            "sysORIndex": ([1, 3, 6, 1, 2, 1, 1, 9, 1, 1], "Integer32", "not-accessible"),
            "sysORID": ([1, 3, 6, 1, 2, 1, 1, 9, 1, 2], "ObjectIdentifier", "read-only"),
            "sysORDescr": ([1, 3, 6, 1, 2, 1, 1, 9, 1, 3], "DisplayString", "read-only"),
            "sysORUpTime": ([1, 3, 6, 1, 2, 1, 1, 9, 1, 4], "TimeStamp", "read-only"),
        }

        for col_name, (expected_oid, expected_type, expected_access) in required_columns.items():
            col_obj = objects.get(col_name)
            if not isinstance(col_obj, dict):
                msg = f"SNMPv2-MIB core column missing or invalid: {col_name}"
                raise TypeError(msg)

            oid_value = col_obj.get("oid")
            if oid_value != expected_oid:
                msg = (
                    f"SNMPv2-MIB {col_name} has malformed OID {oid_value}; "
                    f"expected {expected_oid}"
                )
                raise ValueError(msg)

            type_value = col_obj.get("type")
            if type_value != expected_type:
                msg = (
                    f"SNMPv2-MIB {col_name} has malformed type {type_value}; "
                    f"expected {expected_type}"
                )
                raise ValueError(msg)

            access_value = col_obj.get("access")
            if access_value != expected_access:
                msg = (
                    f"SNMPv2-MIB {col_name} has malformed access {access_value}; "
                    f"expected {expected_access}"
                )
                raise ValueError(msg)

    def run(self) -> None:
        """Compile/load MIB assets, register symbols, and start the SNMP dispatcher."""
        self.logger.info("Starting SNMP Agent setup workflow...")
        # Compile MIBs and generate behavior JSONs as before
        mibs = cast("list[str]", self.app_config.get("mibs", []))
        compiled_dir = compiled_mibs_dir(__file__)
        json_dir = agent_model_dir(__file__)
        json_dir.mkdir(parents=True, exist_ok=True)

        # Build and export the canonical type registry
        from app.type_registry import TypeRegistry

        compiled_mib_paths: list[str] = []
        compiler = MibCompiler(str(compiled_dir), self.app_config)

        # Check if compiled MIBs exist and if source files are newer (timestamp-based recompilation)
        for mib_name in mibs:
            compiled_file = compiled_dir / f"{mib_name}.py"

            if self._should_recompile(mib_name, compiled_file):
                if compiled_file.exists():
                    self.logger.info("Recompiling outdated MIB: %s", mib_name)
                else:
                    self.logger.info("Compiling missing MIB: %s", mib_name)

                try:
                    # Pass just the module name; pysmi will find .mib files by name
                    py_path = compiler.compile(mib_name)
                    compiled_mib_paths.append(py_path)
                    self.logger.info("Compiled %s to %s", mib_name, py_path)
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ) as e:
                    self.logger.exception("Failed to compile %s: %s", mib_name, e)
                    continue
            else:
                compiled_mib_paths.append(str(compiled_file))

        types_json_path = TYPE_REGISTRY_FILE
        if self.preloaded_model and types_json_path.exists():
            self.logger.info(
                "Using preloaded model and existing types.json, skipping full MIB compilation"
            )
            # Load existing type registry; if malformed, rebuild it.
            try:
                with types_json_path.open("r", encoding="utf-8") as f:
                    type_registry_data = json.load(f)
                type_registry = TypeRegistry(Path())  # dummy
                type_registry._registry = type_registry_data
            except json.JSONDecodeError as e:
                self.logger.warning(
                    "Invalid JSON in type registry at %s: %s. Rebuilding types.json.",
                    types_json_path,
                    e,
                )
                type_registry = TypeRegistry(compiled_dir)
                type_registry.build()
                type_registry.export_to_json(str(types_json_path))
                self.logger.info(
                    "Rebuilt type registry to %s with %s types.",
                    types_json_path,
                    len(type_registry.registry),
                )
        else:
            type_registry = TypeRegistry(compiled_dir)
            type_registry.build()
            type_registry.export_to_json(str(types_json_path))
            self.logger.info(
                "Exported type registry to %s with %s types.",
                types_json_path,
                len(type_registry.registry),
            )

        # Validate types
        self.logger.info("Validating type registry...")
        from app.type_registry_validator import validate_type_registry_file

        is_valid, errors, type_count = validate_type_registry_file(str(types_json_path))
        if not is_valid:
            self.logger.error("Type registry validation failed: %s", errors)
            return
        self.logger.info("Type registry validation passed. %s types validated.", type_count)

        if self.preloaded_model:
            self.mib_jsons = self.preloaded_model
            self.logger.info("Using preloaded model for schemas")
        else:
            # Generate schema JSON for each MIB
            from app.generator import BehaviourGenerator

            generator = BehaviourGenerator(str(json_dir))
            # Build a map of MIB name -> compiled Python path
            mib_to_py_path: dict[str, str] = {}
            for mib in mibs:
                py_file = compiled_dir / f"{mib}.py"
                if py_file.exists():
                    mib_to_py_path[mib] = str(py_file)

            # Generate schemas for each MIB that was compiled
            for mib_name, py_path in mib_to_py_path.items():
                self.logger.info("Processing schema for %s: %s", mib_name, py_path)
                try:
                    mib_dir = json_dir / mib_name
                    schema_path = mib_dir / "schema.json"

                    # Check if schema exists and if compiled MIB file is newer than schema
                    force_regen = True
                    if schema_path.exists():
                        schema_mtime = Path(schema_path).stat().st_mtime
                        py_mtime = Path(py_path).stat().st_mtime
                        if py_mtime <= schema_mtime:
                            # Schema is up-to-date, don't regenerate
                            force_regen = False
                            self.logger.info(
                                "%s", f"✓ Schema for {mib_name} is up-to-date "
                                f"(MIB: {py_mtime:.0f}, Schema: {schema_mtime:.0f}). "
                                f"Preserving baked values. To regenerate, use Fresh State."
                            )
                        else:
                            self.logger.info(
                                "Compiled MIB %s is newer than schema, regenerating", mib_name
                            )
                    else:
                        self.logger.info(
                            "Schema does not exist for %s, generating from compiled MIB", mib_name
                        )

                    # Pass the MIB name explicitly and force_regenerate flag
                    generator.generate(py_path, mib_name=mib_name, force_regenerate=force_regen)
                    if force_regen:
                        self.logger.info("Schema JSON generated for %s", mib_name)
                except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                    self.logger.exception(
                        "Failed to generate schema JSON for %s: %s", mib_name, e,
                    )

            # Load schema JSONs for SNMP serving
            # Directory structure: {json_dir}/{MIB_NAME}/schema.json
            invalid_schema_mibs: list[str] = []
            for mib in mibs:
                schema_path = json_dir / mib / "schema.json"
                if not schema_path.exists():
                    continue
                try:
                    with schema_path.open("r", encoding="utf-8") as jf:
                        json.load(jf)
                except json.JSONDecodeError:
                    invalid_schema_mibs.append(mib)

            if invalid_schema_mibs:
                self.logger.warning(
                    "Pre-load schema health check found %d invalid schema file(s): %s",
                    len(invalid_schema_mibs),
                    ", ".join(invalid_schema_mibs),
                )

            for mib in mibs:
                mib_dir = json_dir / mib
                schema_path = mib_dir / "schema.json"

                if schema_path.exists():
                    try:
                        with schema_path.open("r", encoding="utf-8") as jf:
                            self.mib_jsons[mib] = json.load(jf)
                        self._repair_loaded_schema(mib, self.mib_jsons[mib])
                        self._validate_snmpv2_core_schema(mib, self.mib_jsons[mib])
                        self.logger.info("Loaded schema for %s from %s", mib, schema_path)
                    except json.JSONDecodeError as e:
                        self.logger.warning(
                            "Invalid JSON schema for %s at %s: %s",
                            mib,
                            schema_path,
                            e,
                        )

                        regenerated = False
                        regen_py_path = mib_to_py_path.get(mib)
                        if regen_py_path:
                            try:
                                self.logger.info(
                                    "Regenerating schema for %s due to invalid JSON...",
                                    mib,
                                )
                                generator.generate(
                                    regen_py_path,
                                    mib_name=mib,
                                    force_regenerate=True,
                                )
                                with schema_path.open("r", encoding="utf-8") as jf:
                                    self.mib_jsons[mib] = json.load(jf)
                                self._repair_loaded_schema(mib, self.mib_jsons[mib])
                                self._validate_snmpv2_core_schema(mib, self.mib_jsons[mib])
                                self.logger.info(
                                    "Successfully regenerated and loaded schema for %s",
                                    mib,
                                )
                                regenerated = True
                            except (
                                AttributeError,
                                LookupError,
                                OSError,
                                TypeError,
                                ValueError,
                            ) as regen_error:
                                if isinstance(regen_error, ValueError):
                                    raise
                                self.logger.exception(
                                    "Failed to regenerate schema for %s: %s",
                                    mib,
                                    regen_error,
                                )

                        if not regenerated:
                            self.logger.warning(
                                "Skipping schema for %s due to invalid JSON at %s",
                                mib,
                                schema_path,
                            )
                else:
                    self.logger.warning("Schema not found for %s at %s", mib, schema_path)

        for loaded_mib, loaded_schema in self.mib_jsons.items():
            self._validate_snmpv2_core_schema(loaded_mib, loaded_schema)

        self.logger.info(
            "Loaded %d MIB schemas for SNMP serving.",
            len(self.mib_jsons),
        )

        # Load value links from schemas
        link_manager = get_link_manager()
        link_manager.clear()  # Clear any existing links
        for mib_name, schema in self.mib_jsons.items():
            link_manager.load_links_from_schema(schema)

        self.logger.info("Value links loaded from schemas")

        # Build relationships between tables that share indexes via AUGMENTS
        self._build_augmented_index_map()

        # Setup SNMP engine and transport
        self._setup_snmp_engine(str(compiled_dir))
        if self.snmp_engine is not None:
            self._setup_transport()
            self._setup_community()
            self._setup_responders()
            self._register_mib_objects()
            # Capture initial scalar values (for comparison) and apply overrides
            try:
                self._capture_initial_values()
                self._load_mib_state()  # Load unified state (scalars, tables, deletions)
                self._apply_overrides()
                self._apply_table_instances()  # Apply loaded table instance values to MIB cells
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.exception("Error applying overrides: %s", e)
            self._populate_sysor_table()  # Populate sysORTable with actual MIBs
            self.logger.info("SNMP Agent is now listening for SNMP requests.")
            # Block and serve SNMP requests using asyncio dispatcher
            try:
                self.logger.info("Entering SNMP event loop...")
                # Just run the dispatcher - no need for job_started() or open_dispatcher()
                self.snmp_engine.transport_dispatcher.run_dispatcher()
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, shutting down agent")
                self._shutdown()
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.exception("SNMP event loop error: %s", e)
                self._shutdown()
        else:
            self.logger.error("snmp_engine is not initialized. SNMP agent will not start.")

    def _setup_snmp_engine(self, compiled_dir: str) -> None:
        from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
        from pysnmp.entity import engine
        from pysnmp.entity.rfc3413 import context
        from pysnmp.smi import builder as snmp_builder

        self.logger.info("Setting up SNMP engine...")
        self.snmp_engine = engine.SnmpEngine()

        # Register asyncio dispatcher
        dispatcher = AsyncioDispatcher()
        self.snmp_engine.register_transport_dispatcher(dispatcher)

        # Create context and get MIB builder from instrumentation (like working reference)
        self.snmp_context = context.SnmpContext(self.snmp_engine)
        mib_instrum = self.snmp_context.get_mib_instrum()
        self.mib_builder = mib_instrum.get_mib_builder()

        # Ensure compiled MIBs are discoverable and loaded into the builder
        compiled_path = Path(compiled_dir)
        self.mib_builder.add_mib_sources(snmp_builder.DirMibSource(str(compiled_path)))
        compiled_modules = [p.stem for p in compiled_path.glob("*.py")]
        if compiled_modules:
            self.mib_builder.load_modules(*compiled_modules)
            self.logger.info("Loaded compiled MIB modules: %s", ", ".join(sorted(compiled_modules)))
        else:
            self.logger.warning("No compiled MIB modules found to load from %s", compiled_dir)

        # Import MIB classes from SNMPv2-SMI
        (
            MibScalar,
            MibScalarInstance,
            MibTable,
            MibTableRow,
            MibTableColumn,
        ) = self.mib_builder.import_symbols(
            "SNMPv2-SMI",
            "MibScalar",
            "MibScalarInstance",
            "MibTable",
            "MibTableRow",
            "MibTableColumn",
        )

        # Create MIB registrar
        snmp_context = SNMPContext(
            mib_builder=self.mib_builder,
            mib_scalar_instance=MibScalarInstance,
            mib_table=MibTable,
            mib_table_row=MibTableRow,
            mib_table_column=MibTableColumn,
        )
        self.mib_registrar = MibRegistrar(
            snmp_context=snmp_context,
            logger=self.logger,
            start_time=self.start_time,
        )

        self.logger.info("SNMP engine and MIB classes initialized")

    def _setup_transport(self) -> None:
        try:
            from pysnmp.carrier.asyncio.dgram import udp
            from pysnmp.entity import config
        except ImportError as err:
            raise RuntimeError("pysnmp is not installed or not available.") from err
        if self.snmp_engine is None:
            raise RuntimeError("snmp_engine is not initialized.") from None

        # Use UdpAsyncioTransport for asyncio dispatcher
        config.add_transport(
            self.snmp_engine,
            config.SNMP_UDP_DOMAIN,
            udp.UdpAsyncioTransport().open_server_mode((self.host, self.port)),
        )
        self.logger.info("%s", f"Transport opened on {self.host}:{self.port}")

    def _setup_community(self) -> None:
        from pysnmp.entity import config

        if self.snmp_engine is None:
            raise RuntimeError("snmp_engine is not initialized.")

        # Add read-only community "public"
        config.add_v1_system(self.snmp_engine, "public-area", "public")

        # Add read-write community "private"
        config.add_v1_system(self.snmp_engine, "private-area", "private")

        # Add context
        config.add_context(self.snmp_engine, "")

        # Create VACM groups for read-only and read-write access
        config.add_vacm_group(self.snmp_engine, "read-only-group", 2, "public-area")
        config.add_vacm_group(self.snmp_engine, "read-write-group", 2, "private-area")

        # Create VACM views
        # fullView: allows access to all OIDs (include)
        config.add_vacm_view(self.snmp_engine, "fullView", 1, (1,), "")
        # restrictedView: denies access to all OIDs (exclude) - used for write view in read-only
        config.add_vacm_view(self.snmp_engine, "restrictedView", 2, (1,), "")

        # Configure read-only access for "public" community
        config.add_vacm_access(
            self.snmp_engine,
            "read-only-group",
            "",
            2,
            "noAuthNoPriv",
            "prefix",
            "fullView",  # read view (allow all reads)
            "restrictedView",  # write view (deny all writes)
            "fullView",  # notify view
        )

        # Configure read-write access for "private" community
        config.add_vacm_access(
            self.snmp_engine,
            "read-write-group",
            "",
            2,
            "noAuthNoPriv",
            "prefix",
            "fullView",  # read view (allow all reads)
            "fullView",  # write view (allow all writes)
            "fullView",  # notify view
        )

    def _setup_responders(self) -> None:
        from pysnmp.entity.rfc3413 import cmdrsp

        if self.snmp_engine is None:
            raise RuntimeError("snmp_engine is not initialized.")
        if not hasattr(self, "snmp_context") or self.snmp_context is None:
            raise RuntimeError("snmp_context is not initialized.")

        # Use the context created in _setup_snmp_engine
        cmdrsp.GetCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.NextCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.BulkCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.SetCommandResponder(self.snmp_engine, self.snmp_context)

    def _register_mib_objects(self) -> None:
        """Register all MIB objects using the MibRegistrar."""
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Create MibRegistrar lazily if it does not exist (tests may call this directly)
        registrar = getattr(self, "mib_registrar", None)
        if registrar is None:
            try:
                import importlib

                mib_registrar_module = importlib.import_module("app.mib_registrar")

                registrar_cls = mib_registrar_module.MibRegistrar
                snmp_context_cls = getattr(mib_registrar_module, "SNMPContext", None)

                if snmp_context_cls is not None:
                    snmp_context = snmp_context_cls(
                        mib_builder=getattr(self, "mib_builder", None),
                        mib_scalar_instance=getattr(self, "MibScalarInstance", None),
                        mib_table=getattr(self, "MibTable", None),
                        mib_table_row=getattr(self, "MibTableRow", None),
                        mib_table_column=getattr(self, "MibTableColumn", None),
                    )
                    registrar = registrar_cls(
                        snmp_context=snmp_context,
                        logger=self.logger,
                        start_time=self.start_time,
                    )
                else:
                    registrar = registrar_cls(
                        logger=self.logger,
                        start_time=self.start_time,
                    )
                self.mib_registrar = registrar
            except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                self.logger.exception("Failed to create MibRegistrar")
                return

        registrar.register_all_mibs(self.mib_jsons)

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
            import importlib

            mib_registrar_module = importlib.import_module("app.mib_registrar")

            registrar_cls = mib_registrar_module.MibRegistrar
            snmp_context_cls = getattr(mib_registrar_module, "SNMPContext", None)

            if snmp_context_cls is not None:
                snmp_context = snmp_context_cls(
                    mib_builder=None,
                    mib_scalar_instance=None,
                    mib_table=None,
                    mib_table_row=None,
                    mib_table_column=None,
                )
                temp = registrar_cls(
                    snmp_context=snmp_context,
                    logger=self.logger,
                    start_time=self.start_time,
                )
            else:
                temp = registrar_cls(
                    logger=self.logger,
                    start_time=self.start_time,
                )
            decoded = temp._decode_value(value)
            if isinstance(decoded, (str, int, float, bool, list, dict, bytes, bytearray)):
                return cast("DecodedValue", decoded)
            if decoded is None:
                return None
            return value
        except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
            # As a last resort, return the value unchanged
            return value

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

        # Import MibScalarInstance for type checking
        MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[0]

        # Search through all MIB modules and symbols
        for symbols in self.mib_builder.mibSymbols.values():
            for symbol_obj in symbols.values():
                if isinstance(symbol_obj, MibScalarInstance) and symbol_obj.name == oid:
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

        # Import MibScalarInstance for type checking
        MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[0]

        # Search through all MIB modules and symbols
        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                if isinstance(symbol_obj, MibScalarInstance) and symbol_obj.name == oid:
                    # Update in-memory value - must use clone() to preserve pysnmp type
                    try:
                        new_syntax = symbol_obj.syntax.clone(value)
                        symbol_obj.syntax = new_syntax
                    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                        self.logger.error(
                            "%s", f"Failed to update scalar {oid} with value {value!r} "
                            f"(type: {type(value).__name__}): {e}"
                        )

                    # Persist override if different from initial
                    dotted = ".".join(str(x) for x in oid)
                    new_serial = self._serialize_value(symbol_obj.syntax)
                    initial = self._initial_values.get(dotted)
                    # Log the set operation for debugging and info-level visibility
                    try:
                        # INFO so it's visible with default logging configuration
                        mod, sym = self._lookup_symbol_for_dotted(dotted)
                        name = f"{mod}:{sym}" if mod and sym else dotted
                        self.logger.info(
                            "SNMP SET received for %s (%s): initial=%r new=%r",
                            dotted,
                            name,
                            initial,
                            new_serial,
                        )
                        # Also emit a DEBUG-level detailed message
                        self.logger.debug(
                            "(debug) SNMP SET for %s (%s): initial=%r new=%r",
                            dotted,
                            name,
                            initial,
                            new_serial,
                        )
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        pass

                    if initial is None or new_serial != initial:
                        table_cell = self._resolve_table_cell_context(oid)
                        if table_cell is not None:
                            table_oid, instance_str, column_name, index_columns = table_cell
                            table_data = self.table_instances.setdefault(table_oid, {})
                            row_data = table_data.setdefault(instance_str, {"column_values": {}})
                            row_values = row_data.setdefault("column_values", {})
                            row_values[column_name] = new_serial

                            parts = [part for part in instance_str.split(".") if part]
                            if parts and len(index_columns) == len(parts):
                                for idx_name, idx_part in zip(index_columns, parts, strict=True):
                                    if idx_name in row_values:
                                        continue
                                    if idx_part.isdigit():
                                        row_values[idx_name] = int(idx_part)
                                    else:
                                        row_values[idx_name] = idx_part

                            # Table cells are persisted under tables, not scalar overrides.
                            self.overrides.pop(dotted, None)
                        else:
                            self.overrides[dotted] = new_serial

                        try:
                            self._save_mib_state()
                        except (AttributeError, LookupError, OSError, TypeError, ValueError):
                            self.logger.exception("Failed to save MIB state")
                    # If we've reverted to initial, remove any existing override
                    elif dotted in self.overrides:
                        self.overrides.pop(dotted, None)
                        try:
                            self._save_mib_state()
                        except (AttributeError, LookupError, OSError, TypeError, ValueError):
                            self.logger.exception("Failed to save MIB state")

                    return

        raise ValueError(f"Scalar OID {oid} not found")

    def get_all_oids(self) -> dict[str, tuple[int, ...]]:
        """Get all registered OIDs with their names.

        Returns:
            Dict mapping OID names to OID tuples

        """
        if self.mib_builder is None:
            raise RuntimeError("MIB builder not initialized")

        oid_map = {}

        # Iterate through all MIB modules and symbols
        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                # Check if it has a name attribute (OID)
                if hasattr(symbol_obj, "name") and symbol_obj.name:
                    oid_map[symbol_name] = symbol_obj.name

        return oid_map

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

        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                try:
                    if hasattr(symbol_obj, "name") and symbol_obj.name:
                        if tuple(symbol_obj.name) == target_oid:
                            return module_name, symbol_name
                except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                    continue
        return None, None

    # ---- Overrides persistence helpers ----
    def _state_file_path(self) -> str:
        """Return path to unified state file (scalars, tables, deletions)."""
        return str(mib_state_file(__file__))

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

    def _coerce_state_scalars(self, value: JsonValue | None) -> dict[str, JsonValue]:
        """Coerce persisted scalar overrides into dict[str, JsonValue]."""
        if not isinstance(value, dict):
            return {}
        return {str(key): val for key, val in value.items()}

    def _coerce_state_tables(self, value: JsonValue | None) -> dict[str, dict[str, TableInstance]]:
        """Coerce persisted table instance state into typed structure."""
        if not isinstance(value, dict):
            return {}

        tables: dict[str, dict[str, TableInstance]] = {}
        for table_oid, instances_raw in value.items():
            if not isinstance(table_oid, str) or not isinstance(instances_raw, dict):
                continue

            table_instances: dict[str, TableInstance] = {}
            for instance_key, instance_raw in instances_raw.items():
                if not isinstance(instance_key, str) or not isinstance(instance_raw, dict):
                    continue

                entry: TableInstance = {}
                column_values_raw = instance_raw.get("column_values")
                if isinstance(column_values_raw, dict):
                    entry["column_values"] = {
                        str(col_name): col_val
                        for col_name, col_val in column_values_raw.items()
                    }

                index_values_raw = instance_raw.get("index_values")
                if isinstance(index_values_raw, dict):
                    entry["index_values"] = {
                        str(index_name): index_val
                        for index_name, index_val in index_values_raw.items()
                    }

                table_instances[instance_key] = entry

            tables[table_oid] = table_instances

        return tables

    def _load_mib_state(self) -> None:
        """Load unified MIB state (scalars, tables, deletions) from disk."""
        path = Path(self._state_file_path())
        mib_state: dict[str, JsonValue] = {}

        if path.exists():
            try:
                with path.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    mib_state = {
                        str(key): cast("JsonValue", val)
                        for key, val in loaded.items()
                    }
                self.logger.info("Loaded MIB state from %s", path)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.exception("Failed to load MIB state from %s", path)
        else:
            # Try to migrate legacy files (overrides.json and table_instances.json)
            try:
                self._migrate_legacy_state_files()
                if path.exists():
                    with path.open(encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        mib_state = {
                            str(key): cast("JsonValue", val)
                            for key, val in loaded.items()
                        }
                    self.logger.info("Migrated legacy state files to %s", path)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.warning("No legacy state files to migrate: %s", e)

        # Extract scalars (overrides)
        self.overrides = self._coerce_state_scalars(mib_state.get("scalars"))

        # Extract tables
        self.table_instances = self._coerce_state_tables(mib_state.get("tables"))
        self._normalize_loaded_table_instances()
        self._materialize_index_columns()
        self._fill_missing_table_defaults()

        # Extract deleted instances list
        deleted_instances_raw = mib_state.get("deleted_instances")
        if isinstance(deleted_instances_raw, list):
            self.deleted_instances = [oid for oid in deleted_instances_raw if isinstance(oid, str)]
        else:
            self.deleted_instances = []
        self._filter_deleted_instances_against_schema()

        # Extract links (state only) and load into link manager
        try:
            link_manager = get_link_manager()
            links_raw = mib_state.get("links")
            links: list[dict[str, object]] = []
            if isinstance(links_raw, list):
                links = [
                    cast("dict[str, object]", link)
                    for link in links_raw
                    if isinstance(link, dict)
                ]
            link_manager.load_links_from_state(links)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Failed to load link state")

        self.logger.info(
            "%s", f"Loaded state: {len(self.overrides)} scalars, "
            f"{sum(len(v) for v in self.table_instances.values())} table instances, "
            f"{len(self.deleted_instances)} deleted instances"
        )

    def _filter_deleted_instances_against_schema(self) -> None:
        """Drop deleted instances that are not present in schema files."""
        if not self.deleted_instances:
            return

        schema_instance_oids, saw_table = self._collect_schema_instance_oids()
        if not saw_table:
            return

        before = len(self.deleted_instances)
        self.deleted_instances = [
            oid for oid in self.deleted_instances if oid in schema_instance_oids
        ]
        if len(self.deleted_instances) != before:
            self._save_mib_state()
            self.logger.info(
                "Filtered deleted instances against schema: %s -> %s",
                before,
                len(self.deleted_instances),
            )

    def _collect_schema_instance_oids(self) -> tuple[set[str], bool]:
        """Collect all instance OIDs that are defined in schema table rows."""
        instance_oids: set[str] = set()
        if not self.mib_jsons:
            return instance_oids, False

        saw_table = False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            for obj_data in objects.values():
                if obj_data.get("type") != "MibTable":
                    continue

                saw_table = True

                table_oid_list = self._oid_list_parts(obj_data.get("oid"))
                if not table_oid_list:
                    continue
                table_oid = ".".join(str(x) for x in table_oid_list)

                entry_oid_list = [*table_oid_list, 1]
                entry_obj = None
                for other_data in objects.values():
                    if (
                        other_data.get("type") == "MibTableRow"
                        and other_data.get("oid") == entry_oid_list
                    ):
                        entry_obj = other_data
                        break

                if not entry_obj:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))

                columns_meta: dict[str, dict[str, JsonValue]] = {}
                for col_name in index_columns:
                    col_obj = objects.get(col_name)
                    if col_obj is not None:
                        columns_meta[col_name] = col_obj

                rows = obj_data.get("rows", [])
                if not isinstance(rows, list):
                    continue

                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    instance_str = self._build_instance_str_from_row(
                        row, index_columns, columns_meta
                    )
                    if instance_str:
                        instance_oids.add(f"{table_oid}.{instance_str}")

        return instance_oids, saw_table

    def _build_instance_str_from_row(
        self,
        row: dict[str, JsonValue],
        index_columns: list[str],
        columns_meta: dict[str, dict[str, JsonValue]],
    ) -> str:
        """Build a dotted instance string from a schema table row."""
        if not index_columns:
            return "1"
        parts: list[str] = []
        for col_name in index_columns:
            raw_val = row.get(col_name)
            col_type = str(columns_meta.get(col_name, {}).get("type", "")).lower()
            if col_type == "ipaddress":
                if isinstance(raw_val, (list, tuple)):
                    parts.extend(str(v) for v in raw_val)
                else:
                    raw_str = str(raw_val) if raw_val is not None else ""
                    if raw_str:
                        parts.extend(p for p in raw_str.split(".") if p)
                    else:
                        parts.append("")
            else:
                parts.append(str(raw_val) if raw_val is not None else "")
        return ".".join(p for p in parts if p != "")

    def _instance_defined_in_schema(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
    ) -> bool:
        """Return True if a table instance exists in schema rows."""
        if not self.mib_jsons:
            return False

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)

            for obj_data in objects.values():
                if obj_data.get("type") != "MibTable":
                    continue

                table_oid_list = self._oid_list_parts(obj_data.get("oid"))
                if not table_oid_list:
                    continue
                if ".".join(str(x) for x in table_oid_list) != table_oid:
                    continue

                entry_oid_list = [*table_oid_list, 1]
                entry_obj = None
                for other_data in objects.values():
                    if (
                        other_data.get("type") == "MibTableRow"
                        and other_data.get("oid") == entry_oid_list
                    ):
                        entry_obj = other_data
                        break

                if not entry_obj:
                    return False

                index_columns = self._string_list(entry_obj.get("indexes"))

                rows = obj_data.get("rows", [])
                if not isinstance(rows, list):
                    return False

                if not index_columns:
                    return any(isinstance(row, dict) for row in rows)

                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    matches = True
                    for col_name in index_columns:
                        row_val = row.get(col_name)
                        row_val_str = self._format_index_value(row_val)
                        idx_val_str = self._format_index_value(index_values.get(col_name))
                        if row_val_str != idx_val_str:
                            matches = False
                            break
                    if matches:
                        return True

        return False

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
                entry_obj = None
                for other_data in objects.values():
                    if (
                        other_data.get("type") == "MibTableRow"
                        and other_data.get("oid") == entry_oid_list
                    ):
                        entry_obj = other_data
                        break

                if not entry_obj:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))

                rows = obj_data.get("rows", [])
                if not isinstance(rows, list) or not rows:
                    continue

                default_row = rows[0] if isinstance(rows[0], dict) else {}
                if not default_row:
                    continue

                for instance_data in self.table_instances.get(table_oid, {}).values():
                    col_values = instance_data.get("column_values", {})

                    for col_name, default_val in default_row.items():
                        if col_name in index_columns:
                            continue
                        current_val = col_values.get(col_name)
                        if current_val is None or (
                            isinstance(current_val, str) and current_val.strip().lower() == "unset"
                        ):
                            col_values[col_name] = default_val
                            updated = True

        if updated:
            self._save_mib_state()

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
                entry_obj = None
                for other_data in objects.values():
                    if (
                        other_data.get("type") == "MibTableRow"
                        and other_data.get("oid") == entry_oid_list
                    ):
                        entry_obj = other_data
                        break

                if not entry_obj:
                    continue

                index_columns = self._string_list(entry_obj.get("indexes"))
                if not index_columns:
                    continue

                # For each row in this table
                for instance_str, instance_data in self.table_instances.get(table_oid, {}).items():
                    col_values = instance_data.get("column_values", {})

                    # Split instance string into parts
                    parts = [p for p in instance_str.split(".") if p]

                    # Match parts to index columns
                    if len(parts) == len(index_columns):
                        for idx_col_name, idx_part in zip(index_columns, parts, strict=True):
                            # Only set if not already present
                            if idx_col_name not in col_values:
                                # Convert to int if it looks like a number
                                if idx_part.isdigit():
                                    col_values[idx_col_name] = int(idx_part)
                                else:
                                    col_values[idx_col_name] = idx_part
                                updated = True

        if updated:
            self._save_mib_state()

    def _normalize_oid_str(self, oid: str) -> str:
        """Normalize a dotted OID string (remove extra dots/spaces)."""
        cleaned = oid.strip().strip(".")
        if not cleaned:
            return ""
        parts = [part for part in cleaned.split(".") if part]
        return ".".join(parts)

    def _oid_list_to_str(self, oid_list: list[int | str]) -> str:
        """Convert a list-based OID to its dotted string representation."""
        if not oid_list:
            return ""
        return ".".join(str(part) for part in oid_list if part is not None)

    def _parse_index_from_entry(
        self,
        entry: dict[str, JsonValue] | list[JsonValue] | tuple[JsonValue, ...],
    ) -> tuple[str, str] | None:
        """Normalize different formats of index_from metadata."""
        if isinstance(entry, dict):
            mib = entry.get("mib")
            column = entry.get("column")
            if isinstance(mib, str) and isinstance(column, str):
                return mib, column
            return None
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            mib = entry[0]
            column = entry[-1]
            if isinstance(mib, str) and isinstance(column, str):
                return mib, column
        return None

    def _find_entry_name_by_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        entry_oid: tuple[int, ...],
    ) -> str | None:
        """Look up a table entry name by its OID."""
        for name, obj in objects.items():
            if obj.get("type") != "MibTableRow":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid is None:
                continue
            if oid == entry_oid:
                return name
        return None

    def _find_table_name_by_oid(
        self,
        objects: dict[str, dict[str, JsonValue]],
        table_oid: tuple[int, ...],
    ) -> str | None:
        """Look up a table name by OID."""
        for name, obj in objects.items():
            if obj.get("type") != "MibTable":
                continue
            oid = self._oid_tuple(obj.get("oid"))
            if oid is None:
                continue
            if oid == table_oid:
                return name
        return None

    def _find_parent_table_for_column(
        self, module_name: str, column_name: str
    ) -> dict[str, str] | None:
        """Locate the parent table metadata for an inherited column reference."""
        module_schema = self.mib_jsons.get(module_name)
        if not module_schema:
            return None
        objects = self._schema_objects(module_schema)
        column_obj = objects.get(column_name)
        if not isinstance(column_obj, dict):
            return None
        column_oid = self._oid_tuple(column_obj.get("oid"))
        if column_oid is None or len(column_oid) < 2:
            return None

        entry_oid = column_oid[:-1]
        table_oid = entry_oid[:-1]
        table_name = self._find_table_name_by_oid(objects, table_oid)
        if not table_name:
            return None
        entry_name = self._find_entry_name_by_oid(objects, entry_oid)
        return {
            "table_oid": self._oid_list_to_str(list(table_oid)),
            "table_name": table_name,
            "entry_name": entry_name or "",
        }

    def _resolve_table_cell_context(
        self,
        oid: tuple[int, ...],
    ) -> tuple[str, str, str, list[str]] | None:
        """Resolve table metadata for a concrete table cell OID.

        Returns:
            (table_oid_str, instance_str, column_name, index_columns) when OID points to a table cell,
            otherwise None.

        """
        if not self.mib_jsons:
            return None

        for schema in self.mib_jsons.values():
            objects = self._schema_objects(schema)
            if not objects:
                continue

            for obj in objects.values():
                if obj.get("type") != "MibTable":
                    continue

                table_oid = self._oid_tuple(obj.get("oid"))
                if table_oid is None:
                    continue

                if len(oid) <= len(table_oid) + 2:
                    continue
                if oid[: len(table_oid)] != table_oid:
                    continue
                if oid[len(table_oid)] != 1:
                    continue

                entry_oid = table_oid + (1,)
                entry_obj: dict[str, JsonValue] | None = None
                for candidate in objects.values():
                    if candidate.get("type") != "MibTableRow":
                        continue
                    if self._oid_tuple(candidate.get("oid")) == entry_oid:
                        entry_obj = candidate
                        break

                if not entry_obj:
                    continue

                column_id = oid[len(table_oid) + 1]
                column_name: str | None = None
                for candidate_name, candidate in objects.items():
                    col_oid = self._oid_tuple(candidate.get("oid"))
                    if col_oid == entry_oid + (column_id,):
                        column_name = candidate_name
                        break

                if not column_name:
                    continue

                instance_parts = oid[len(table_oid) + 2 :]
                instance_str = ".".join(str(x) for x in instance_parts) if instance_parts else "1"
                index_columns = self._string_list(entry_obj.get("indexes"))
                return self._oid_list_to_str(list(table_oid)), instance_str, column_name, index_columns

        return None

    def _build_augmented_index_map(self) -> None:
        """Build parent -> child mappings for tables that AUGMENT indexes."""
        self._augmented_parents.clear()
        seen_defaults: dict[str, dict[str, JsonValue]] = {}
        table_entries: dict[str, tuple[str, tuple[str, ...]]] = {}

        for module_schema in self.mib_jsons.values():
            objects = self._schema_objects(module_schema)

            # Cache default column values for each table
            for name, table_obj in objects.items():
                if table_obj.get("type") != "MibTable":
                    continue
                table_oid_parts = self._oid_list_parts(table_obj.get("oid"))
                if not table_oid_parts:
                    continue
                table_oid = self._oid_list_to_str(table_oid_parts)
                table_oid_tuple = tuple(table_oid_parts)
                rows = table_obj.get("rows", [])
                if isinstance(rows, list) and rows:
                    first_row = rows[0]
                    if isinstance(first_row, dict):
                        seen_defaults[table_oid] = dict(first_row)

                entry_name = f"{name}Entry"
                entry_obj = objects.get(entry_name)
                if not (entry_obj is not None and entry_obj.get("type") == "MibTableRow"):
                    candidates: list[tuple[str, dict[str, JsonValue]]] = []
                    for cand_name, cand_obj in objects.items():
                        if cand_obj.get("type") != "MibTableRow":
                            continue
                        cand_oid = cand_obj.get("oid", [])
                        if (
                            isinstance(cand_oid, list)
                            and len(cand_oid) > len(table_oid_tuple)
                            and tuple(self._oid_list_parts(cand_oid)[: len(table_oid_tuple)])
                            == table_oid_tuple
                        ):
                            candidates.append((cand_name, cand_obj))
                    if candidates:
                        candidates.sort(
                            key=lambda item: len(self._oid_list_parts(item[1].get("oid")))
                        )
                        entry_name, entry_obj = candidates[0]

                if entry_obj is not None and entry_obj.get("type") == "MibTableRow":
                    indexes = self._string_list(entry_obj.get("indexes"))
                    if indexes:
                        table_entries[table_oid] = (
                            entry_name,
                            tuple(idx for idx in indexes if isinstance(idx, str)),
                        )

            for entry_name, entry_obj in objects.items():
                if entry_obj.get("type") != "MibTableRow":
                    continue
                index_from_raw = entry_obj.get("index_from")
                if not isinstance(index_from_raw, list) or not index_from_raw:
                    continue
                parsed_inherited: list[str] = []
                parent_oids: set[str] = set()
                valid = True

                for inherit in index_from_raw:
                    if not isinstance(inherit, (dict, list, tuple)):
                        valid = False
                        break
                    parsed = self._parse_index_from_entry(inherit)
                    if parsed is None:
                        valid = False
                        break
                    parent_mib, parent_column = parsed
                    parent_info = self._find_parent_table_for_column(parent_mib, parent_column)
                    if not parent_info:
                        valid = False
                        break
                    parent_oids.add(parent_info["table_oid"])
                    parsed_inherited.append(parent_column)

                if not valid or len(parent_oids) != 1:
                    continue

                parent_oid = next(iter(parent_oids))
                entry_oid = self._oid_tuple(entry_obj.get("oid"))
                if entry_oid is None or len(entry_oid) < 1:
                    continue
                child_table_oid = self._oid_list_to_str(list(entry_oid[:-1]))
                indexes = self._string_list(entry_obj.get("indexes"))

                child_meta = AugmentedTableChild(
                    table_oid=child_table_oid,
                    entry_name=entry_name,
                    indexes=tuple(indexes),
                    inherited_columns=tuple(parsed_inherited),
                    default_columns=dict(seen_defaults.get(child_table_oid, {})),
                )
                self._augmented_parents.setdefault(parent_oid, []).append(child_meta)

        for table_oid, (entry_name, indexes_tuple) in table_entries.items():
            if table_oid in self._augmented_parents:
                continue
            if len(indexes_tuple) != 1:
                continue

            defaults = dict(seen_defaults.get(table_oid, {}))
            non_index_cols = [name for name in defaults if name not in indexes_tuple]
            synthetic_children = 2 if non_index_cols else 1

            for _ in range(synthetic_children):
                self._augmented_parents.setdefault(table_oid, []).append(
                    AugmentedTableChild(
                        table_oid=table_oid,
                        entry_name=entry_name,
                        indexes=indexes_tuple,
                        inherited_columns=indexes_tuple,
                        default_columns={},
                    )
                )

        self._table_defaults = seen_defaults

    def _propagate_augmented_tables(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        """Create matching rows for tables that AUGMENT the given table."""
        children = self._augmented_parents.get(table_oid, [])
        if not children:
            return

        for child in children:
            if child.table_oid in visited:
                continue
            if not child.table_oid:
                continue
            if child.indexes != child.inherited_columns:
                continue
            if (
                child.table_oid in self.table_instances
                and index_str in self.table_instances[child.table_oid]
            ):
                continue

            child_defaults = dict(child.default_columns) if child.default_columns else {}
            next_visited = set(visited)
            next_visited.add(child.table_oid)

            try:
                self.add_table_instance(
                    child.table_oid,
                    dict(index_values),
                    column_values=child_defaults,
                    propagate_augments=True,
                    _augment_path=next_visited,
                )
                self.logger.debug(
                    "Auto-created augmented row %s.%s from %s",
                    child.table_oid,
                    index_str,
                    table_oid,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
                self.logger.exception(
                    "Failed to add augmented row for %s: %s",
                    child.table_oid,
                    exc,
                )

    def _propagate_augmented_deletions(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        index_str: str,
        visited: set[str],
    ) -> None:
        """Delete matching rows for tables that AUGMENT the given table."""
        children = self._augmented_parents.get(table_oid, [])
        if not children:
            return

        for child in children:
            if child.table_oid in visited:
                continue
            if not child.table_oid:
                continue
            if child.indexes != child.inherited_columns:
                continue
            if child.table_oid not in self.table_instances:
                continue
            if index_str not in self.table_instances[child.table_oid]:
                continue

            next_visited = set(visited)
            next_visited.add(child.table_oid)

            try:
                self.delete_table_instance(
                    child.table_oid,
                    dict(index_values),
                    propagate_augments=True,
                    _augment_path=next_visited,
                )
                self.logger.debug(
                    "Auto-deleted augmented row %s.%s from %s",
                    child.table_oid,
                    index_str,
                    table_oid,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
                self.logger.exception(
                    "Failed to delete augmented row for %s: %s",
                    child.table_oid,
                    exc,
                )

    def _format_index_value(self, value: JsonValue) -> str:
        """Normalize index values to a dotted string for comparison."""
        if isinstance(value, (list, tuple)):
            return ".".join(str(v) for v in value)
        if value is None:
            return ""
        return str(value)

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
            self._save_mib_state()

    def _save_mib_state(self) -> None:
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

    def _create_missing_cell_instance(
        self,
        column_name: str,
        cell_oid: tuple[int, ...],
        value: JsonValue,
    ) -> bool:
        """Create a missing MibScalarInstance for a table cell if needed.

        This is called when loading state with instances that weren't in the
        original schema. We need to create the MibScalarInstance objects so
        pysnmp can find them during queries.

        Args:
            column_name: The column name (e.g., "ifDescr")
            cell_oid: The full cell OID as tuple (e.g., (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2))
            value: The value to set for this cell

        Returns:
            True if instance was created or already existed, False on error

        """
        if self.mib_builder is None:
            return False

        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[
                0
            ]
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.debug("Could not import MibScalarInstance: %s", e)
            return False

        # Check if instance already exists
        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_obj in symbols.values():
                if isinstance(symbol_obj, MibScalarInstance) and symbol_obj.name == cell_oid:
                    return True  # Already exists

        # Find an existing MibScalarInstance for the same column (different index)
        # to use as a template for the type
        template_instance = None
        target_module = None
        column_oid = None
        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                if (
                    isinstance(symbol_obj, MibScalarInstance)
                    and symbol_name.startswith(f"{column_name}Inst_")
                ):
                    # Found an existing instance for this column
                    template_instance = symbol_obj
                    target_module = module_name
                    if hasattr(symbol_obj, "name") and isinstance(symbol_obj.name, tuple):
                        # Derive column OID from concrete cell OID by removing
                        # the current instance suffix from template symbol name.
                        # Works for single- and multi-component indices.
                        current_name = symbol_obj.name
                        suffix = "Inst_"
                        current_index_str = symbol_name.split(suffix, 1)[1] if suffix in symbol_name else ""
                        current_index_len = len([p for p in current_index_str.split("_") if p])
                        if 0 < current_index_len < len(current_name):
                            column_oid = current_name[:-current_index_len]
                        else:
                            column_oid = current_name[:-1]
                    break
            if template_instance:
                break

        if not template_instance or not target_module or not column_oid:
            self.logger.debug(
                "Could not find template instance for column %s to determine type",
                column_name,
            )
            return False

        try:
            # Clone the syntax from the template instance
            new_syntax = template_instance.syntax.clone(value)
            # Extract the index tuple from the cell_oid by removing the column OID prefix
            index_tuple = cell_oid[len(column_oid) :]
            # Create instance with proper arguments: (col_oid, index_tuple, syntax)
            new_instance = MibScalarInstance(column_oid, index_tuple, new_syntax)

            # Generate a unique instance name and export
            instance_name = f"{column_name}Inst_{'_'.join(str(x) for x in index_tuple)}"
            self.mib_builder.mibSymbols[target_module][instance_name] = new_instance
            self.logger.info(
                "Created missing MibScalarInstance %s for %s = %s",
                cell_oid,
                column_name,
                value,
            )
            return True

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.debug(
                "Failed to create MibScalarInstance for %s: %s",
                cell_oid,
                e,
            )
            return False

    def _update_table_cell_values(
        self,
        table_oid: str,
        instance_str: str,
        column_values: dict[str, JsonValue],
        _processed: set[str] | None = None,
    ) -> None:
        """Update the MibScalarInstance objects for table cell values.

        Args:
            table_oid: The table OID (e.g., "1.3.6.1.4.1.99998.1.4")
            instance_str: The instance index as string (e.g., "1")
            column_values: Dict mapping column names to values
            _processed: Internal set of columns already processed in this update session

        """
        if self.mib_builder is None:
            return

        # Initialize processed set for top-level call
        if _processed is None:
            _processed = set()

        # Import MibScalarInstance for type checking
        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[
                0
            ]
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.error("Failed to import MibScalarInstance: %s", e)
            return

        # Parse table OID
        table_parts = tuple(int(x) for x in table_oid.split("."))
        entry_oid = table_parts + (1,)  # Entry is table + .1

        # Parse instance string to tuple
        instance_parts = tuple(int(x) for x in instance_str.split("."))

        # Get link manager for propagating linked values
        link_manager = get_link_manager()
        instance_key = f"{table_oid}:{instance_str}"

        # For each column value, find and update the corresponding MibScalarInstance
        for column_name, value in column_values.items():
            processed_key = f"{table_oid}:{column_name}"
            # Skip if already processed in this update session
            if processed_key in _processed:
                self.logger.debug(
                    "Skipping %s in %s (already processed via propagation)", column_name, table_oid
                )
                continue

            # Check if we should propagate this update to linked columns
            if not link_manager.should_propagate(column_name, instance_key):
                self.logger.debug("Skipping propagation for %s (already updating)", column_name)
                continue

            try:
                # Mark that we're updating this column (prevents infinite loops)
                link_manager.begin_update(column_name, instance_key)

                # Mark as processed in this update session
                _processed.add(processed_key)

                # Convert unhashable types (list, dict) to strings for storage
                if isinstance(value, (list, dict)):
                    self.logger.debug(
                        "%s", f"Converting {type(value).__name__} to string "
                        f"for column {column_name}: {value}"
                    )
                    if isinstance(value, list):
                        # Convert list to dot-notation OID string
                        value = ".".join(str(x) for x in value)
                    elif isinstance(value, dict):
                        # Convert dict to string representation
                        value = str(value)

                # Keep table_instances in sync for API reads
                stored = False
                if (
                    table_oid in self.table_instances
                    and instance_str in self.table_instances[table_oid]
                ):
                    self.table_instances[table_oid][instance_str].setdefault("column_values", {})[
                        column_name
                    ] = value
                    stored = True

                # Search through MIB symbols to find the column by name
                column_oid = None
                for module_name, symbols in self.mib_builder.mibSymbols.items():
                    if column_name in symbols:
                        col_obj = symbols[column_name]
                        if hasattr(col_obj, "name") and isinstance(col_obj.name, tuple):
                            # Check if this column belongs to our table (starts with entry_oid)
                            if (
                                len(col_obj.name) > len(entry_oid)
                                and col_obj.name[: len(entry_oid)] == entry_oid
                            ):
                                column_oid = col_obj.name
                                break

                if not column_oid:
                    self.logger.debug("Could not find column OID for %s", column_name)
                    continue

                # Build the full cell OID: column_oid + instance_parts
                cell_oid = column_oid + instance_parts

                # Find and update the MibScalarInstance for this cell
                updated = False
                for module_name, symbols in self.mib_builder.mibSymbols.items():
                    for symbol_name, symbol_obj in symbols.items():
                        if (
                            isinstance(symbol_obj, MibScalarInstance)
                            and symbol_obj.name == cell_oid
                        ):
                            # Update the value - must always use proper pysnmp type object
                            try:
                                # Clone the existing syntax object to preserve type constraints
                                new_syntax = symbol_obj.syntax.clone(value)
                                symbol_obj.syntax = new_syntax
                                self.logger.debug(
                                    "Updated MibScalarInstance %s = %s",
                                    cell_oid,
                                    value,
                                )
                                updated = True
                            except (
                                AttributeError,
                                LookupError,
                                OSError,
                                TypeError,
                                ValueError,
                            ) as e:
                                self.logger.error(
                                    "Failed to update MibScalarInstance %s with value %r "
                                    "(type: %s): %s",
                                    cell_oid,
                                    value,
                                    type(value).__name__,
                                    e,
                                )
                            break

                # If not found, try to create a missing instance
                # (for instances loaded from state that weren't in the schema)
                if not updated:
                    if self._create_missing_cell_instance(column_name, cell_oid, value):
                        updated = True
                        self.logger.info(
                            "Created missing MibScalarInstance for %s",
                            cell_oid,
                        )

                # If update succeeded or we stored in table_instances, propagate to linked columns
                if updated or stored:
                    linked_targets = link_manager.get_linked_targets(column_name, table_oid)
                    if linked_targets:
                        targets_display = [f"{t.table_oid}:{t.column_name}" for t in linked_targets]
                        self.logger.info(
                            "Propagating value from %s to linked columns: %s",
                            column_name,
                            targets_display,
                        )
                        for target in linked_targets:
                            target_table = target.table_oid or table_oid
                            linked_values: dict[str, JsonValue] = {target.column_name: value}
                            self._update_table_cell_values(
                                target_table,
                                instance_str,
                                linked_values,
                                _processed,
                            )

            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.exception("Error updating column %s: %s", column_name, e)
            finally:
                # Always clear the update marker
                link_manager.end_update(column_name, instance_key)

    def add_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        column_values: dict[str, JsonValue] | None = None,
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> str:
        """Add a new table instance and persist it, optionally propagating augment tables.

        Args:
            table_oid: The OID of the table (e.g., "1.3.6.1.4.1.99998.1.3.1")
            index_values: Dict mapping index column names to values
            column_values: Optional dict mapping column names to values
            propagate_augments: Whether to create matching rows for AUGMENTS tables
            _augment_path: Internal set used to avoid cycles during propagation

        Returns:
            The instance OID as a string

        """
        if column_values is None:
            column_values = {}

        # Serialize any unhashable types in column_values
        serialized_column_values: dict[str, JsonValue] = {}
        for col_name, col_value in column_values.items():
            if isinstance(col_value, list):
                # Convert list to dot-notation string (for OIDs)
                serialized_column_values[col_name] = ".".join(str(x) for x in col_value)
            elif isinstance(col_value, dict):
                # Convert dict to string
                serialized_column_values[col_name] = str(col_value)
            else:
                serialized_column_values[col_name] = col_value

        table_oid = self._normalize_oid_str(table_oid)

        # Create an instance key from index values
        index_str = self._build_index_str(index_values)
        instance_oid = f"{table_oid}.{index_str}"

        # Store the instance
        if table_oid not in self.table_instances:
            self.table_instances[table_oid] = {}

        self.table_instances[table_oid][index_str] = {"column_values": serialized_column_values}

        # Remove from deleted list if it was previously deleted
        if instance_oid in self.deleted_instances:
            self.deleted_instances.remove(instance_oid)

        # Update the actual MibScalarInstance objects for each column value
        self._update_table_cell_values(table_oid, index_str, serialized_column_values)

        # Persist to unified state file
        self._save_mib_state()

        self.logger.info("Added table instance: %s", instance_oid)

        if propagate_augments:
            visited = set(_augment_path) if _augment_path else set()
            if table_oid not in visited:
                visited.add(table_oid)
                self._propagate_augmented_tables(
                    table_oid,
                    dict(index_values),
                    index_str,
                    visited,
                )
        return instance_oid

    def _build_index_str(self, index_values: dict[str, JsonValue]) -> str:
        """Build an instance index string, supporting implied/faux indices and multi-part indexes.

        Supports:
        - __index__: "5" → "5"
        - __index__, __index_2__: builds "5.10" from parts
        - Regular index columns: joins all values with dots
        """
        if not index_values:
            return "1"

        # Handle multi-part __index__ values (__index__, __index_2__, __index_3__, etc.)
        index_parts = []
        i = 1
        while True:
            key = "__index__" if i == 1 else f"__index_{i}__"
            if key in index_values:
                index_parts.append(str(index_values[key]))
                i += 1
            else:
                break

        if index_parts:
            return ".".join(index_parts)

        # Legacy single __instance__ support
        if "__instance__" in index_values:
            return str(index_values["__instance__"])

        # Regular index columns
        return ".".join(str(v) for v in index_values.values())

    def delete_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        propagate_augments: bool = True,
        _augment_path: set[str] | None = None,
    ) -> bool:
        """Mark a table instance as deleted and optionally cascade to AUGMENTS children."""
        table_oid = self._normalize_oid_str(table_oid)
        index_str = self._build_index_str(index_values)
        instance_oid = f"{table_oid}.{index_str}"

        # Remove from active dynamic instances if it exists
        if table_oid in self.table_instances and index_str in self.table_instances[table_oid]:
            del self.table_instances[table_oid][index_str]

            # Cleanup empty table entry
            if not self.table_instances[table_oid]:
                del self.table_instances[table_oid]

        # Track deletion only when the instance exists in schema rows
        if self._instance_defined_in_schema(table_oid, index_values):
            if instance_oid not in self.deleted_instances:
                self.deleted_instances.append(instance_oid)
                self._save_mib_state()
                self.logger.info("Deleted table instance: %s", instance_oid)
        else:
            self.logger.info("Skipping deleted_instances for %s (not in schema rows)", instance_oid)

        if propagate_augments:
            visited = set(_augment_path) if _augment_path else set()
            if table_oid not in visited:
                visited.add(table_oid)
                self._propagate_augmented_deletions(
                    table_oid,
                    dict(index_values),
                    index_str,
                    visited,
                )

        return True

    def restore_table_instance(
        self,
        table_oid: str,
        index_values: dict[str, JsonValue],
        column_values: dict[str, JsonValue] | None = None,
    ) -> bool:
        """Restore a previously deleted table instance.

        Args:
            table_oid: The OID of the table
            index_values: Dict mapping index column names to values
            column_values: Optional dict mapping column names to values

        Returns:
            True if instance was restored

        """
        instance_oid = f"{table_oid}.{self._build_index_str(index_values)}"

        if instance_oid in self.deleted_instances:
            # Re-add the instance
            self.add_table_instance(table_oid, index_values, column_values or {})
            return True

        return False

    def _serialize_value(self, value: DecodedValue) -> JsonValue:
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
        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[
                0
            ]
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                try:
                    if (
                        isinstance(symbol_obj, MibScalarInstance)
                        and hasattr(symbol_obj, "name")
                        and symbol_obj.name
                    ):
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
                                # Fallback to inspecting symbol object if it exposes access
                                access = None
                                if hasattr(symbol_obj, "getMaxAccess"):
                                    access = symbol_obj.getMaxAccess()
                                elif hasattr(symbol_obj, "maxAccess"):
                                    access = symbol_obj.maxAccess
                                if access and str(access).lower().startswith("readwrite"):
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
        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[
                0
            ]
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return

        removed_invalid: list[str] = []

        for dotted, stored in list(self.overrides.items()):
            try:
                oid = tuple(int(x) for x in dotted.split("."))
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.warning("Invalid OID in overrides: %s", dotted)
                removed_invalid.append(dotted)
                continue

            applied = False
            # We'll attempt the literal OID, and if not found and the OID does not
            # already end with an instance (i.e. last component != 0), try appending .0
            candidate_oids = [oid]
            try:
                if oid[-1] != 0:
                    candidate_oids.append(oid + (0,))
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
            for module_name, symbols in self.mib_builder.mibSymbols.items():
                for symbol_name, symbol_obj in symbols.items():
                    try:
                        if (
                            isinstance(symbol_obj, MibScalarInstance)
                            and tuple(symbol_obj.name) in candidate_oids
                        ):
                            # Update value using clone() to preserve pysnmp type
                            try:
                                new_syntax = symbol_obj.syntax.clone(stored)
                                symbol_obj.syntax = new_syntax
                            except (
                                AttributeError,
                                LookupError,
                                OSError,
                                TypeError,
                                ValueError,
                            ) as e:
                                self.logger.warning(
                                    "%s", f"Failed to apply override for {dotted} "
                                    f"with value {stored!r}: {e}"
                                )
                                continue

                            applied = True
                            break
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        continue
                if applied:
                    break

            if not applied:
                # No matching scalar instance found; mark for removal
                self.logger.warning(
                    "Override for %s found, but no matching scalar instance to apply", dotted
                )
                removed_invalid.append(dotted)

        # Remove any invalid overrides that could not be applied
        if removed_invalid:
            for k in removed_invalid:
                self.overrides.pop(k, None)
            try:
                self._save_mib_state()
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
                    self._update_table_cell_values(table_oid, instance_str, column_values)
                    self.logger.debug("Applied table instance %s.%s", table_oid, instance_str)


if __name__ == "__main__":  # pragma: no cover
    try:
        agent = SNMPAgent()
        agent.run()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        import traceback

        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
