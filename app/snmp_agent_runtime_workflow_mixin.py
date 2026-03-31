"""Runtime setup and schema workflow mixin for SNMPAgent."""

# pylint: disable=invalid-name

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: D101,EM101,N806,PERF102,SLF001,TC006,TRY003,TRY300,TRY401

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pyasn1.type.base import SimpleAsn1Type
from pyasn1.type.univ import Integer, OctetString
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    NotificationType,
    ObjectIdentity,
    ObjectType,
    UdpTransportTarget,
    send_notification,
)
from pysnmp.smi import builder as snmp_builder

from app.api_debug import record_snmp_operation
from app.behaviour_plugins import SetTransition, get_set_transition_trap_directives
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

_VAR_BIND_MIN_TUPLE_LEN = 2
_LOOKUP_RESULT_TUPLE_LEN = 2


def _to_var_text(value: object) -> str:
    pretty = getattr(value, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(value)


class SNMPAgentRuntimeWorkflowMixin:
    mib_registrar: MibRegistrar | None
    mib_symbols_adapter: Any | None
    MibScalar: type[object] | None
    MibScalarInstance: type[object] | None
    MibTable: type[object] | None
    MibTableRow: type[object] | None
    MibTableColumn: type[object] | None

    @staticmethod
    def _format_request_oid(var_bind: object) -> str:
        """Best-effort formatter for request OIDs in MIB instrumentation callbacks."""
        oid_obj = var_bind
        if isinstance(var_bind, tuple) and var_bind:
            oid_obj = var_bind[0]

        if isinstance(oid_obj, (tuple, list)):
            with contextlib.suppress(TypeError, ValueError):
                oid_tuple = tuple(int(x) for x in oid_obj)
                return ".".join(str(x) for x in oid_tuple)

        return str(oid_obj)

    def _format_set_request_var_bind(self, var_bind: object) -> str:
        """Best-effort formatter for SNMP SET request var-binds (OID=value)."""
        if isinstance(var_bind, tuple) and len(var_bind) >= _VAR_BIND_MIN_TUPLE_LEN:
            oid_text = self._format_request_oid(var_bind)
            return f"{oid_text}={var_bind[1]!r}"
        return self._format_request_oid(var_bind)

    def _install_snmp_request_logging_hooks(self, mib_instrum: object) -> None:
        """Log SNMP GET/GETNEXT requests at the instrumentation boundary."""
        read_variables = getattr(mib_instrum, "read_variables", None)
        if callable(read_variables):

            def _logged_read_variables(*var_binds: object, **ctx: object) -> object:
                oids = [self._format_request_oid(vb) for vb in var_binds]
                self.logger.info("SNMP GET request for OID(s): %s", ", ".join(oids))
                for oid in oids:
                    record_snmp_operation("GET", oid)
                return read_variables(*var_binds, **ctx)

            mib_instrum.read_variables = _logged_read_variables

        read_next_variables = getattr(mib_instrum, "read_next_variables", None)
        if callable(read_next_variables):

            def _logged_read_next_variables(*var_binds: object, **ctx: object) -> object:
                oids = [self._format_request_oid(vb) for vb in var_binds]
                self.logger.info("SNMP GETNEXT request for OID(s): %s", ", ".join(oids))
                for oid in oids:
                    record_snmp_operation("GETNEXT", oid)
                return read_next_variables(*var_binds, **ctx)

            mib_instrum.read_next_variables = _logged_read_next_variables

        write_variables = getattr(mib_instrum, "write_variables", None)
        if callable(write_variables):

            def _logged_write_variables(*var_binds: object, **ctx: object) -> object:
                formatted = [self._format_set_request_var_bind(vb) for vb in var_binds]
                self.logger.info("SNMP SET request for var-bind(s): %s", ", ".join(formatted))
                before_values: dict[str, str | None] = {}
                for vb in var_binds:
                    oid_text = self._format_request_oid(vb)
                    val_text: str | None = None
                    if isinstance(vb, tuple) and len(vb) >= _VAR_BIND_MIN_TUPLE_LEN:
                        val = vb[1]
                        val_text = _to_var_text(val)
                    before_values[oid_text] = self._read_oid_value_text(oid_text)
                    record_snmp_operation("SET", oid_text, val_text)
                result = write_variables(*var_binds, **ctx)
                self._emit_behaviour_traps_after_set(var_binds, before_values)
                return result

            mib_instrum.write_variables = _logged_write_variables

    def _read_oid_value_text(self, oid_text: str) -> str | None:
        """Best-effort current scalar value lookup for transition detection."""
        with contextlib.suppress(ValueError, RuntimeError, TypeError, AttributeError):
            oid_tuple = tuple(int(part) for part in oid_text.split("."))
            value = self.get_scalar_value(oid_tuple)
            return _to_var_text(value)
        return None

    def _emit_behaviour_traps_after_set(
        self,
        var_binds: tuple[object, ...],
        before_values: dict[str, str | None],
    ) -> None:
        """Emit plugin-defined traps after successful SET commit."""
        for vb in var_binds:
            if not (isinstance(vb, tuple) and len(vb) >= _VAR_BIND_MIN_TUPLE_LEN):
                continue
            oid_text = self._format_request_oid(vb)
            new_text = _to_var_text(vb[1])
            old_text = before_values.get(oid_text)

            mib_name: str | None = None
            symbol_name: str | None = None
            raw_lookup_fn: object = getattr(self, "_lookup_symbol_for_dotted", None)
            lookup_fn: Callable[[str], object] | None = (
                cast("Callable[[str], object]", raw_lookup_fn)
                if callable(raw_lookup_fn)
                else None
            )
            if lookup_fn is not None:
                try:
                    lookup_result = lookup_fn(oid_text)
                    if (
                        isinstance(lookup_result, tuple)
                        and len(lookup_result) == _LOOKUP_RESULT_TUPLE_LEN
                    ):
                        candidate_mib, candidate_symbol = lookup_result
                        if candidate_mib is None or isinstance(candidate_mib, str):
                            mib_name = candidate_mib
                        if candidate_symbol is None or isinstance(candidate_symbol, str):
                            symbol_name = candidate_symbol
                except (
                    AttributeError,
                    LookupError,
                    OSError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ):
                    pass

            transition = SetTransition(
                oid=oid_text,
                mib_name=mib_name,
                symbol_name=symbol_name,
                old_value=old_text,
                new_value=new_text,
            )
            directives = get_set_transition_trap_directives(transition)
            for directive in directives:
                converted_var_binds = [
                    (oid, self._coerce_trap_value(value)) for oid, value in directive.var_binds
                ]
                self._schedule_snmp_trap_send(directive.trap_oid, converted_var_binds)

    @staticmethod
    def _coerce_trap_value(value: object) -> SimpleAsn1Type:
        if isinstance(value, SimpleAsn1Type):
            return value
        if isinstance(value, int):
            return cast(SimpleAsn1Type, Integer().clone(value))
        if isinstance(value, str):
            return cast(SimpleAsn1Type, OctetString().clone(value))
        return cast(SimpleAsn1Type, OctetString().clone(str(value)))

    def _schedule_snmp_trap_send(
        self,
        trap_oid: str,
        var_binds: list[tuple[str, SimpleAsn1Type]],
    ) -> None:
        """Send trap now if no loop is running, otherwise schedule on current loop."""

        async def _send() -> None:
            snmp_engine = getattr(self, "snmp_engine", None)
            if snmp_engine is None:
                return

            notification = NotificationType(ObjectIdentity(trap_oid))
            if var_binds:
                notification = notification.add_varbinds(
                    *[ObjectType(ObjectIdentity(oid), value) for oid, value in var_binds]
                )

            error_indication, error_status, error_index, _ = await send_notification(
                snmp_engine,
                CommunityData("public"),
                await UdpTransportTarget.create(("127.0.0.1", 162)),
                ContextData(),
                "trap",
                notification,
            )
            if error_indication:
                self.logger.warning("Modeled trap send error: %s", error_indication)
            elif error_status:
                self.logger.warning(
                    "Modeled trap send error: %s at %s",
                    error_status,
                    error_index,
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                asyncio.run(_send())
            return

        task = loop.create_task(_send())
        task.add_done_callback(lambda _task: None)

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

    def _repair_sysor_table_basics(self, sysor_table: dict[str, JsonValue]) -> bool:
        """Ensure sysORTable has required top-level metadata fields."""
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
        return changed

    def _repair_sysor_entry(self, objects: dict[str, JsonValue]) -> bool:
        """Ensure sysOREntry exists and references sysORIndex as its index."""
        expected_sysor_entry_oid: list[int] = [1, 3, 6, 1, 2, 1, 1, 9, 1]
        sysor_entry = objects.get("sysOREntry")
        if not isinstance(sysor_entry, dict):
            objects["sysOREntry"] = {
                "oid": cast(JsonValue, expected_sysor_entry_oid),
                "type": "MibTableRow",
                "indexes": ["sysORIndex"],
            }
            return True

        changed = False
        if sysor_entry.get("oid") != expected_sysor_entry_oid:
            sysor_entry["oid"] = cast(JsonValue, expected_sysor_entry_oid)
            changed = True

        if not sysor_entry.get("type"):
            sysor_entry["type"] = "MibTableRow"
            changed = True

        indexes = sysor_entry.get("indexes")
        if isinstance(indexes, list):
            normalized_indexes = [str(index) for index in indexes if index is not None]
            if normalized_indexes != ["sysORIndex"]:
                sysor_entry["indexes"] = ["sysORIndex"]
                changed = True
        elif sysor_entry.get("index") != "sysORIndex":
            sysor_entry["indexes"] = ["sysORIndex"]
            changed = True

        return changed

    def _repair_sysor_columns(self, objects: dict[str, JsonValue]) -> bool:
        """Ensure sysOR column metadata exists and matches expected OIDs/types/access."""
        changed = False
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

        return changed

    def _repair_loaded_schema(
        self,
        mib: str,
        schema: dict[str, JsonValue],
    ) -> None:
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
        changed |= self._repair_sysor_table_basics(sysor_table)
        changed |= self._repair_sysor_entry(objects)
        changed |= self._repair_sysor_columns(objects)

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
        self._install_snmp_request_logging_hooks(mib_instrum)
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

        # Import canonical MIB classes from SNMPv2-SMI.
        # Keep compatibility with older adapter versions that do not expose
        # load_snmpv2_smi_classes().
        snmpv2_smi_classes_loader = getattr(
            self.mib_symbols_adapter,
            "load_snmpv2_smi_classes",
            None,
        )
        if callable(snmpv2_smi_classes_loader):
            snmpv2_smi_classes = snmpv2_smi_classes_loader()
            if snmpv2_smi_classes is None:
                raise RuntimeError("Failed to load SNMPv2-SMI class symbols")

            MibScalar = snmpv2_smi_classes.mib_scalar
            MibScalarInstance = snmpv2_smi_classes.mib_scalar_instance
            MibTable = snmpv2_smi_classes.mib_table
            MibTableRow = snmpv2_smi_classes.mib_table_row
            MibTableColumn = snmpv2_smi_classes.mib_table_column
        else:
            self.logger.warning(
                "MIB symbols adapter missing load_snmpv2_smi_classes(); "
                "falling back to import_symbols"
            )
            mib_scalar, mib_scalar_instance, mib_table, mib_table_row, mib_table_column = (
                self.mib_builder.import_symbols(
                    "SNMPv2-SMI",
                    "MibScalar",
                    "MibScalarInstance",
                    "MibTable",
                    "MibTableRow",
                    "MibTableColumn",
                )
            )
            MibScalar = mib_scalar
            MibScalarInstance = mib_scalar_instance
            MibTable = mib_table
            MibTableRow = mib_table_row
            MibTableColumn = mib_table_column
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
