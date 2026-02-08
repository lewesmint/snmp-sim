"""
SNMPAgent: Main orchestrator for the SNMP agent (initial workflow).
"""

from typing import cast
from app.app_logger import AppLogger
from app.app_config import AppConfig
from app.compiler import MibCompiler
from app.mib_registrar import MibRegistrar
import os
import signal
import sys
from pathlib import Path
import json
import time
from typing import Any, Dict, Optional
from pysnmp import debug as pysnmp_debug

# Load type converter plugins
import plugins.date_and_time  # noqa: F401 - registers the converter


class SNMPAgent:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 11161,
        config_path: str = "agent_config.yaml",
        preloaded_model: Optional[Dict[str, Dict[str, Any]]] = None,
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
        self.snmpEngine: Optional[Any] = None
        self.snmpContext: Optional[Any] = None
        # self.mib_builder: Optional[Any] = None
        self.mib_jsons: Dict[str, Dict[str, Any]] = {}
        # Track agent start time for sysUpTime
        self.start_time = time.time()
        self.preloaded_model = preloaded_model
        self._shutdown_requested = False
        # Overrides: dotted OID -> JSON-serializable value
        self.overrides: dict[str, object] = {}
        # Map of initial values captured after registration: dotted OID -> JSON-serializable value
        self._initial_values: dict[str, object] = {}
        # Set of dotted OIDs that are writable (read-write)
        self._writable_oids: set[str] = set()

        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        import os

        def signal_handler(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            self.logger.info(
                f"Received signal {sig_name} ({signum}), terminating immediately..."
            )
            # Force immediate exit - don't wait for event loop
            os._exit(0)

        # Register handlers for common termination signals
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # On Unix systems, also handle SIGHUP
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal_handler)

    def _shutdown(self) -> None:
        """Perform graceful shutdown of the SNMP agent."""
        import os
        self.logger.info("Starting graceful shutdown...")

        try:
            if self.snmpEngine is not None:
                self.logger.info("Closing SNMP transport dispatcher...")
                # Close the dispatcher to stop accepting new requests
                if hasattr(self.snmpEngine, "transport_dispatcher"):
                    dispatcher = self.snmpEngine.transport_dispatcher
                    dispatcher.close_dispatcher()
                    self.logger.info("Transport dispatcher closed successfully")

            # Flush and close log handlers
            self.logger.info("Flushing log handlers...")
            import logging

            for handler in logging.getLogger().handlers:
                handler.flush()

            self.logger.info("Shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
        finally:
            # Exit cleanly - use os._exit to ensure termination
            os._exit(0)

    def run(self) -> None:
        self.logger.info("Starting SNMP Agent setup workflow...")
        # Compile MIBs and generate behavior JSONs as before
        mibs = cast(list[str], self.app_config.get("mibs", []))
        compiled_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "compiled-mibs")
        )
        json_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "mock-behaviour")
        )
        os.makedirs(json_dir, exist_ok=True)

        # Build and export the canonical type registry
        from app.type_registry import TypeRegistry

        compiled_mib_paths: list[str] = []
        compiler = MibCompiler(compiled_dir, self.app_config)
        
        # Always check if compiled MIBs exist; compile any missing ones
        for mib_name in mibs:
            compiled_file = os.path.join(compiled_dir, f"{mib_name}.py")
            if not os.path.exists(compiled_file):
                self.logger.info(f"Compiling missing MIB: {mib_name}")
                try:
                    # Pass just the module name; pysmi will find .mib files by name
                    py_path = compiler.compile(mib_name)
                    compiled_mib_paths.append(py_path)
                    self.logger.info(f"Compiled {mib_name} to {py_path}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to compile {mib_name}: {e}", exc_info=True
                    )
                    continue
            else:
                compiled_mib_paths.append(compiled_file)
        
        if self.preloaded_model and os.path.exists("data/types.json"):
            self.logger.info(
                "Using preloaded model and existing types.json, skipping full MIB compilation"
            )
            # Load existing type registry
            with open("data/types.json", "r") as f:
                type_registry_data = json.load(f)
            type_registry = TypeRegistry(Path(""))  # dummy
            type_registry._registry = type_registry_data
        else:
            type_registry = TypeRegistry(Path(compiled_dir))
            type_registry.build()
            type_registry.export_to_json("data/types.json")
            self.logger.info(
                f"Exported type registry to data/types.json with {len(type_registry.registry)} types."
            )

        # Validate types
        self.logger.info("Validating type registry...")
        from app.type_registry_validator import validate_type_registry_file

        is_valid, errors, type_count = validate_type_registry_file("data/types.json")
        if not is_valid:
            self.logger.error(f"Type registry validation failed: {errors}")
            return
        self.logger.info(
            f"Type registry validation passed. {type_count} types validated."
        )

        if self.preloaded_model:
            self.mib_jsons = self.preloaded_model
            self.logger.info("Using preloaded model for schemas")
        else:
            # Generate schema JSON for each MIB
            from app.generator import BehaviourGenerator

            generator = BehaviourGenerator(json_dir)
            for py_path in compiled_mib_paths:
                self.logger.info(f"Generating schema JSON for: {py_path}")
                try:
                    generator.generate(py_path)
                    self.logger.info(f"Schema JSON generated for {py_path}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate schema JSON for {py_path}: {e}",
                        exc_info=True,
                    )

            # Load schema JSONs for SNMP serving
            # Directory structure: {json_dir}/{MIB_NAME}/schema.json
            for mib in mibs:
                mib_dir = os.path.join(json_dir, mib)
                schema_path = os.path.join(mib_dir, "schema.json")

                if os.path.exists(schema_path):
                    with open(schema_path, "r") as jf:
                        self.mib_jsons[mib] = json.load(jf)
                    self.logger.info(f"Loaded schema for {mib} from {schema_path}")
                else:
                    self.logger.warning(f"Schema not found for {mib} at {schema_path}")

        self.logger.info(f"Loaded {len(self.mib_jsons)} MIB schemas for SNMP serving.")

        # Setup SNMP engine and transport
        self._setup_snmpEngine(compiled_dir)
        if self.snmpEngine is not None:
            self._setup_transport()
            self._setup_community()
            self._setup_responders()
            self._register_mib_objects()
            # Capture initial scalar values (for comparison) and apply overrides
            try:
                self._capture_initial_values()
                self._load_overrides()
                self._apply_overrides()
            except Exception as e:
                self.logger.error(f"Error applying overrides: {e}", exc_info=True)
            self._populate_sysor_table()  # Populate sysORTable with actual MIBs
            self.logger.info("SNMP Agent is now listening for SNMP requests.")
            # Block and serve SNMP requests using asyncio dispatcher
            try:
                self.logger.info("Entering SNMP event loop...")
                # Just run the dispatcher - no need for job_started() or open_dispatcher()
                self.snmpEngine.transport_dispatcher.run_dispatcher()
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, shutting down agent")
                self._shutdown()
            except Exception as e:
                self.logger.error(f"SNMP event loop error: {e}", exc_info=True)
                self._shutdown()
        else:
            self.logger.error(
                "snmpEngine is not initialized. SNMP agent will not start."
            )

    def _setup_snmpEngine(self, compiled_dir: str) -> None:
        from pysnmp.entity import engine
        from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
        from pysnmp.entity.rfc3413 import context
        from pysnmp.smi import builder as snmp_builder

        self.logger.info("Setting up SNMP engine...")
        self.snmpEngine = engine.SnmpEngine()

        # Register asyncio dispatcher
        dispatcher = AsyncioDispatcher()
        self.snmpEngine.register_transport_dispatcher(dispatcher)

        # Create context and get MIB builder from instrumentation (like working reference)
        self.snmpContext = context.SnmpContext(self.snmpEngine)
        mib_instrum = self.snmpContext.get_mib_instrum()
        self.mib_builder = mib_instrum.get_mib_builder()

        # Ensure compiled MIBs are discoverable and loaded into the builder
        compiled_path = Path(compiled_dir)
        self.mib_builder.add_mib_sources(snmp_builder.DirMibSource(str(compiled_path)))
        compiled_modules = [p.stem for p in compiled_path.glob("*.py")]
        if compiled_modules:
            self.mib_builder.load_modules(*compiled_modules)
            self.logger.info(
                "Loaded compiled MIB modules: %s", ", ".join(sorted(compiled_modules))
            )
        else:
            self.logger.warning(
                "No compiled MIB modules found to load from %s", compiled_dir
            )

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
        self.mib_registrar = MibRegistrar(
            mib_builder=self.mib_builder,
            mib_scalar_instance=MibScalarInstance,
            mib_table=MibTable,
            mib_table_row=MibTableRow,
            mib_table_column=MibTableColumn,
            logger=self.logger,
            start_time=self.start_time,
        )

        self.logger.info("SNMP engine and MIB classes initialized")

    def _setup_transport(self) -> None:
        try:
            from pysnmp.carrier.asyncio.dgram import udp
            from pysnmp.entity import config
        except ImportError:
            raise RuntimeError("pysnmp is not installed or not available.")
        if self.snmpEngine is None:
            raise RuntimeError("snmpEngine is not initialized.")

        # Use UdpAsyncioTransport for asyncio dispatcher
        config.add_transport(
            self.snmpEngine,
            config.SNMP_UDP_DOMAIN,
            udp.UdpAsyncioTransport().open_server_mode((self.host, self.port)),
        )
        self.logger.info(f"Transport opened on {self.host}:{self.port}")

    def _setup_community(self) -> None:
        from pysnmp.entity import config

        if self.snmpEngine is None:
            raise RuntimeError("snmpEngine is not initialized.")

        # Add read-only community "public"
        config.add_v1_system(self.snmpEngine, "public-area", "public")

        # Add read-write community "private"
        config.add_v1_system(self.snmpEngine, "private-area", "private")

        # Add context
        config.add_context(self.snmpEngine, "")

        # Create VACM groups for read-only and read-write access
        config.add_vacm_group(self.snmpEngine, "read-only-group", 2, "public-area")
        config.add_vacm_group(self.snmpEngine, "read-write-group", 2, "private-area")

        # Create VACM views
        # fullView: allows access to all OIDs (include)
        config.add_vacm_view(self.snmpEngine, "fullView", 1, (1,), "")
        # restrictedView: denies access to all OIDs (exclude) - used for write view in read-only
        config.add_vacm_view(self.snmpEngine, "restrictedView", 2, (1,), "")

        # Configure read-only access for "public" community
        config.add_vacm_access(
            self.snmpEngine,
            "read-only-group",
            "",
            2,
            "noAuthNoPriv",
            "prefix",
            "fullView",        # read view (allow all reads)
            "restrictedView",  # write view (deny all writes)
            "fullView",        # notify view
        )

        # Configure read-write access for "private" community
        config.add_vacm_access(
            self.snmpEngine,
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

        if self.snmpEngine is None:
            raise RuntimeError("snmpEngine is not initialized.")
        if not hasattr(self, "snmpContext") or self.snmpContext is None:
            raise RuntimeError("snmpContext is not initialized.")

        # Use the context created in _setup_snmpEngine
        cmdrsp.GetCommandResponder(self.snmpEngine, self.snmpContext)
        cmdrsp.NextCommandResponder(self.snmpEngine, self.snmpContext)
        cmdrsp.BulkCommandResponder(self.snmpEngine, self.snmpContext)
        cmdrsp.SetCommandResponder(self.snmpEngine, self.snmpContext)

    def _register_mib_objects(self) -> None:
        """Register all MIB objects using the MibRegistrar."""
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Create MibRegistrar lazily if it does not exist (tests may call this directly)
        registrar = getattr(self, "mib_registrar", None)
        if registrar is None:
            try:
                from app.mib_registrar import MibRegistrar

                registrar = MibRegistrar(
                    mib_builder=getattr(self, "mib_builder", None),
                    mib_scalar_instance=getattr(self, "MibScalarInstance", None),
                    mib_table=getattr(self, "MibTable", None),
                    mib_table_row=getattr(self, "MibTableRow", None),
                    mib_table_column=getattr(self, "MibTableColumn", None),
                    logger=self.logger,
                    start_time=self.start_time,
                )
                self.mib_registrar = registrar
            except Exception:
                self.logger.error("Failed to create MibRegistrar", exc_info=True)
                return

        registrar.register_all_mibs(self.mib_jsons)

    def _populate_sysor_table(self) -> None:
        """Populate sysORTable with the MIBs being served by this agent.

        This is called after all MIBs are registered to dynamically generate
        sysORTable rows based on the actual MIBs that have been loaded.
        """
        # Use the MibRegistrar to populate sysORTable
        self.mib_registrar.populate_sysor_table(self.mib_jsons)

    # The following methods have been moved to MibRegistrar:
    # - _register_mib()
    # - _build_mib_symbols()
    # - _build_table_symbols()
    # - _find_table_related_objects()
    # - _decode_value()
    # - _get_pysnmp_type()

    def _decode_value(self, value: Any) -> Any:
        """Compatibility wrapper: delegate decoding to MibRegistrar._decode_value.

        Historically this was a method on SNMPAgent; tests and some external
        callers expect it to exist. It simply delegates to a temporary
        MibRegistrar instance which implements the decoding logic.
        """
        try:
            from app.mib_registrar import MibRegistrar

            temp = MibRegistrar(
                mib_builder=None,
                mib_scalar_instance=None,
                mib_table=None,
                mib_table_row=None,
                mib_table_column=None,
                logger=self.logger,
                start_time=self.start_time,
            )
            return temp._decode_value(value)
        except Exception:
            # As a last resort, return the value unchanged
            return value

    def get_scalar_value(self, oid: tuple[int, ...]) -> Any:
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
        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                if isinstance(symbol_obj, MibScalarInstance) and symbol_obj.name == oid:
                    return symbol_obj.syntax
                    
        raise ValueError(f"Scalar OID {oid} not found")

    def set_scalar_value(self, oid: tuple[int, ...], value: Any) -> None:
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
                    # Update in-memory value
                    try:
                        # If incoming value is a pysnmp type, assign directly
                        symbol_obj.syntax = value
                    except Exception:
                        # Try to coerce using existing type class
                        try:
                            type_cls = type(symbol_obj.syntax)
                            symbol_obj.syntax = type_cls(value)
                        except Exception:
                            # Fallback to raw assignment
                            symbol_obj.syntax = value

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
                    except Exception:
                        pass

                    if initial is None or new_serial != initial:
                        # Save override
                        self.overrides[dotted] = new_serial
                        try:
                            self._save_overrides()
                        except Exception:
                            self.logger.exception("Failed to save overrides")
                    else:
                        # If we've reverted to initial, remove any existing override
                        if dotted in self.overrides:
                            self.overrides.pop(dotted, None)
                            try:
                                self._save_overrides()
                            except Exception:
                                self.logger.exception("Failed to save overrides")

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
                if hasattr(symbol_obj, 'name') and symbol_obj.name:
                    oid_map[symbol_name] = symbol_obj.name
        
        return oid_map

    def _lookup_symbol_for_dotted(self, dotted: str) -> tuple[Optional[str], Optional[str]]:
        """Return (module_name, symbol_name) for a dotted OID string if known.

        This helps produce human-friendly log messages (e.g. SNMPv2-MIB:sysContact).
        """
        if self.mib_builder is None:
            return None, None
        try:
            target_oid = tuple(int(x) for x in dotted.split("."))
        except Exception:
            return None, None

        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                try:
                    if hasattr(symbol_obj, "name") and symbol_obj.name:
                        if tuple(symbol_obj.name) == target_oid:
                            return module_name, symbol_name
                except Exception:
                    continue
        return None, None

    # ---- Overrides persistence helpers ----
    def _overrides_file_path(self) -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "overrides.json"))

    def _load_overrides(self) -> None:
        path = self._overrides_file_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self.overrides = json.load(f)
                self.logger.info(f"Loaded {len(self.overrides)} overrides from {path}")
                # Prune any overrides that are identical to initial values
                if self._initial_values:
                    removed = []
                    for k in list(self.overrides.keys()):
                        init = self._initial_values.get(k)
                        if init is not None and self.overrides.get(k) == init:
                            removed.append(k)
                            self.overrides.pop(k, None)
                    if removed:
                        self.logger.info(f"Pruned {len(removed)} redundant overrides: {removed}")
                        # Persist pruned result
                        try:
                            self._save_overrides()
                        except Exception:
                            self.logger.exception("Failed to save overrides after pruning")
            except Exception as e:
                self.logger.error(f"Failed to load overrides from {path}: {e}", exc_info=True)
                self.overrides = {}
        else:
            self.overrides = {}

    def _save_overrides(self) -> None:
        path = self._overrides_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            # Only persist overrides that differ from initial values (don't store defaults)
            to_persist = {}
            for k, v in self.overrides.items():
                init = self._initial_values.get(k)
                if init is None or v != init:
                    to_persist[k] = v

            with open(path, "w") as f:
                json.dump(to_persist, f, indent=2, sort_keys=True)
            self.logger.info(f"Saved {len(to_persist)} overrides to {path}")
        except Exception as e:
            self.logger.error(f"Failed to save overrides to {path}: {e}", exc_info=True)

    def _serialize_value(self, value: Any) -> object:
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
                except Exception:
                    return value.hex()
            # pysnmp rfc1902 types often stringify sensibly
            try:
                s = str(value)
                return s
            except Exception:
                return repr(value)
        except Exception:
            return str(value)

    def _capture_initial_values(self) -> None:
        """Capture the initial scalar values after MIB registration for comparison."""
        self._initial_values = {}
        if self.mib_builder is None:
            return
        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[0]
        except Exception:
            return

        for module_name, symbols in self.mib_builder.mibSymbols.items():
            for symbol_name, symbol_obj in symbols.items():
                try:
                    if isinstance(symbol_obj, MibScalarInstance) and hasattr(symbol_obj, "name") and symbol_obj.name:
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
                            if base_name.endswith("Inst"):
                                base_name = base_name[:-4]
                            if isinstance(module_json, dict) and base_name in module_json:
                                access_field = module_json[base_name].get("access")
                                if access_field and access_field.lower() == "read-write":
                                    self._writable_oids.add(dotted)
                                    added = True
                                    self.logger.debug(f"Marked writable via schema: {dotted} -> {module_name}.{base_name}")
                            if not added:
                                # Fallback to inspecting symbol object if it exposes access
                                access = None
                                if hasattr(symbol_obj, "getMaxAccess"):
                                    access = symbol_obj.getMaxAccess()
                                elif hasattr(symbol_obj, "maxAccess"):
                                    access = getattr(symbol_obj, "maxAccess")
                                if access and str(access).lower().startswith("readwrite"):
                                    self._writable_oids.add(dotted)
                        except Exception:
                            pass
                except Exception:
                    continue

        self.logger.info(f"Captured {len(self._initial_values)} initial scalar values")

    def _apply_overrides(self) -> None:
        """Apply loaded overrides to the in-memory MIB scalar instances."""
        if not self.overrides:
            return
        if self.mib_builder is None:
            return
        try:
            MibScalarInstance = self.mib_builder.import_symbols("SNMPv2-SMI", "MibScalarInstance")[0]
        except Exception:
            return

        removed_invalid: list[str] = []

        for dotted, stored in list(self.overrides.items()):
            try:
                oid = tuple(int(x) for x in dotted.split("."))
            except Exception:
                self.logger.warning(f"Invalid OID in overrides: {dotted}")
                removed_invalid.append(dotted)
                continue

            applied = False
            # We'll attempt the literal OID, and if not found and the OID does not
            # already end with an instance (i.e. last component != 0), try appending .0
            candidate_oids = [oid]
            try:
                if oid[-1] != 0:
                    candidate_oids.append(oid + (0,))
            except Exception:
                pass
            for module_name, symbols in self.mib_builder.mibSymbols.items():
                for symbol_name, symbol_obj in symbols.items():
                    try:
                        if isinstance(symbol_obj, MibScalarInstance) and tuple(symbol_obj.name) in candidate_oids:
                            # Determine target type class from existing syntax
                            try:
                                type_cls = type(symbol_obj.syntax)
                                # Try direct construction
                                try:
                                    symbol_obj.syntax = type_cls(stored)
                                except Exception:
                                    # Try numeric cast for integer-like types
                                    try:
                                        if isinstance(stored, str) and stored.isdigit():
                                            symbol_obj.syntax = type_cls(int(stored))
                                        else:
                                            # For octet strings, pass bytes
                                            if hasattr(type_cls, "__name__") and "Octet" in type_cls.__name__:
                                                if isinstance(stored, str):
                                                    symbol_obj.syntax = type_cls(stored.encode("latin1"))
                                                else:
                                                    symbol_obj.syntax = type_cls(stored)
                                            else:
                                                symbol_obj.syntax = type_cls(stored)
                                    except Exception:
                                        # Last resort: assign string representation
                                        symbol_obj.syntax = type_cls(str(stored))
                            except Exception:
                                # fallback to raw assignment
                                symbol_obj.syntax = stored

                            applied = True
                            break
                    except Exception:
                        continue
                if applied:
                    break

            if not applied:
                # No matching scalar instance found; mark for removal
                self.logger.warning(
                    f"Override for {dotted} found, but no matching scalar instance to apply"
                )
                removed_invalid.append(dotted)

        # Remove any invalid overrides that could not be applied
        if removed_invalid:
            for k in removed_invalid:
                self.overrides.pop(k, None)
            try:
                self._save_overrides()
            except Exception:
                self.logger.exception("Failed to save overrides after pruning invalid entries")
            self.logger.info(f"Removed {len(removed_invalid)} invalid overrides: {removed_invalid}")



if __name__ == "__main__": # pragma: no cover
    import sys

    try:
        agent = SNMPAgent()
        agent.run()
    except Exception as e:
        import traceback

        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
