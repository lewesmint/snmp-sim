"""Helper classes for MIB registration."""

from __future__ import annotations

import contextlib
import logging
import time
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

type ObjectType = Any
type WriteHookWrapper = Callable[..., None]


@dataclass(frozen=True)
class RegistrarCommonDeps:
    """Shared dependencies for registrar helpers."""

    logger: logging.Logger
    get_pysnmp_type: Callable[[str], ObjectType]
    normalize_access: Callable[[str], str]
    preferred_snmp_types: Callable[[], set[str]]
    decode_value: Callable[[ObjectType], ObjectType]
    encode_value: Callable[[ObjectType, str], ObjectType]
    write_hooks: RegistrarWriteHooks
    mib_builder: ObjectType


@dataclass(frozen=True)
class RegistrarScalarDeps:
    """Dependencies for scalar registration helpers."""

    mib_scalar_instance_cls: ObjectType
    start_time: float
    common: RegistrarCommonDeps


@dataclass(frozen=True)
class RegistrarTableDeps:
    """Dependencies for table registration helpers."""

    mib_scalar_instance_cls: ObjectType
    mib_table_cls: ObjectType
    mib_table_row_cls: ObjectType
    mib_table_column_cls: ObjectType
    common: RegistrarCommonDeps


class RegistrarValueDecoder:
    """Decode values encoded in schema JSON."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize decoder with logger."""
        self.logger = logger

    def decode_value(self, value: ObjectType) -> ObjectType:
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
                    return (
                        encoded_value.encode("utf-8").decode("unicode_escape").encode("latin1")
                    )
                self.logger.warning(
                    "%s",
                    f"Hex encoding expects string value, got {type(encoded_value)}",
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                self.logger.exception("Failed to decode hex value '%s'", encoded_value)
            return encoded_value

        self.logger.warning("Unknown encoding '%s', returning raw value", encoding)
        return encoded_value


class RegistrarWriteHooks:
    """Build and attach write hooks to MIB instances."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize hook builder with logger."""
        self.logger = logger

    @staticmethod
    def format_snmp_value(val: ObjectType) -> str:
        """Format a PySNMP value for logging."""
        if val is None:
            return "<none>"
        try:
            text = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            text = None
        if not text:
            try:
                if hasattr(val, "asOctets"):
                    octs = val.asOctets()
                    text = octs.decode("utf-8", errors="replace") if octs else "<empty-octets>"
                elif hasattr(val, "asNumbers"):
                    text = str(val.asNumbers())
                elif isinstance(val, (bytes, bytearray)):
                    text = val.decode("utf-8", errors="replace") or "<empty-bytes>"
                else:
                    text = repr(val)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                text = repr(val)
        return text or "<empty>"

    def build_write_commit_wrapper(
        self,
        dotted: str,
        friendly: str,
        is_writable: bool,
        original_write: ObjectType,
    ) -> WriteHookWrapper:
        """Build the writeCommit wrapper function."""
        registrar_logger = self.logger
        registrar_format = self.format_snmp_value

        def _write_commit_wrapper(
            inst_ref: ObjectType,
            *a: ObjectType,
            **kw: ObjectType,
        ) -> None:
            try:
                if original_write:
                    original_write(*a, **kw)
            except (AttributeError, LookupError, OSError, TypeError, ValueError, RuntimeError):
                pass

            try:
                if not is_writable:
                    registrar_logger.debug(
                        "Ignoring SET on read-only %s (%s)",
                        dotted,
                        friendly,
                    )
                    return

                old_val = getattr(inst_ref, "syntax", None)
                var_bind = a[0] if a else None
                new_val = None
                vb_oid = None
                vb_pair_len = 2

                if isinstance(var_bind, tuple) and len(var_bind) == vb_pair_len:
                    pair = tuple(var_bind)
                    vb_oid = pair[0]
                    new_val = pair[1]

                if new_val is not None:
                    with contextlib.suppress(
                        AttributeError, LookupError, OSError, TypeError, ValueError
                    ):
                        inst_ref.syntax = new_val

                if vb_oid is not None:
                    try:
                        vb_oid_tuple = tuple(int(x) for x in vb_oid)
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        vb_oid_tuple = None
                else:
                    vb_oid_tuple = None

                final_dotted = dotted
                if vb_oid_tuple:
                    final_dotted = ".".join(str(x) for x in vb_oid_tuple)

                registrar_logger.info(
                    "SNMP SET applied to %s (%s): old=%s new=%s",
                    final_dotted,
                    friendly,
                    registrar_format(old_val),
                    registrar_format(getattr(inst_ref, "syntax", None)),
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass

        return _write_commit_wrapper

    def build_write_test_wrapper(
        self,
        dotted: str,
        friendly: str,
        is_writable: bool,
    ) -> WriteHookWrapper:
        """Build the writeTest wrapper function."""
        registrar_logger = self.logger

        def _write_test_wrapper(
            _self: ObjectType,
            var_bind: ObjectType,
            **_context: ObjectType,
        ) -> None:
            if not is_writable:
                registrar_logger.debug(
                    "Rejecting SET (writeTest) on read-only %s (%s)",
                    dotted,
                    friendly,
                )
                error_msg = "notWritable"
                raise ValueError(error_msg)
            registrar_logger.debug("writeTest called for %s", var_bind)

        return _write_test_wrapper

    def attach_write_hooks(
        self,
        inst: ObjectType,
        dotted: str,
        friendly: str,
        *,
        is_writable: bool,
        original_write: ObjectType,
    ) -> None:
        """Attach write commit and write test hooks to an instance."""
        commit_wrapper = self.build_write_commit_wrapper(
            dotted, friendly, is_writable, original_write
        )
        inst.writeCommit = types.MethodType(commit_wrapper, inst)

        test_wrapper = self.build_write_test_wrapper(dotted, friendly, is_writable)
        inst.writeTest = types.MethodType(test_wrapper, inst)


class RegistrarScalarBuilder:
    """Build scalar MIB symbols."""

    def __init__(self, deps: RegistrarScalarDeps) -> None:
        """Initialize scalar builder with dependencies."""
        self.mib_scalar_instance_cls = deps.mib_scalar_instance_cls
        self.logger = deps.common.logger
        self.start_time = deps.start_time
        self._get_pysnmp_type = deps.common.get_pysnmp_type
        self._normalize_access = deps.common.normalize_access
        self._preferred_snmp_types = deps.common.preferred_snmp_types
        self._decode_value = deps.common.decode_value
        self._encode_value = deps.common.encode_value
        self._write_hooks = deps.common.write_hooks

    def iter_scalar_candidates(
        self,
        mib_json: dict[str, ObjectType],
        table_related_objects: set[str],
    ) -> Iterator[tuple[str, dict[str, ObjectType], str, tuple[int, ...]]]:
        """Iterate scalar candidates excluding table objects."""
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

            yield name, info, access or "read-only", oid_value

    def resolve_scalar_type_value(
        self,
        name: str,
        info: dict[str, ObjectType],
        type_registry: dict[str, ObjectType],
    ) -> tuple[str, str, object] | None:
        """Resolve scalar type metadata and initial value."""
        value = info.get("current") if "current" in info else info.get("initial")
        type_name = info.get("type")
        if not isinstance(type_name, str):
            self.logger.warning("Skipping %s: invalid type '%s'", name, type_name)
            return None

        type_info = type_registry.get(type_name, {})
        base_type_raw = type_info.get("base_type") or type_name

        if not isinstance(base_type_raw, str) or not base_type_raw:
            self.logger.warning("Skipping %s: invalid type '%s'", name, type_name)
            return None

        preferred_snmp_types = self._preferred_snmp_types()
        snmp_type_name: str = type_name if type_name in preferred_snmp_types else base_type_raw
        base_type: str = snmp_type_name

        if name == "sysUpTime":
            uptime_seconds = time.time() - self.start_time
            value = int(uptime_seconds * 100)

        value = self._decode_value(value)
        value = self._encode_value(value, base_type)

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
                    "Skipping %s: no value and no default for type '%s'", name, base_type
                )
                return None

        return snmp_type_name, base_type, value

    def attach_sysuptime_read_hook(self, scalar_inst: ObjectType, pysnmp_type: ObjectType) -> None:
        """Attach a dynamic read hook for sysUpTime."""
        original_read_get = getattr(scalar_inst, "readGet", None)
        registrar_start_time = self.start_time

        def _sysuptime_read_get(
            inst: ObjectType,
            *args: ObjectType,
            _start_time: float = registrar_start_time,
            _pysnmp_type: ObjectType = pysnmp_type,
            _original_read_get: ObjectType = original_read_get,
            **kwargs: ObjectType,
        ) -> ObjectType:
            uptime_seconds = time.time() - _start_time
            uptime_centiseconds = int(uptime_seconds * 100)
            inst.syntax = _pysnmp_type(uptime_centiseconds)
            if _original_read_get:
                return _original_read_get(*args, **kwargs)
            return inst.syntax

        scalar_inst.readGet = types.MethodType(_sysuptime_read_get, scalar_inst)

    def attach_scalar_read_logging_hook(
        self,
        scalar_inst: ObjectType,
        dotted: str,
        friendly: str,
    ) -> None:
        """Attach a readGet wrapper that logs scalar SNMP GET requests."""
        original_read_get = getattr(scalar_inst, "readGet", None)
        registrar_logger = self.logger
        registrar_format = self._write_hooks.format_snmp_value

        def _logged_read_get(
            inst: ObjectType,
            *args: ObjectType,
            _original_read_get: ObjectType = original_read_get,
            **kwargs: ObjectType,
        ) -> ObjectType:
            result = _original_read_get(*args, **kwargs) if _original_read_get else None
            current_value = result if result is not None else getattr(inst, "syntax", None)
            registrar_logger.info(
                "SNMP GET received for %s (%s): value=%s",
                dotted,
                friendly,
                registrar_format(current_value),
            )
            return result if result is not None else current_value

        scalar_inst.readGet = types.MethodType(_logged_read_get, scalar_inst)

    def build_scalar_instance(
        self,
        mib: str,
        name: str,
        scalar_context: tuple[tuple[int, ...], str],
        scalar_payload: tuple[str, ObjectType],
    ) -> tuple[ObjectType, str, str] | None:
        """Create a scalar instance and attach hooks."""
        try:
            oid_value, access = scalar_context
            snmp_type_name, value = scalar_payload
            pysnmp_type = self._get_pysnmp_type(snmp_type_name)
            if pysnmp_type is None:
                msg = f"Could not resolve type '{snmp_type_name}'"
                raise ImportError(msg)

            scalar_inst = self.mib_scalar_instance_cls(oid_value, (0,), pysnmp_type(value))

            max_access = self._normalize_access(access)
            scalar_inst.setMaxAccess(max_access)
            is_writable = max_access in ("readwrite", "readcreate")

            if name == "sysUpTime":
                self.attach_sysuptime_read_hook(scalar_inst, pysnmp_type)

            try:
                try:
                    dotted = ".".join(str(x) for x in scalar_inst.name)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    dotted = ".".join(str(x) for x in (*oid_value, 0))
                friendly = f"{mib}:{name}"
                self.attach_scalar_read_logging_hook(scalar_inst, dotted, friendly)
                original_write = getattr(scalar_inst, "writeCommit", None)
                self._write_hooks.attach_write_hooks(
                    inst=scalar_inst,
                    dotted=dotted,
                    friendly=friendly,
                    is_writable=is_writable,
                    original_write=original_write,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
            else:
                return scalar_inst, max_access, pysnmp_type.__name__
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            self.logger.exception("Error creating scalar %s", name)
            return None
        return None


class RegistrarTableBuilder:
    """Build table MIB symbols."""

    def __init__(self, deps: RegistrarTableDeps) -> None:
        """Initialize table builder with dependencies."""
        self.mib_scalar_instance_cls = deps.mib_scalar_instance_cls
        self.mib_table_cls = deps.mib_table_cls
        self.mib_table_row_cls = deps.mib_table_row_cls
        self.mib_table_column_cls = deps.mib_table_column_cls
        self.logger = deps.common.logger
        self._get_pysnmp_type = deps.common.get_pysnmp_type
        self._normalize_access = deps.common.normalize_access
        self._preferred_snmp_types = deps.common.preferred_snmp_types
        self._decode_value = deps.common.decode_value
        self._encode_value = deps.common.encode_value
        self._write_hooks = deps.common.write_hooks
        self.mib_builder = deps.common.mib_builder

    def resolve_table_entry(
        self,
        table_name: str,
        mib_json: dict[str, ObjectType],
    ) -> tuple[str, dict[str, ObjectType], tuple[int, ...], list[str]]:
        """Resolve the entry name and index data for a table."""
        entry_name: str | None = None
        entry_info: dict[str, ObjectType] | None = None
        entry_oid: tuple[int, ...] | None = None

        for obj_name, obj_info in mib_json.items():
            if isinstance(obj_info, dict) and obj_name.endswith("Entry"):
                obj_table_name = obj_name[:-5]
                if obj_table_name + "Table" == table_name:
                    entry_name = obj_name
                    entry_info = obj_info
                    entry_oid = tuple(obj_info.get("oid", []))
                    break

        if not entry_name or not entry_oid or entry_info is None:
            msg = f"No entry found for table {table_name}"
            raise ValueError(msg)

        raw_indexes = entry_info.get("indexes", [])
        if raw_indexes:
            index_names = [str(idx) for idx in raw_indexes if idx is not None]
        else:
            index_single = entry_info.get("index")
            index_names = [str(index_single)] if index_single is not None else []

        return entry_name, entry_info, entry_oid, index_names

    def collect_table_columns(
        self,
        mib_json: dict[str, ObjectType],
        entry_oid: tuple[int, ...],
        type_registry: dict[str, ObjectType],
        symbols: dict[str, ObjectType],
        mib: str = "",
    ) -> dict[str, tuple[tuple[int, ...], str, bool]]:
        """Collect and create table column symbols."""
        columns_by_name: dict[str, tuple[tuple[int, ...], str, bool]] = {}

        for col_name, col_info in mib_json.items():
            if not isinstance(col_info, dict):
                continue

            col_oid = tuple(col_info.get("oid", []))
            if not col_oid or len(col_oid) < len(entry_oid) + 1:
                continue
            if col_oid[: len(entry_oid)] != entry_oid:
                continue

            col_type_name = col_info.get("type")
            if not col_type_name:
                continue

            type_info = type_registry.get(col_type_name, {})
            base_type_raw = type_info.get("base_type") or col_type_name
            preferred = self._preferred_snmp_types()
            base_type = col_type_name if col_type_name in preferred else base_type_raw

            try:
                pysnmp_type = self._get_pysnmp_type(base_type)
                if pysnmp_type is None:
                    # If type not found and mib is provided, try importing from that mib
                    if mib:
                        try:
                            pysnmp_type = self.mib_builder.import_symbols(mib, col_type_name)[0]
                            self.logger.info(
                                "Found type %s in MIB %s for column %s",
                                col_type_name,
                                mib,
                                col_name,
                            )
                        except (
                            AttributeError,
                            ImportError,
                            IndexError,
                            LookupError,
                            OSError,
                            TypeError,
                            ValueError,
                        ) as e:
                            self.logger.warning(
                                "Failed to find type %s for column %s (tried %s and %s): %s",
                                col_type_name,
                                col_name,
                                base_type,
                                mib,
                                e,
                            )
                            continue
                    else:
                        self.logger.warning(
                            "Type %s for column %s not found and no mib provided",
                            col_type_name,
                            col_name,
                        )
                        continue

                col_access_raw = col_info.get("access", "read-only")
                col_access = self._normalize_access(col_access_raw)
                col_obj = self.mib_table_column_cls(col_oid, pysnmp_type()).setMaxAccess(col_access)
                col_is_writable = col_access in ("readwrite", "readcreate")
                symbols[col_name] = col_obj
                # Store the resolved base_type (not the original col_type_name)
                # so create_table_instance can find it.
                columns_by_name[col_name] = (col_oid, base_type, col_is_writable)
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
                self.logger.warning("Error creating column %s: %s", col_name, e)
                continue

        return columns_by_name

    def build_row_index_tuple(
        self,
        row_data: dict[str, ObjectType],
        index_names: list[str],
        columns_by_name: dict[str, tuple[tuple[int, ...], str, bool]],
        row_idx: int,
    ) -> tuple[int, ...]:
        """Build the index tuple for a table row."""
        index_components: list[int] = []
        for i, idx_name in enumerate(index_names):
            idx_value = row_data.get(idx_name, row_idx + 1 if i == 0 else 0)
            idx_type = "Integer32"
            if idx_name in columns_by_name:
                _, idx_type, _ = columns_by_name[idx_name]

            self.logger.info("Expanding index: %s value=%s type=%s", idx_name, idx_value, idx_type)
            components = self.expand_index_value_to_oid_components(idx_value, idx_type)
            self.logger.info("Expanded components for %s: %s", idx_name, components)
            index_components.extend(components)

        return tuple(index_components)

    @staticmethod
    def extract_row_values(row_data: dict[str, ObjectType]) -> dict[str, ObjectType]:
        """Extract row values payload from a row definition."""
        if "values" in row_data and isinstance(row_data.get("values"), dict):
            values = row_data.get("values")
            if isinstance(values, dict):
                return values
        return row_data

    @staticmethod
    def resolve_table_cell_value(
        col_name: str,
        row_values: dict[str, ObjectType],
        index_names: list[str],
        index_tuple: tuple[int, ...],
    ) -> tuple[bool, ObjectType | int]:
        """Resolve a cell value from row data or index tuple."""
        if col_name in row_values:
            return True, row_values[col_name]
        if col_name in index_names:
            idx_pos = index_names.index(col_name)
            return True, index_tuple[idx_pos]
        return False, 0

    def create_table_instance(
        self,
        mib: str,
        col_name: str,
        column_context: tuple[tuple[int, ...], str, bool],
        instance_context: tuple[tuple[int, ...], object],
    ) -> tuple[str, object, str] | None:
        """Create a table cell instance for a row/column."""
        col_oid, base_type, col_is_writable = column_context
        index_tuple, value = instance_context

        value = self._decode_value(value)
        value = self._encode_value(value, base_type)

        try:
            pysnmp_type = self._get_pysnmp_type(base_type)
            if pysnmp_type is None:
                # If type not found and mib is provided, try importing from that mib
                if mib:
                    try:
                        pysnmp_type = self.mib_builder.import_symbols(mib, base_type)[0]
                        self.logger.info(
                            "Found type %s in MIB %s for instance %s",
                            base_type,
                            mib,
                            col_name,
                        )
                    except (
                        AttributeError,
                        ImportError,
                        IndexError,
                        LookupError,
                        OSError,
                        TypeError,
                        ValueError,
                    ) as e:
                        self.logger.warning(
                            "Failed to find type %s for instance %s  in MIB %s: %s",
                            base_type,
                            col_name,
                            mib,
                            e,
                        )
                        return None
                else:
                    return None

            inst = self.mib_scalar_instance_cls(col_oid, index_tuple, pysnmp_type(value))
            inst_name = f"{col_name}Inst_{'_'.join(map(str, index_tuple))}"

            try:
                try:
                    dotted = ".".join(str(x) for x in inst.name)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    dotted = ".".join(str(x) for x in col_oid + index_tuple)
                friendly = f"{mib}:{col_name}"
                original_write = getattr(inst, "writeCommit", None)
                self._write_hooks.attach_write_hooks(
                    inst=inst,
                    dotted=dotted,
                    friendly=friendly,
                    is_writable=col_is_writable,
                    original_write=original_write,
                )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
            else:
                return inst_name, inst, pysnmp_type.__name__
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self.logger.warning(
                "Error creating instance for %s row %s: %s",
                col_name,
                index_tuple,
                e,
            )
            return None
        return None

    def expand_ipaddress_components(self, value: ObjectType) -> tuple[int, ...]:
        """Expand IpAddress value to OID components."""
        ip_parts_count = 4
        if isinstance(value, str):
            try:
                parts = [int(x) for x in value.split(".")]
                if len(parts) == ip_parts_count:
                    return tuple(parts)
            except (ValueError, AttributeError):
                pass
        # Fallback: treat as 0.0.0.0
        return (0, 0, 0, 0)

    def expand_string_components(self, value: ObjectType) -> tuple[int, ...]:
        """Expand string/bytes value to OID components."""
        if isinstance(value, str):
            return tuple(ord(c) for c in value)
        if isinstance(value, bytes):
            return tuple(value)
        if isinstance(value, int):
            return (value,)
        return ()

    def expand_integer_components(self, value: ObjectType) -> tuple[int, ...]:
        """Expand integer value to OID components."""
        try:
            return (int(value),)
        except (ValueError, TypeError):
            return (0,)

    def expand_index_value_to_oid_components(
        self,
        value: ObjectType,
        index_type: str,
    ) -> tuple[int, ...]:
        """Expand an index value into OID components based on its type."""
        normalized_index_type = str(index_type).strip().lower().replace(" ", "")

        # Handle IpAddress type - convert "a.b.c.d" to (a, b, c, d)
        if "ipaddress" in normalized_index_type:
            return self.expand_ipaddress_components(value)

        # Handle OctetString and DisplayString - convert to octets
        if normalized_index_type in ("octetstring", "displaystring", "physaddress"):
            return self.expand_string_components(value)

        # Handle integer types - simple single value
        if normalized_index_type in (
            "integer32",
            "unsigned32",
            "integer",
            "gauge32",
            "counter32",
            "timeticks",
        ):
            return self.expand_integer_components(value)

        # Default: try to convert to int, or use ASCII values if string
        try:
            return (int(value),)
        except (ValueError, TypeError):
            if isinstance(value, str):
                return tuple(ord(c) for c in value)
            return (0,)

    def process_table_rows(
        self,
        table_name: str,
        rows_data: list[ObjectType],
        index_names: list[str],
        columns_by_name: dict[str, tuple[tuple[int, ...], str, bool]],
        mib: str,
    ) -> dict[str, ObjectType]:
        """Process table rows and create row instances."""
        symbols = {}

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

            # Skip rows with sentinel values in raw data (sample/template data)
            if any(row_data.get(idx) == "default" for idx in index_names):
                continue

            index_tuple = self.build_row_index_tuple(
                row_data=row_data,
                index_names=index_names,
                columns_by_name=columns_by_name,
                row_idx=row_idx,
            )

            if table_name == "sysORTable":
                self.logger.info(
                    "sysORTable row %d raw=%s index_tuple=%s",
                    row_idx,
                    row_data,
                    index_tuple,
                )

            row_values = self.extract_row_values(row_data)

            for col_name, (col_oid, base_type, col_is_writable) in columns_by_name.items():
                has_value, value = self.resolve_table_cell_value(
                    col_name=col_name,
                    row_values=row_values,
                    index_names=index_names,
                    index_tuple=index_tuple,
                )
                if not has_value:
                    continue

                created = self.create_table_instance(
                    mib=mib,
                    col_name=col_name,
                    column_context=(col_oid, base_type, col_is_writable),
                    instance_context=(index_tuple, value),
                )
                if not created:
                    continue

                inst_name, inst, pysnmp_type_name = created
                symbols[inst_name] = inst

                try:
                    try:
                        inst_name_tuple = tuple(inst.name)  # type: ignore[attr-defined]
                    except (AttributeError, LookupError, OSError, TypeError, ValueError):
                        inst_name_tuple = tuple(col_oid + index_tuple)
                    self.logger.info("Registered instance %s -> %s", inst_name, inst_name_tuple)
                except (AttributeError, LookupError, OSError, TypeError, ValueError):
                    pass

                if table_name == "sysORTable":
                    self.logger.info(
                        "sysORTable cell %s[%s]=%r (type %s)",
                        col_name,
                        index_tuple,
                        value,
                        pysnmp_type_name,
                    )

        return symbols

    def build_table_symbols(
        self,
        mib: str,
        table_name: str,
        table_info: dict[str, ObjectType],
        mib_json: dict[str, ObjectType],
        type_registry: dict[str, ObjectType],
    ) -> dict[str, ObjectType]:
        """Build symbols for a single table (table, entry, columns, instances)."""
        symbols = {}

        entry_name, _entry_info, entry_oid, index_names = self.resolve_table_entry(
            table_name,
            mib_json,
        )

        # Get table OID; if missing, infer from entry OID (entry is table OID + .1)
        table_oid = tuple(table_info.get("oid", []))
        if not table_oid:
            inferred_table_oid = entry_oid[:-1] if entry_oid else ()
            if not inferred_table_oid:
                msg = f"Table {table_name} has no OID"
                raise ValueError(msg)
            table_oid = inferred_table_oid
            self.logger.warning(
                "Table %s missing OID in schema; inferred table OID %s from entry %s",
                table_name,
                table_oid,
                entry_name,
            )

        # Create table and entry objects
        table_obj = self.mib_table_cls(table_oid)
        symbols[table_name] = table_obj

        # Create entry with index specs
        index_specs = tuple((0, mib, idx_name) for idx_name in index_names)
        entry_obj = self.mib_table_row_cls(entry_oid).setIndexNames(*index_specs)
        symbols[entry_name] = entry_obj

        columns_by_name = self.collect_table_columns(
            mib_json=mib_json,
            entry_oid=entry_oid,
            type_registry=type_registry,
            symbols=symbols,
            mib=mib,
        )

        # Create row instances
        rows_data = table_info.get("rows", [])
        if not isinstance(rows_data, list):
            rows_data = []
        row_symbols = self.process_table_rows(
            table_name=table_name,
            rows_data=rows_data,
            index_names=index_names,
            columns_by_name=columns_by_name,
            mib=mib,
        )
        symbols.update(row_symbols)

        return symbols

    def find_table_related_objects(self, mib_json: dict[str, ObjectType]) -> set[str]:
        """Find all table-related object names."""
        table_related = set()

        for name, info in mib_json.items():
            if not isinstance(info, dict):
                continue

            if name.endswith(("Table", "Entry")):
                table_related.add(name)

                # Also mark columns as table-related
                if name.endswith("Entry"):
                    entry_oid = tuple(info.get("oid", []))
                    for col_name, col_info in mib_json.items():
                        if (
                            isinstance(col_info, dict)
                            and (col_oid := tuple(col_info.get("oid", [])))
                            and len(col_oid) > len(entry_oid)
                            and col_oid[: len(entry_oid)] == entry_oid
                        ):
                            table_related.add(col_name)

        return table_related
