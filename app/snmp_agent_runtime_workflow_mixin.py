"""Runtime setup and schema workflow mixin for SNMPAgent."""

# pylint: disable=invalid-name

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: D101,EM101,N806,PERF102,SLF001,TC006,TRY003,TRY300,TRY401

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.smi import builder as snmp_builder

from app.compiler import MibCompiler
from app.generator import BehaviourGenerator
from app.mib_registrar import MibRegistrar, SNMPContext
from app.model_paths import TYPE_REGISTRY_FILE, agent_model_dir, compiled_mibs_dir
from app.pysnmp_mib_symbols_adapter import PysnmpMibSymbolsAdapter
from app.type_registry import TypeRegistry
from app.type_registry_validator import validate_type_registry_file
from app.value_links import get_link_manager

if TYPE_CHECKING:
    from pysnmp_type_wrapper.raw_boundary_types import SupportsBoundaryMibBuilder


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class SNMPAgentRuntimeWorkflowMixin:
    mib_registrar: MibRegistrar | None
    mib_symbols_adapter: Any | None
    MibScalar: type[object] | None
    MibScalarInstance: type[object] | None
    MibTable: type[object] | None
    MibTableRow: type[object] | None
    MibTableColumn: type[object] | None

    def _find_source_mib_file(self, mib_name: str) -> Path | None:
        """Find the source .mib file for a given MIB name.

        Searches in data/mibs and all its subdirectories.
        Returns the Path to the .mib file if found, None otherwise.
        """
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

    def _should_recompile(self, mib_name: str, compiled_file: Path | str) -> bool:
        """Check if a MIB should be recompiled based on timestamp comparison.

        Returns True if:
        - The compiled file doesn't exist, OR
        - The source .mib file is newer than the compiled .py file
        """
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

    def _compile_required_mibs(
        self,
        *,
        mibs: list[str],
        compiled_dir: Path,
        compiler: MibCompiler,
    ) -> None:
        for mib_name in mibs:
            compiled_file = compiled_dir / f"{mib_name}.py"
            if not self._should_recompile(mib_name, compiled_file):
                continue

            if compiled_file.exists():
                self.logger.info("Recompiling outdated MIB: %s", mib_name)
            else:
                self.logger.info("Compiling missing MIB: %s", mib_name)

            try:
                py_path = compiler.compile(mib_name)
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

    def _prepare_type_registry(self, *, compiled_dir: Path, types_json_path: Path) -> None:
        if self.preloaded_model and types_json_path.exists():
            self.logger.info(
                "Using preloaded model and existing types.json, skipping full MIB compilation"
            )
            try:
                with types_json_path.open("r", encoding="utf-8") as f:
                    type_registry_data = json.load(f)
                type_registry = TypeRegistry(Path())
                type_registry._registry = type_registry_data
                return
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
            "Exported type registry to %s with %s types.",
            types_json_path,
            len(type_registry.registry),
        )

    def _validate_type_registry_or_log(self, types_json_path: Path) -> bool:
        self.logger.info("Validating type registry...")
        is_valid, errors, type_count = validate_type_registry_file(str(types_json_path))
        if not is_valid:
            self.logger.error("Type registry validation failed: %s", errors)
            return False
        self.logger.info("Type registry validation passed. %s types validated.", type_count)
        return True

    def _build_mib_to_py_path(self, *, mibs: list[str], compiled_dir: Path) -> dict[str, str]:
        mib_to_py_path: dict[str, str] = {}
        for mib in mibs:
            py_file = compiled_dir / f"{mib}.py"
            if py_file.exists():
                mib_to_py_path[mib] = str(py_file)
        return mib_to_py_path

    def _generate_schema_files(
        self,
        *,
        generator: BehaviourGenerator,
        mib_to_py_path: dict[str, str],
        json_dir: Path,
    ) -> None:
        for mib_name, py_path in mib_to_py_path.items():
            self.logger.info("Processing schema for %s: %s", mib_name, py_path)
            try:
                schema_path = json_dir / mib_name / "schema.json"
                force_regen = True
                if schema_path.exists():
                    schema_mtime = Path(schema_path).stat().st_mtime
                    py_mtime = Path(py_path).stat().st_mtime
                    if py_mtime <= schema_mtime:
                        force_regen = False
                        self.logger.info(
                            "%s", f"✓ Schema for {mib_name} is up-to-date "
                            f"(MIB: {py_mtime:.0f}, Schema: {schema_mtime:.0f}). "
                            f"Preserving baked values. To regenerate, use Fresh State."
                        )
                    else:
                        self.logger.info(
                            "Compiled MIB %s is newer than schema, regenerating",
                            mib_name
                        )
                else:
                    self.logger.info(
                        "Schema does not exist for %s, generating from compiled MIB", mib_name
                    )

                generator.generate(py_path, mib_name=mib_name, force_regenerate=force_regen)
                if force_regen:
                    self.logger.info("Schema JSON generated for %s", mib_name)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.exception("Failed to generate schema JSON for %s: %s", mib_name, e)

    def _warn_invalid_schema_files(self, *, mibs: list[str], json_dir: Path) -> None:
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

    def _load_single_schema_with_recovery(
        self,
        *,
        mib: str,
        schema_path: Path,
        generator: BehaviourGenerator,
        mib_to_py_path: dict[str, str],
    ) -> None:
        try:
            with schema_path.open("r", encoding="utf-8") as jf:
                self.mib_jsons[mib] = json.load(jf)
            self._repair_loaded_schema(mib, self.mib_jsons[mib])
            self._validate_snmpv2_core_schema(mib, self.mib_jsons[mib])
            self.logger.info("Loaded schema for %s from %s", mib, schema_path)
            return
        except json.JSONDecodeError as e:
            self.logger.warning("Invalid JSON schema for %s at %s: %s", mib, schema_path, e)

        regen_py_path = mib_to_py_path.get(mib)
        if not regen_py_path:
            self.logger.warning(
                "Skipping schema for %s due to invalid JSON at %s",
                mib,
                schema_path
            )
            return

        try:
            self.logger.info("Regenerating schema for %s due to invalid JSON...", mib)
            generator.generate(regen_py_path, mib_name=mib, force_regenerate=True)
            with schema_path.open("r", encoding="utf-8") as jf:
                self.mib_jsons[mib] = json.load(jf)
            self._repair_loaded_schema(mib, self.mib_jsons[mib])
            self._validate_snmpv2_core_schema(mib, self.mib_jsons[mib])
            self.logger.info("Successfully regenerated and loaded schema for %s", mib)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as regen_error:
            if isinstance(regen_error, ValueError):
                raise
            self.logger.exception("Failed to regenerate schema for %s: %s", mib, regen_error)
            self.logger.warning(
                "Skipping schema for %s due to invalid JSON at %s", mib, schema_path)

    def _load_or_generate_schemas(
        self,
        *,
        mibs: list[str],
        compiled_dir: Path,
        json_dir: Path,
    ) -> None:
        if self.preloaded_model:
            self.mib_jsons = self.preloaded_model
            self.logger.info("Using preloaded model for schemas")
            return

        generator = BehaviourGenerator(str(json_dir))
        mib_to_py_path = self._build_mib_to_py_path(mibs=mibs, compiled_dir=compiled_dir)
        self._generate_schema_files(
            generator=generator,
            mib_to_py_path=mib_to_py_path,
            json_dir=json_dir
        )
        self._warn_invalid_schema_files(mibs=mibs, json_dir=json_dir)

        for mib in mibs:
            schema_path = json_dir / mib / "schema.json"
            if not schema_path.exists():
                self.logger.warning("Schema not found for %s at %s", mib, schema_path)
                continue
            self._load_single_schema_with_recovery(
                mib=mib,
                schema_path=schema_path,
                generator=generator,
                mib_to_py_path=mib_to_py_path,
            )

    def _validate_loaded_schemas_or_raise(self) -> None:
        for loaded_mib, loaded_schema in self.mib_jsons.items():
            self._validate_snmpv2_core_schema(loaded_mib, loaded_schema)
        self.logger.info("Loaded %d MIB schemas for SNMP serving.", len(self.mib_jsons))

    def _load_value_links_from_schemas(self) -> None:
        link_manager = get_link_manager()
        link_manager.clear()
        for _mib_name, schema in self.mib_jsons.items():
            link_manager.load_links_from_schema(cast("dict[str, object]", schema))
        self.logger.info("Value links loaded from schemas")

    def _start_snmp_runtime(self, *, compiled_dir: Path) -> None:
        self._setup_snmp_engine(str(compiled_dir))
        if self.snmp_engine is None:
            self.logger.error("snmp_engine is not initialized. SNMP agent will not start.")
            return

        self._setup_transport()
        self._setup_community()
        self._setup_responders()
        self._register_mib_objects()

        try:
            self._capture_initial_values()
            self._load_mib_state()
            self._apply_overrides()
            self._apply_table_instances()
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.exception("Error applying overrides: %s", e)

        self._populate_sysor_table()
        self.logger.info("SNMP Agent is now listening for SNMP requests.")
        try:
            self.logger.info("Entering SNMP event loop...")
            self.snmp_engine.transport_dispatcher.run_dispatcher()
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down agent")
            self._shutdown()
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.exception("SNMP event loop error: %s", e)
            self._shutdown()

    def run(self) -> None:
        """Compile/load MIB assets, register symbols, and start the SNMP dispatcher."""
        self.logger.info("Starting SNMP Agent setup workflow...")
        mibs = cast("list[str]", self.app_config.get("mibs", []))
        compiled_dir = compiled_mibs_dir(__file__)
        json_dir = agent_model_dir(__file__)
        json_dir.mkdir(parents=True, exist_ok=True)

        compiler = MibCompiler(str(compiled_dir), self.app_config)
        self._compile_required_mibs(mibs=mibs, compiled_dir=compiled_dir, compiler=compiler)

        types_json_path = TYPE_REGISTRY_FILE
        self._prepare_type_registry(compiled_dir=compiled_dir, types_json_path=types_json_path)
        if not self._validate_type_registry_or_log(types_json_path):
            return

        self._load_or_generate_schemas(mibs=mibs, compiled_dir=compiled_dir, json_dir=json_dir)
        self._validate_loaded_schemas_or_raise()
        self._load_value_links_from_schemas()
        self._build_augmented_index_map()
        self._start_snmp_runtime(compiled_dir=compiled_dir)

    def _setup_snmp_engine(self, compiled_dir: str) -> None:
        self.logger.info("Setting up SNMP engine...")
        self.snmp_engine = engine.SnmpEngine()

        # Register asyncio dispatcher
        dispatcher = AsyncioDispatcher()
        self.snmp_engine.register_transport_dispatcher(dispatcher)

        # Create context and get MIB builder from instrumentation (like working reference)
        self.snmp_context = context.SnmpContext(self.snmp_engine)
        mib_instrum = self.snmp_context.get_mib_instrum()
        self.mib_builder = mib_instrum.get_mib_builder()
        self.mib_symbols_adapter = PysnmpMibSymbolsAdapter(
            cast("SupportsBoundaryMibBuilder", self.mib_builder)
        )
        self._mib_symbols_adapter_builder = self.mib_builder

        # Ensure compiled MIBs are discoverable and loaded into the builder
        compiled_path = Path(compiled_dir)
        self.mib_builder.add_mib_sources(snmp_builder.DirMibSource(str(compiled_path)))
        compiled_modules = [p.stem for p in compiled_path.glob("*.py")]
        if compiled_modules:
            self.mib_builder.load_modules(*compiled_modules)
            self.logger.info("Loaded compiled MIB modules: %s", ", ".join(sorted(compiled_modules)))
        else:
            self.logger.warning("No compiled MIB modules found to load from %s", compiled_dir)

        # Import canonical MIB classes from SNMPv2-SMI via wrapper helper
        snmpv2_smi_classes = self.mib_symbols_adapter.load_snmpv2_smi_classes()
        if snmpv2_smi_classes is None:
            raise RuntimeError("Failed to load SNMPv2-SMI class symbols")

        MibScalar = snmpv2_smi_classes.mib_scalar
        MibScalarInstance = snmpv2_smi_classes.mib_scalar_instance
        MibTable = snmpv2_smi_classes.mib_table
        MibTableRow = snmpv2_smi_classes.mib_table_row
        MibTableColumn = snmpv2_smi_classes.mib_table_column
        self.MibScalar = MibScalar
        self.MibScalarInstance = MibScalarInstance
        self.MibTable = MibTable
        self.MibTableRow = MibTableRow
        self.MibTableColumn = MibTableColumn

        # Create MIB registrar
        snmp_context = SNMPContext(
            mib_builder=self.mib_builder,
            mib_scalar=MibScalar,
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
        if self.snmp_engine is None:
            raise RuntimeError("snmp_engine is not initialized.")
        if not hasattr(self, "snmp_context") or self.snmp_context is None:
            raise RuntimeError("snmp_context is not initialized.")

        # Use the context created in _setup_snmp_engine
        cmdrsp.GetCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.NextCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.BulkCommandResponder(self.snmp_engine, self.snmp_context)
        cmdrsp.SetCommandResponder(self.snmp_engine, self.snmp_context)
