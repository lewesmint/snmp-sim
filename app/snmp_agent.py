"""
SNMPAgent: Main orchestrator for the SNMP agent (initial workflow).
"""
from typing import cast
from app.app_logger import AppLogger
from app.app_config import AppConfig
from app.compiler import MibCompiler
from app.table_registrar import TableRegistrar
import os
from pathlib import Path
import json
import time
from typing import Any, Dict, Optional
from pysnmp import debug as pysnmp_debug

class SNMPAgent:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11161,
        config_path: str = "agent_config.yaml",
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
        # self.mib_builder: Optional[Any] = None
        self.mib_jsons: Dict[str, Dict[str, Any]] = {}
        # Track agent start time for sysUpTime
        self.start_time = time.time()

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
        compiler = MibCompiler(compiled_dir, self.app_config)
        compiled_mib_paths: list[str] = []
        for mib_path in mibs:
            self.logger.info(f"Compiling MIB: {mib_path}")
            try:
                py_path = compiler.compile(mib_path)
                compiled_mib_paths.append(py_path)
                self.logger.info(f"Compiled {mib_path} to {py_path}")
            except Exception as e:
                self.logger.error(f"Failed to compile {mib_path}: {e}", exc_info=True)
                continue

        # Build and export the canonical type registry
        from app.type_registry import TypeRegistry

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
        self.logger.info(f"Type registry validation passed. {type_count} types validated.")

        # Generate JSON for MIB behavior
        from app.generator import BehaviourGenerator

        generator = BehaviourGenerator(json_dir)
        for py_path in compiled_mib_paths:
            self.logger.info(f"Generating behavior JSON for: {py_path}")
            try:
                generator.generate(py_path)
                self.logger.info(f"Behavior JSON generated for {py_path}")
            except Exception as e:
                self.logger.error(f"Failed to generate behavior JSON for {py_path}: {e}", exc_info=True)

        # Load behavior JSONs for SNMP serving
        for mib in mibs:
            json_path = os.path.join(json_dir, f"{mib}_behaviour.json")
            if os.path.exists(json_path):
                with open(json_path, "r") as jf:
                    self.mib_jsons[mib] = json.load(jf)
        self.logger.info("Loaded behavior JSONs for SNMP serving.")

        # Setup SNMP engine and transport
        self._setup_snmpEngine(compiled_dir)
        if self.snmpEngine is not None:
            self._setup_transport()
            self._setup_community()
            self._setup_responders()
            self._register_mib_objects()
            self.logger.info("SNMP Agent is now listening for SNMP requests.")
            # Block and serve SNMP requests using asyncio carrier correctly
            try:
                self.logger.info("Entering SNMP event loop...")
                self.snmpEngine.transport_dispatcher.job_started(1)

                # IMPORTANT: asyncio carrier needs the dispatcher to stay open
                # open_dispatcher() opens it but doesn't block, so we block using run_dispatcher()
                self.snmpEngine.open_dispatcher()
                
                # Run the dispatcher's internal event loop - this blocks
                self.snmpEngine.transport_dispatcher.run_dispatcher()
            except KeyboardInterrupt:
                self.logger.info("Shutting down agent")
            except Exception as e:
                self.logger.error(f"SNMP event loop error: {e}", exc_info=True)
            finally:
                # Close dispatcher on exit
                self.snmpEngine.close_dispatcher()
        else:
            self.logger.error("snmpEngine is not initialized. SNMP agent will not start.")

    def _setup_snmpEngine(self, compiled_dir: str) -> None:
        from pysnmp.entity import engine
        from pysnmp.smi import builder

        self.logger.info("Setting up SNMP engine...")
        self.snmpEngine = engine.SnmpEngine()
        self.mib_builder = self.snmpEngine.get_mib_builder()

        # Add MIB sources
        self.mib_builder.add_mib_sources(builder.DirMibSource(compiled_dir))

        # Import MIB classes from SNMPv2-SMI
        (self.MibScalar,
         self.MibScalarInstance,
         self.MibTable,
         self.MibTableRow,
         self.MibTableColumn) = self.mib_builder.import_symbols(
            'SNMPv2-SMI',
            'MibScalar',
            'MibScalarInstance',
            'MibTable',
            'MibTableRow',
            'MibTableColumn'
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
        config.add_transport(
            self.snmpEngine,
            udp.DOMAIN_NAME,
            udp.UdpTransport().open_server_mode((self.host, self.port)),
        )

    def _setup_community(self) -> None:
        from pysnmp.entity import config

        if self.snmpEngine is None:
            raise RuntimeError("snmpEngine is not initialized.")
        config.add_v1_system(self.snmpEngine, "my-area", "public")
        config.add_context(self.snmpEngine, "")
        config.add_vacm_group(self.snmpEngine, "mygroup", 2, "my-area")
        config.add_vacm_view(self.snmpEngine, "restrictedView", 1, (1, 3, 6, 1), "")
        config.add_vacm_view(
            self.snmpEngine, "restrictedView", 2, (1, 3, 6, 1, 6, 3), ""
        )
        config.add_vacm_access(
            self.snmpEngine,
            "mygroup",
            "",
            2,
            "noAuthNoPriv",
            "exact",
            "restrictedView",
            "restrictedView",
            "restrictedView",
        )

    def _setup_responders(self) -> None:
        from pysnmp.entity.rfc3413 import cmdrsp, context

        if self.snmpEngine is None:
            raise RuntimeError("snmpEngine is not initialized.")
        snmpContext = context.SnmpContext(self.snmpEngine)
        cmdrsp.GetCommandResponder(self.snmpEngine, snmpContext)
        cmdrsp.NextCommandResponder(self.snmpEngine, snmpContext)
        cmdrsp.BulkCommandResponder(self.snmpEngine, snmpContext)
        cmdrsp.SetCommandResponder(self.snmpEngine, snmpContext)

    def _register_mib_objects(self) -> None:
        # Register scalars and tables from behavior JSONs using the type registry
        if self.mib_builder is None:
            self.logger.error("mibBuilder is not initialized.")
            return

        # Load the type registry from the exported JSON file
        type_registry_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "types.json"
        )
        try:
            with open(type_registry_path, "r") as f:
                type_registry = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load type registry: {e}", exc_info=True)
            type_registry = {}

        # Register each MIB with all its objects (scalars and tables) at once
        for mib, mib_json in self.mib_jsons.items():
            self._register_mib(mib, mib_json, type_registry)

    def _register_mib(
        self,
        mib: str,
        mib_json: Dict[str, Any],
        type_registry: Dict[str, Any]
    ) -> None:
        """Register a complete MIB with all its objects (scalars and tables)."""
        try:
            export_symbols = self._build_mib_symbols(mib, mib_json, type_registry)
            if export_symbols:
                self.mib_builder.export_symbols(mib, **export_symbols)
                self.logger.info(f"Registered {len(export_symbols)} objects for {mib}")
            else:
                self.logger.warning(f"No objects to register for {mib}")
        except Exception as e:
            self.logger.error(f"Error registering MIB {mib}: {e}", exc_info=True)

    def _build_mib_symbols(
        self,
        mib: str,
        mib_json: Dict[str, Any],
        type_registry: Dict[str, Any]
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
            base_type = type_info.get("base_type") or type_name
            
            if not base_type or not isinstance(base_type, str):
                self.logger.warning(f"Skipping {name}: invalid type '{type_name}'")
                continue
            
            # Special handling for sysUpTime
            if name == "sysUpTime":
                uptime_seconds = time.time() - self.start_time
                value = int(uptime_seconds * 100)
            
            # Handle None values with defaults
            if value is None:
                if base_type in ["Integer32", "Integer", "Gauge32", "Counter32", "Counter64", "TimeTicks", "Unsigned32"]:
                    value = 0
                elif base_type in ["OctetString", "DisplayString"]:
                    value = ""
                elif base_type == "ObjectIdentifier":
                    value = "0.0"
                else:
                    self.logger.warning(f"Skipping {name}: no value and no default for type '{base_type}'")
                    continue
            
            # Get SNMP type class
            try:
                pysnmp_type = self._get_pysnmp_type(base_type)
                if pysnmp_type is None:
                    raise ImportError(f"Could not resolve type '{base_type}'")
                
                # Create scalar instance
                scalar_inst = self.MibScalarInstance(
                    oid_value, (0,), pysnmp_type(value)
                )
                export_symbols[f"{name}Inst"] = scalar_inst
                self.logger.debug(f"Added scalar {name} (type {base_type})")
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
                table_symbols = self._build_table_symbols(mib, name, info, mib_json, type_registry)
                export_symbols.update(table_symbols)
            except Exception as e:
                self.logger.error(f"Error building table {name}: {e}", exc_info=True)
                continue
        
        return export_symbols

    def _build_table_symbols(
        self,
        mib: str,
        table_name: str,
        table_info: Dict[str, Any],
        mib_json: Dict[str, Any],
        type_registry: Dict[str, Any]
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
            if col_oid[:len(entry_oid)] != entry_oid:
                continue
            
            col_type_name = col_info.get("type")
            if not col_type_name:
                continue
            
            type_info = type_registry.get(col_type_name, {})
            base_type = type_info.get("base_type") or col_type_name
            
            try:
                pysnmp_type = self._get_pysnmp_type(base_type)
                if pysnmp_type is None:
                    continue
                
                col_access = col_info.get("access", "read-only")
                col_obj = self.MibTableColumn(col_oid, pysnmp_type()).setMaxAccess(col_access)
                symbols[col_name] = col_obj
                columns_by_name[col_name] = (col_oid, base_type)
            except Exception as e:
                self.logger.warning(f"Error creating column {col_name}: {e}")
                continue
        
        # Create row instances
        rows_data = table_info.get("rows", [])
        if not isinstance(rows_data, list):
            rows_data = []
        
        for row_idx, row_data in enumerate(rows_data):
            if not isinstance(row_data, dict):
                continue
            
            # Get or create index tuple
            index_value = row_data.get("index")
            if index_value is None:
                index_value = row_idx + 1
            
            if isinstance(index_value, list):
                index_tuple = tuple(index_value)
            else:
                index_tuple = (index_value,)
            
            # Create instances for each column
            row_values = row_data.get("values", {})
            
            for col_name, (col_oid, base_type) in columns_by_name.items():
                # Get value for this cell
                if col_name in row_values:
                    value = row_values[col_name]
                elif col_name in index_names:
                    # Use index value for index columns
                    idx_pos = index_names.index(col_name)
                    value = index_tuple[idx_pos]
                else:
                    continue
                
                try:
                    pysnmp_type = self._get_pysnmp_type(base_type)
                    if pysnmp_type is None:
                        continue
                    
                    inst = self.MibScalarInstance(
                        col_oid,
                        index_tuple,
                        pysnmp_type(value)
                    )
                    
                    inst_name = f"{col_name}Inst_{'_'.join(map(str, index_tuple))}"
                    symbols[inst_name] = inst
                except Exception as e:
                    self.logger.warning(f"Error creating instance for {col_name} row {index_tuple}: {e}")
                    continue
        
        return symbols

    def _find_table_related_objects(self, mib_json: Dict[str, Any]) -> set[str]:
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
                                if col_oid[:len(entry_oid)] == entry_oid:
                                    table_related.add(col_name)
        
        return table_related

    def _get_pysnmp_type(self, base_type: str) -> Any:
        """Get SNMP type class from base type name."""
        try:
            return self.mib_builder.import_symbols("SNMPv2-SMI", base_type)[0]
        except Exception:
            try:
                return self.mib_builder.import_symbols("SNMPv2-TC", base_type)[0]
            except Exception:
                from pysnmp.proto import rfc1902
                return getattr(rfc1902, base_type, None)




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