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
        config.add_v1_system(self.snmpEngine, "my-area", "public")
        config.add_context(self.snmpEngine, "")
        config.add_vacm_group(self.snmpEngine, "mygroup", 2, "my-area")
        config.add_vacm_view(self.snmpEngine, "fullView", 1, (1,), "")
        config.add_vacm_access(
            self.snmpEngine,
            "mygroup",
            "",
            2,
            "noAuthNoPriv",
            "prefix",
            "fullView",
            "fullView",
            "fullView",
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

        # Use the MibRegistrar to register all MIBs
        self.mib_registrar.register_all_mibs(self.mib_jsons)

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


if __name__ == "__main__":
    import sys

    try:
        agent = SNMPAgent()
        agent.run()
    except Exception as e:
        import traceback

        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
