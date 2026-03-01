"""Build a canonical SNMP type registry by introspecting compiled MIB symbols."""

from __future__ import annotations

import argparse
import inspect
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    TypedDict,
    TypeGuard,
    cast,
)

import pysnmp.entity.engine as _engine
import pysnmp.proto.rfc1902 as _rfc1902
import pysnmp.smi.builder as _builder
from pysnmp_type_wrapper.constraint_parser import parse_constraints_from_repr as parse_constraints
from pysnmp_type_wrapper.pysnmp_rfc1902_adapter import PysnmpRfc1902Adapter

from app.interface_types import (
    HasDisplayHint,
    HasGetDisplayHint,
    HasNamedValues,
    HasSubtypeSpec,
    HasSyntax,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pysnmp_type_wrapper.raw_boundary_types import MibSymbolMap, SupportsBoundarySnmpEngine

    from app.types import JsonDict

# True ASN.1 base types (RFC 2578)
# These are the only fundamental types in ASN.1:
TRUE_ASN1_BASE_TYPES: set[str] = {
    "Integer",
    "OctetString",
    "ObjectIdentifier",
}

# SNMP application types that we expect to find in SNMPv2-SMI (RFC 2578).
# These are NOT ASN.1 base types - they are application-specific types built on top of ASN.1.
# This list is used as a fallback if dynamic discovery fails.
_EXPECTED_SNMPV2_SMI_TYPES: set[str] = {
    "Integer32",
    "Unsigned32",
    "Counter32",
    "Counter64",
    "Gauge32",
    "TimeTicks",
    "IpAddress",
    "Bits",
    "Opaque",
}

_MIN_RANGE_COUNT = 2


class TypeEntry(TypedDict):
    """Normalized metadata schema for one type entry in the generated registry."""

    base_type: str | None
    display_hint: str | None
    size: JsonDict | None
    constraints: list[JsonDict]
    constraints_repr: str | None
    enums: list[JsonDict] | None
    used_by: list[str]
    defined_in: str | None
    # True for abstract/structural types (CHOICE, aliases)
    # not used directly in OBJECT-TYPEs.
    abstract: bool


# Move all static/class methods and logic to TypeRecorder
class TypeRecorder:
    """Recorder that discovers and normalizes type metadata from compiled MIBs."""

    def __init__(
        self,
        compiled_dir: Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        """Create a recorder configured for a compiled-MIB directory."""
        self.compiled_dir = compiled_dir
        self._registry: dict[str, TypeEntry] | None = None
        self._snmpv2_smi_types: set[str] | None = None
        self._progress_callback = progress_callback
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _get_rfc1902_adapter() -> PysnmpRfc1902Adapter:
        return PysnmpRfc1902Adapter(_rfc1902)

    @staticmethod
    def _discover_snmpv2_smi_types() -> set[str]:
        """Dynamically discover SNMP application types from SNMPv2-SMI.

        Returns a set of type names that are classes (not instances) exported from SNMPv2-SMI.
        Falls back to expected types if discovery fails.

        Includes all types, even abstract ones (they'll be flagged as abstract separately).
        """
        try:
            adapter = TypeRecorder._get_rfc1902_adapter()
            discovered = set()
            for name, obj in adapter.iter_public_symbols():
                # We want classes that are likely SNMP types
                if inspect.isclass(obj) and (
                    adapter.has_attribute(obj, "subtypeSpec")
                    or name in TRUE_ASN1_BASE_TYPES
                    or name in _EXPECTED_SNMPV2_SMI_TYPES
                ):
                    discovered.add(name)

            # Ensure we at least have the ASN.1 base types and expected SNMP types
            return discovered | TRUE_ASN1_BASE_TYPES | _EXPECTED_SNMPV2_SMI_TYPES
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            # Fallback to expected types if discovery fails
            return TRUE_ASN1_BASE_TYPES | _EXPECTED_SNMPV2_SMI_TYPES

    def get_snmpv2_smi_types(self) -> set[str]:
        """Get the set of SNMP application types (cached)."""
        if self._snmpv2_smi_types is None:
            self._snmpv2_smi_types = self._discover_snmpv2_smi_types()
        return self._snmpv2_smi_types

    @staticmethod
    def infer_base_type_from_mro(syntax: object) -> str | None:
        """Infer the underlying SNMP application type from the class MRO.

        This is a static helper so it can be used without instantiating a TypeRecorder
        (useful in unit tests and simple type inspection).
        """
        cls = type(syntax)
        snmp_types = TypeRecorder._discover_snmpv2_smi_types()
        for base in cls.__mro__[1:]:
            name = base.__name__
            if name in snmp_types:
                return name
        return None

    @staticmethod
    def unwrap_syntax(syntax: object) -> tuple[str, str, object]:
        """Return syntax, base type, and base syntax object.

        (syntax_type_name, base_type_name, base_syntax_obj)

        - If syntax.getSyntax() exists and returns something, use that as base.
        - Otherwise infer base type from class inheritance (MRO).

        """
        syntax_type = syntax.__class__.__name__

        base_obj: object | None = None
        if isinstance(syntax, HasSyntax):
            try:
                base_obj = syntax.getSyntax()
            except TypeError:
                base_obj = None
        if base_obj is not None:
            return syntax_type, base_obj.__class__.__name__, base_obj

        inferred = TypeRecorder.infer_base_type_from_mro(syntax)
        if inferred is not None:
            return syntax_type, inferred, syntax

        return syntax_type, syntax_type, syntax

    @staticmethod
    def extract_display_hint(syntax: object) -> str | None:
        """Extract a display hint string from syntax metadata when present."""
        hint: str | None = None
        if isinstance(syntax, HasGetDisplayHint):
            try:
                hint = syntax.getDisplayHint()
            except TypeError:
                hint = None
        if hint is not None:
            text = hint.strip()
            return text or None

        for candidate in (syntax, type(syntax)):
            if not isinstance(candidate, HasDisplayHint):
                continue
            display_hint = candidate.displayHint
            if isinstance(display_hint, str):
                text = display_hint.strip()
                if text:
                    return text

        return None

    @staticmethod
    def extract_enums_list(syntax: object) -> list[JsonDict] | None:
        """Return enums as a numerically ordered list.

        [{"value": 1, "name": "true"}, {"value": 2, "name": "false"}]
        """
        candidates: list[Mapping[object, object]] = []
        if isinstance(syntax, HasNamedValues):
            candidates.append(syntax.namedValues)

        syntax_type = type(syntax)
        class_named_values = syntax_type.__dict__.get("namedValues")
        if isinstance(class_named_values, Mapping):
            candidates.append(class_named_values)

        for candidate in candidates:
            try:
                raw_pairs = candidate.items()
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).debug(
                    "Skipping enum extraction for candidate %r",
                    candidate,
                )
                continue

            pairs = list(raw_pairs)

            rows: list[JsonDict] = []
            for name, value in pairs:
                if isinstance(name, str) and isinstance(value, int):
                    rows.append({"value": value, "name": name})

            if rows:
                rows.sort(key=lambda r: cast("int", r["value"]))
                return rows

        return None

    @classmethod
    def parse_constraints_from_repr(
        cls, subtype_repr: str
    ) -> tuple[JsonDict | None, list[JsonDict]]:
        """Parse subtypeSpec repr text into normalized size/constraint structures."""
        return cast("tuple[JsonDict | None, list[JsonDict]]", parse_constraints(subtype_repr))

    @classmethod
    def extract_constraints(
        cls, syntax: object
    ) -> tuple[JsonDict | None, list[JsonDict], str | None]:
        """Extract normalized size/range constraints and optional repr text."""
        subtype_spec = syntax.subtypeSpec if isinstance(syntax, HasSubtypeSpec) else None
        if subtype_spec is None:
            return None, [], None
        repr_text = repr(subtype_spec)
        size, constraints = cls.parse_constraints_from_repr(repr_text)
        constraints_repr: str | None = None
        empty_markers = {
            "<ConstraintsIntersection object>",
            "<ConstraintsIntersection object, consts >",
        }
        if constraints and repr_text not in empty_markers:
            constraints_repr = repr_text
        return size, constraints, constraints_repr

    @staticmethod
    def _filter_constraints_by_size(
        size: JsonDict | None,
        constraints: list[JsonDict],
    ) -> list[JsonDict]:
        if size is None:
            return constraints

        size_type = size.get("type")
        if size_type == "range":
            s_min = size.get("min")
            s_max = size.get("max")
            if not isinstance(s_min, int) or not isinstance(s_max, int):
                return constraints

            filtered: list[JsonDict] = []
            for c in constraints:
                if c.get("type") != "ValueSizeConstraint":
                    filtered.append(c)
                    continue
                c_min = c.get("min")
                c_max = c.get("max")
                if c_min == s_min and c_max == s_max:
                    filtered.append(c)
            return filtered

        if size_type == "set":
            allowed = size.get("allowed")
            if not isinstance(allowed, list) or not all(isinstance(x, int) for x in allowed):
                return constraints

            allowed_set = set(cast("list[int]", allowed))
            filtered = []
            for c in constraints:
                if c.get("type") != "ValueSizeConstraint":
                    filtered.append(c)
                    continue
                c_min = c.get("min")
                c_max = c.get("max")
                if isinstance(c_min, int) and c_min == c_max and c_min in allowed_set:
                    filtered.append(c)
            return filtered

        return constraints

    @staticmethod
    def _compact_single_value_constraints_if_enums_present(
        constraints: list[JsonDict],
        enums: list[JsonDict] | None,
    ) -> list[JsonDict]:
        if not enums:
            return constraints

        out: list[JsonDict] = []
        for c in constraints:
            if c.get("type") != "SingleValueConstraint":
                out.append(c)
                continue

            values = c.get("values")
            if isinstance(values, list):
                out.append({"type": "SingleValueConstraint", "count": len(values)})
            else:
                out.append({"type": "SingleValueConstraint"})
        return out

    @staticmethod
    def _is_textual_convention_class(sym_obj: object) -> TypeGuard[type[object]]:
        """Check whether a symbol is a textual-convention class.

        Compiled MIB textual conventions appear in mibSymbols as classes
        (eg class DisplayString(TextualConvention, OctetString): ...)

        OBJECT-TYPEs appear as instances (eg MibScalar/MibTableColumn/etc).
        """
        if not inspect.isclass(sym_obj):
            return False

        try:
            # TextualConvention is not in pysnmp.proto.rfc1902, it's defined in compiled MIBs.
            # Check if 'TextualConvention' appears in the class's MRO by name.
            return any(base.__name__ == "TextualConvention" for base in sym_obj.__mro__)
        except (TypeError, AttributeError):
            return False

    @staticmethod
    def _is_textual_convention_symbol(sym_obj: object) -> bool:
        """Backward-compatible alias for textual-convention class detection."""
        return TypeRecorder._is_textual_convention_class(sym_obj)

    @staticmethod
    def _is_abstract_type(type_name: str, sym_obj: object = None) -> bool:
        """Determine if a type is abstract (structural/not used directly in OBJECT-TYPEs).

        Abstract types include:
        - CHOICE types (ObjectSyntax, SimpleSyntax, ApplicationSyntax)
        - Type aliases that add no constraints (ObjectName, NotificationName)
        - Null type

        Args:
            type_name: Name of the type
            sym_obj: Optional symbol object from MIB to inspect

        Returns:
            True if the type is abstract

        """
        # Check by name for known abstract types
        known_abstract = {
            "ObjectSyntax",  # ASN.1 CHOICE type
            "SimpleSyntax",  # ASN.1 CHOICE type
            "ApplicationSyntax",  # ASN.1 CHOICE type
            "ObjectName",  # Alias for ObjectIdentifier
            "NotificationName",  # Alias for ObjectIdentifier
            "Null",  # Not used in SNMP
        }

        if type_name in known_abstract:
            return True

        # Check if it's a CHOICE type by inspecting MRO
        # Use 'is not None' instead of truthiness to avoid triggering __bool__ on ASN.1 objects
        if sym_obj is not None:
            try:
                if inspect.isclass(sym_obj):
                    cls = cast("type", sym_obj)
                    mro_names = [base.__name__ for base in cls.__mro__]
                    if "Choice" in mro_names:
                        return True
            except (TypeError, AttributeError):
                pass

        return False

    @staticmethod
    def _canonicalise_constraints(
        size: JsonDict | None,
        constraints: list[JsonDict],
        enums: list[JsonDict] | None,
        constraints_repr: str | None,
        *,
        drop_repr: bool,
    ) -> tuple[JsonDict | None, list[JsonDict], str | None]:
        """Apply post-processing and drop potentially misleading repr text.

        Drops constraints_repr if it could
        be misleading relative to the structured constraints.
        """
        raw_constraints = list(constraints)

        constraints = TypeRecorder._compact_single_value_constraints_if_enums_present(
            constraints, enums
        )
        constraints = TypeRecorder._filter_constraints_by_size(size, constraints)

        if drop_repr:
            constraints_repr = None
        elif constraints != raw_constraints:
            # If we changed constraints, the raw PySNMP repr can now be misleading
            constraints_repr = None

        return size, constraints, constraints_repr

    @staticmethod
    def _infer_asn1_base_type(type_name: str, type_class: type) -> str:
        """Infer the ASN.1 base type from a type's MRO.

        Returns one of: 'INTEGER', 'OCTET STRING', 'OBJECT IDENTIFIER'
        """
        # Check MRO for ASN.1 base type indicators
        mro_names = [base.__name__ for base in type_class.__mro__]

        # Map based on what we find in the MRO
        if "OctetString" in mro_names:
            return "OCTET STRING"
        if "Integer" in mro_names or "Integer32" in mro_names:
            return "INTEGER"
        if "ObjectIdentifier" in mro_names:
            return "OBJECT IDENTIFIER"

        # Fallback: try to guess from type name
        type_lower = type_name.lower()
        if (
            "string" in type_lower
            or "bits" in type_lower
            or "opaque" in type_lower
            or "address" in type_lower
        ):
            return "OCTET STRING"
        if "object" in type_lower or "oid" in type_lower:
            return "OBJECT IDENTIFIER"
        return "INTEGER"  # Default fallback

    def _seed_base_types_impl(self) -> dict[str, TypeEntry]:
        """Create canonical entries for SNMP application types.

        from SNMPv2-SMI so later OBJECT-TYPE instances cannot accidentally tighten them
        (eg sysServices constraining Integer32 to 0..127).

        Set base_type to the actual ASN.1 base type (INTEGER, OCTET STRING, OBJECT IDENTIFIER).
        """
        seeded: dict[str, TypeEntry] = {}
        snmp_types = self.get_snmpv2_smi_types()
        adapter = self._get_rfc1902_adapter()

        for name in sorted(snmp_types):
            ctor = adapter.get_symbol(name)
            if ctor is None or not callable(ctor):
                continue
            try:
                syntax_obj = ctor()
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).debug(
                    "Skipping base type seeding for %s due to constructor error",
                    name,
                )
                continue

            size, constraints, constraints_repr = self.extract_constraints(syntax_obj)
            size, constraints, constraints_repr = self._canonicalise_constraints(
                size=size,
                constraints=constraints,
                enums=None,
                constraints_repr=constraints_repr,
                drop_repr=True,  # always drop repr for seeded base types
            )

            # Check if this is an abstract type
            is_abstract = self._is_abstract_type(name, ctor)

            # Infer the ASN.1 base type from the class MRO
            asn1_base_type = "INTEGER"  # Fallback
            if isinstance(ctor, type):
                asn1_base_type = self._infer_asn1_base_type(name, ctor)

            seeded[name] = {
                "base_type": asn1_base_type,  # Use ASN.1 base type instead of circular reference
                "display_hint": None,
                "size": size,
                "constraints": constraints,
                "constraints_repr": constraints_repr,
                "enums": None,
                "used_by": [],
                "defined_in": "SNMPv2-SMI",  # Base types are defined in SNMPv2-SMI
                "abstract": is_abstract,
            }

        return seeded

    @classmethod
    def _seed_base_types(cls) -> dict[str, TypeEntry]:
        """Class-level entry point for seeding base types for tests and callers.

        This creates a temporary TypeRecorder instance to perform seeding so callers
        can invoke _seed_base_types() without constructing an instance themselves.
        """
        tr = cls(Path())
        return tr._seed_base_types_impl()

    @staticmethod
    def _has_single_value_constraint(constraints: list[JsonDict]) -> bool:
        return any(c.get("type") == "SingleValueConstraint" for c in constraints)

    @staticmethod
    def _is_value_range_constraint(c: JsonDict) -> bool:
        return c.get("type") == "ValueRangeConstraint"

    @staticmethod
    def _value_range_tuple(constraint: JsonDict) -> tuple[int, int]:
        min_val = constraint["min"]
        max_val = constraint["max"]
        if isinstance(min_val, int) and isinstance(max_val, int):
            return min_val, max_val
        return int(str(min_val)), int(str(max_val))

    @staticmethod
    def _drop_dominated_value_ranges(
        constraints: list[JsonDict],
    ) -> list[JsonDict]:
        ranges = [
            TypeRecorder._value_range_tuple(c)
            for c in constraints
            if TypeRecorder._is_value_range_constraint(c)
        ]
        if len(ranges) < _MIN_RANGE_COUNT:
            return constraints
        dominated: set[tuple[int, int]] = set()
        for a_min, a_max in ranges:
            for b_min, b_max in ranges:
                if (a_min, a_max) == (b_min, b_max):
                    continue
                if a_min <= b_min and a_max >= b_max:
                    dominated.add((a_min, a_max))
        if not dominated:
            return constraints
        out: list[JsonDict] = []
        for c in constraints:
            if TypeRecorder._is_value_range_constraint(c):
                rng = TypeRecorder._value_range_tuple(c)
                if rng in dominated:
                    continue
            out.append(c)
        return out

    @staticmethod
    def _drop_redundant_base_value_range(
        base_type: str | None,
        constraints: list[JsonDict],
        types: Mapping[str, TypeEntry],
    ) -> list[JsonDict]:
        """Drop inherited ValueRangeConstraint if a stricter range exists in constraints.

        Only applies if base_type is known and both have ValueRangeConstraint.
        """
        if base_type is None:
            return constraints
        base_entry = types.get(base_type)
        if not base_entry:
            return constraints
        base_ranges = [
            TypeRecorder._value_range_tuple(c)
            for c in base_entry.get("constraints", [])
            if c.get("type") == "ValueRangeConstraint"
        ]
        if not base_ranges:
            return constraints
        # Find all ValueRangeConstraint in constraints
        value_ranges = [
            TypeRecorder._value_range_tuple(c)
            for c in constraints
            if c.get("type") == "ValueRangeConstraint"
        ]
        # If any range in constraints is strictly tighter than a base range, drop the base range
        out = []
        for c in constraints:
            if c.get("type") == "ValueRangeConstraint":
                rng = TypeRecorder._value_range_tuple(c)
                # If this is a base range and a tighter range exists, drop it
                if rng in base_ranges and any(
                    (rng != other and other[0] >= rng[0] and other[1] <= rng[1])
                    for other in value_ranges
                ):
                    continue
            out.append(c)
        return out

    @staticmethod
    def _drop_redundant_base_range_for_enums(
        base_type: str | None,
        constraints: list[JsonDict],
        enums: list[JsonDict] | None,
        types: Mapping[str, TypeEntry],
    ) -> list[JsonDict]:
        if base_type is None:
            return constraints
        if not enums and not TypeRecorder._has_single_value_constraint(constraints):
            return constraints
        base_entry = types.get(base_type)
        if not base_entry:
            return constraints
        base_ranges = {
            TypeRecorder._value_range_tuple(c)
            for c in base_entry.get("constraints", [])
            if TypeRecorder._is_value_range_constraint(c)
        }
        if not base_ranges:
            return constraints
        out = []
        for c in constraints:
            if TypeRecorder._is_value_range_constraint(c):
                rng = TypeRecorder._value_range_tuple(c)
                if rng in base_ranges:
                    continue
            out.append(c)
        return out

    def _load_mib_symbols(self) -> MibSymbolMap:
        snmp_engine = cast("SupportsBoundarySnmpEngine", _engine.SnmpEngine())
        mib_builder = snmp_engine.get_mib_builder()
        mib_builder.add_mib_sources(_builder.DirMibSource(str(self.compiled_dir)))

        for path in self.compiled_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            try:
                mib_builder.load_modules(path.stem)
            except Exception:  # noqa: BLE001
                self.logger.debug("Skipping unloadable compiled MIB %s", path.stem)

        return mib_builder.mibSymbols

    # pylint: disable=too-many-locals
    def _process_textual_convention_symbol(
        self,
        types: dict[str, TypeEntry],
        mib_name: str,
        sym_name: str,
        sym_obj: object,
    ) -> bool:
        if not self._is_textual_convention_class(sym_obj):
            return False

        tc_class = sym_obj

        base_type_name: str | None = None
        snmp_types = self.get_snmpv2_smi_types()
        for base in tc_class.__mro__[1:]:
            if base.__name__ in snmp_types:
                base_type_name = base.__name__
                break

        display_hint: str | None = None
        raw_display_hint = tc_class.__dict__.get("displayHint")
        if isinstance(raw_display_hint, str):
            text = raw_display_hint.strip()
            display_hint = text or None

        subtype_spec = tc_class.__dict__.get("subtypeSpec")
        tc_size: JsonDict | None = None
        tc_constraints: list[JsonDict] = []
        tc_constraints_repr: str | None = None
        if subtype_spec is not None:
            subtype_repr = repr(subtype_spec)
            tc_size, tc_constraints = self.parse_constraints_from_repr(subtype_repr)
            if tc_constraints or tc_size:
                tc_constraints_repr = subtype_repr

        if sym_name not in types:
            types[sym_name] = {
                "base_type": base_type_name,
                "display_hint": display_hint,
                "size": tc_size,
                "constraints": tc_constraints,
                "constraints_repr": tc_constraints_repr,
                "enums": None,
                "used_by": [],
                "defined_in": mib_name,
                "abstract": False,
            }
        elif types[sym_name]["defined_in"] is None:
            types[sym_name]["defined_in"] = mib_name
            if types[sym_name]["base_type"] is None and base_type_name is not None:
                types[sym_name]["base_type"] = base_type_name

        return True

    def _derive_symbol_metadata(
        self,
        syntax: object,
        base_obj: object,
        base_type_out: str | None,
        *,
        allow_metadata: bool,
    ) -> tuple[
        str | None,
        list[JsonDict] | None,
        JsonDict | None,
        list[JsonDict],
        str | None,
    ]:
        if not allow_metadata:
            return None, None, None, [], None

        display = self.extract_display_hint(syntax)
        size, constraints, constraints_repr = self.extract_constraints(syntax)

        if base_obj is not syntax:
            size2, constraints2, repr2 = self.extract_constraints(base_obj)
            if not constraints and constraints2:
                size, constraints, constraints_repr = size2, constraints2, repr2

        enums = self.extract_enums_list(syntax)
        if enums is None and base_obj is not syntax:
            enums = self.extract_enums_list(base_obj)

        size, constraints, constraints_repr = self._canonicalise_constraints(
            size=size,
            constraints=constraints,
            enums=enums,
            constraints_repr=constraints_repr,
            drop_repr=(base_type_out is not None),
        )

        return display, enums, size, constraints, constraints_repr

    # pylint: disable=too-many-locals
    def _process_object_type_symbol(
        self,
        types: dict[str, TypeEntry],
        mib_name: str,
        sym_name: str,
        sym_obj: object,
    ) -> None:  # pylint: disable=too-many-branches
        if not isinstance(sym_obj, HasSyntax):
            return
        try:
            syntax = sym_obj.getSyntax()
        except Exception:  # noqa: BLE001
            return

        if syntax is None:
            return

        t_name, base_type_raw, base_obj = self.unwrap_syntax(syntax)
        base_type_out: str | None = base_type_raw or None
        if (
            base_type_out is not None
            and base_type_out in types
            and types[base_type_out].get("base_type") is None
        ):
            base_type_out = None

        is_tc_def = self._is_textual_convention_class(sym_obj)
        is_application_type = t_name in self.get_snmpv2_smi_types()
        allow_metadata = is_tc_def or not is_application_type

        display, enums, size, constraints, constraints_repr = self._derive_symbol_metadata(
            syntax=syntax,
            base_obj=base_obj,
            base_type_out=base_type_out,
            allow_metadata=allow_metadata,
        )

        if base_type_out is not None and constraints:
            constraints = self._drop_redundant_base_value_range(
                base_type=base_type_out,
                constraints=constraints,
                types=types,
            )
            constraints = self._drop_dominated_value_ranges(constraints)
            constraints = self._drop_redundant_base_range_for_enums(
                base_type=base_type_out,
                constraints=constraints,
                enums=enums,
                types=types,
            )

        is_abstract = self._is_abstract_type(t_name, syntax)

        entry = types.setdefault(
            t_name,
            {
                "base_type": base_type_out,
                "display_hint": display,
                "size": size,
                "constraints": constraints,
                "constraints_repr": constraints_repr,
                "enums": enums,
                "used_by": [],
                "defined_in": None,
                "abstract": is_abstract,
            },
        )

        if is_tc_def and entry["defined_in"] is None:
            entry["defined_in"] = mib_name

        if entry["base_type"] is None and base_type_out is not None:
            entry["base_type"] = base_type_out

        if allow_metadata:
            if entry["display_hint"] is None and display is not None:
                entry["display_hint"] = display
            if entry["size"] is None and size is not None:
                entry["size"] = size
            if entry["enums"] is None and enums is not None:
                entry["enums"] = enums
            if entry["constraints_repr"] is None and constraints_repr is not None:
                entry["constraints_repr"] = constraints_repr
            if not entry["constraints"] and constraints:
                entry["constraints"] = constraints

        entry["used_by"].append(f"{mib_name}::{sym_name}")

    # pylint: enable=too-many-locals

    def build(self) -> None:
        """Build the full type registry by scanning all loaded compiled MIB symbols."""
        types: dict[str, TypeEntry] = self._seed_base_types()

        mib_symbols = self._load_mib_symbols()

        for mib_name, symbols in mib_symbols.items():
            if self._progress_callback:
                self._progress_callback(mib_name)

            for sym_name, sym_obj in symbols.items():
                if self._process_textual_convention_symbol(
                    types=types,
                    mib_name=mib_name,
                    sym_name=sym_name,
                    sym_obj=sym_obj,
                ):
                    continue

                self._process_object_type_symbol(
                    types=types,
                    mib_name=mib_name,
                    sym_name=sym_name,
                    sym_obj=sym_obj,
                )

        self._registry = types

    @property
    def registry(self) -> dict[str, TypeEntry]:
        """Return the built registry, raising if build has not run yet."""
        if self._registry is None:
            msg = "TypeRecorder: build() must be called before accessing registry."
            raise RuntimeError(msg)
        return self._registry

    def export_to_json(self, path: str = "types.json") -> None:
        """Persist the current registry to a JSON file at the provided path."""
        if self._registry is None:
            msg = "TypeRecorder: build() must be called before export."
            raise RuntimeError(msg)
        with Path(path).open("w", encoding="utf-8") as fh:
            json.dump(self._registry, fh, indent=2)


def main() -> None:
    """CLI entry point for generating a type registry JSON from compiled MIBs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("compiled_dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("types.json"))
    args = parser.parse_args()

    recorder = TypeRecorder(args.compiled_dir)
    recorder.build()
    recorder.export_to_json(str(args.output))
    logger.info("Wrote %d types to %s", len(recorder.registry), args.output)


if __name__ == "__main__":  # pragma: no cover
    main()
