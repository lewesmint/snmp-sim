from __future__ import annotations

import argparse
import inspect
import json
import re
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypedDict,
    cast,
)

import pysnmp.entity.engine as _engine
import pysnmp.proto.rfc1902 as _rfc1902
import pysnmp.smi.builder as _builder

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


class HasGetSyntax(Protocol):
    def getSyntax(self) -> object: ...


class TypeEntry(TypedDict):
    base_type: Optional[str]
    display_hint: Optional[str]
    size: Optional[JsonDict]
    constraints: List[JsonDict]
    constraints_repr: Optional[str]
    enums: Optional[List[JsonDict]]
    used_by: List[str]
    defined_in: Optional[str]
    abstract: bool  # True for abstract/structural types (CHOICE, aliases) not used directly in OBJECT-TYPEs


# Move all static/class methods and logic to TypeRecorder
class TypeRecorder:
    _SIZE_RE = re.compile(r"ValueSizeConstraint object, consts (\d+), (\d+)")
    _RANGE_RE = re.compile(r"ValueRangeConstraint object, consts ([-\d]+), ([-\d]+)")
    _SINGLE_RE = re.compile(r"SingleValueConstraint object, consts ([\d,\s-]+)")

    def __init__(
        self,
        compiled_dir: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        self.compiled_dir = compiled_dir
        self._registry: Optional[Dict[str, TypeEntry]] = None
        self._snmpv2_smi_types: Optional[set[str]] = None
        self._progress_callback = progress_callback

    @staticmethod
    def _discover_snmpv2_smi_types() -> set[str]:
        """
        Dynamically discover SNMP application types from SNMPv2-SMI.

        Returns a set of type names that are classes (not instances) exported from SNMPv2-SMI.
        Falls back to expected types if discovery fails.

        Includes all types, even abstract ones (they'll be flagged as abstract separately).
        """
        try:
            import inspect

            # Import from pysnmp.proto.rfc1902 which contains the compiled SNMPv2-SMI types
            discovered = set()
            for name in dir(_rfc1902):
                if name.startswith("_"):
                    continue
                obj = getattr(_rfc1902, name, None)
                if obj is None:
                    continue
                # We want classes that are likely SNMP types
                if inspect.isclass(obj):
                    # Check if it's a type we care about (has subtypeSpec or is a known type)
                    if (
                        hasattr(obj, "subtypeSpec")
                        or name in TRUE_ASN1_BASE_TYPES
                        or name in _EXPECTED_SNMPV2_SMI_TYPES
                    ):
                        discovered.add(name)

            # Ensure we at least have the ASN.1 base types and expected SNMP types
            result = discovered | TRUE_ASN1_BASE_TYPES | _EXPECTED_SNMPV2_SMI_TYPES
            return result
        except Exception:
            # Fallback to expected types if discovery fails
            return TRUE_ASN1_BASE_TYPES | _EXPECTED_SNMPV2_SMI_TYPES

    def get_snmpv2_smi_types(self) -> set[str]:
        """Get the set of SNMP application types (cached)."""
        if self._snmpv2_smi_types is None:
            self._snmpv2_smi_types = self._discover_snmpv2_smi_types()
        return self._snmpv2_smi_types

    @staticmethod
    def safe_call_zero_arg(obj: object, name: str) -> Optional[object]:
        fn_obj = getattr(obj, name, None)
        if not callable(fn_obj):
            return None
        fn = cast(Callable[..., object], fn_obj)
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return None
        required = [
            p
            for p in sig.parameters.values()
            if p.default is p.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if required:
            return None
        try:
            return fn()
        except TypeError:
            return None

    def infer_base_type_from_mro(self, syntax: object) -> Optional[str]:
        """
        If getSyntax() does not unwrap a TEXTUAL-CONVENTION, infer the underlying
        SNMP application type from the class MRO.

        Example compiled MIB:
          class ProductID(TextualConvention, ObjectIdentifier): ...
        """
        cls = type(syntax)
        snmp_types = self.get_snmpv2_smi_types()
        for base in cls.__mro__[1:]:
            name = base.__name__
            if name in snmp_types:
                return name
        return None

    def unwrap_syntax(self, syntax: object) -> Tuple[str, str, object]:
        """
        Returns:
          (syntax_type_name, base_type_name, base_syntax_obj)

        - If syntax.getSyntax() exists and returns something, use that as base.
        - Otherwise infer base type from class inheritance (MRO).
        """
        syntax_type = syntax.__class__.__name__

        base_obj = TypeRecorder.safe_call_zero_arg(syntax, "getSyntax")
        if base_obj is not None:
            return syntax_type, base_obj.__class__.__name__, base_obj

        inferred = self.infer_base_type_from_mro(syntax)
        if inferred is not None:
            return syntax_type, inferred, syntax

        return syntax_type, syntax_type, syntax

    @staticmethod
    def extract_display_hint(syntax: object) -> Optional[str]:
        hint = TypeRecorder.safe_call_zero_arg(syntax, "getDisplayHint")
        if hint is not None:
            text = str(hint).strip()
            return text or None

        for candidate in (
            getattr(syntax, "displayHint", None),
            getattr(type(syntax), "displayHint", None),
        ):
            if isinstance(candidate, str):
                text = candidate.strip()
                if text:
                    return text

        return None

    @staticmethod
    def extract_enums_list(syntax: object) -> Optional[List[JsonDict]]:
        """
        Return enums as a numerically ordered list:
          [{"value": 1, "name": "true"}, {"value": 2, "name": "false"}]
        """
        candidates = (
            getattr(syntax, "namedValues", None),
            getattr(type(syntax), "namedValues", None),
        )

        for candidate in candidates:
            if candidate is None:
                continue

            items = getattr(candidate, "items", None)
            if not callable(items):
                continue

            try:
                pairs = cast(Sequence[Tuple[object, object]], items())
            except Exception:
                continue

            rows: List[JsonDict] = []
            for name, value in pairs:
                if isinstance(name, str) and isinstance(value, int):
                    rows.append({"value": value, "name": name})

            if rows:
                rows.sort(key=lambda r: cast(int, r["value"]))
                return rows

        return None

    @classmethod
    def parse_constraints_from_repr(
        cls, subtype_repr: str
    ) -> Tuple[Optional[JsonDict], List[JsonDict]]:
        constraints: List[JsonDict] = []
        size_ranges: List[Tuple[int, int]] = []
        exact_sizes: List[int] = []
        for m in cls._SIZE_RE.finditer(subtype_repr):
            c_min = int(m.group(1))
            c_max = int(m.group(2))
            constraints.append(
                {"type": "ValueSizeConstraint", "min": c_min, "max": c_max}
            )
            size_ranges.append((c_min, c_max))
            if c_min == c_max:
                exact_sizes.append(c_min)
        for m in cls._RANGE_RE.finditer(subtype_repr):
            c_min = int(m.group(1))
            c_max = int(m.group(2))
            constraints.append(
                {"type": "ValueRangeConstraint", "min": c_min, "max": c_max}
            )
        for m in cls._SINGLE_RE.finditer(subtype_repr):
            raw = m.group(1)
            vals = [int(x.strip()) for x in raw.split(",") if x.strip()]
            constraints.append({"type": "SingleValueConstraint", "values": vals})
        # Deduplicate exact duplicates
        seen: set[Tuple[object, ...]] = set()
        deduped: List[JsonDict] = []
        for c in constraints:
            key: Tuple[object, ...] = (
                c.get("type"),
                c.get("min"),
                c.get("max"),
                tuple(cast(List[int], c.get("values", []))) if "values" in c else None,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        size: Optional[JsonDict] = None
        if exact_sizes:
            size = {"type": "set", "allowed": sorted(set(exact_sizes))}
            return size, deduped
        if size_ranges:
            mins = [mn for mn, _ in size_ranges]
            maxs = [mx for _, mx in size_ranges]
            eff_min = max(mins) if mins else 0
            eff_max = min(maxs) if maxs else 0
            if eff_min <= eff_max:
                size = {"type": "range", "min": eff_min, "max": eff_max}
            else:
                size = {
                    "type": "union",
                    "ranges": [{"min": mn, "max": mx} for mn, mx in size_ranges],
                }
        return size, deduped

    @classmethod
    def extract_constraints(
        cls, syntax: object
    ) -> Tuple[Optional[JsonDict], List[JsonDict], Optional[str]]:
        subtype_spec = getattr(syntax, "subtypeSpec", None)
        if subtype_spec is None:
            return None, [], None
        repr_text = repr(subtype_spec)
        size, constraints = cls.parse_constraints_from_repr(repr_text)
        constraints_repr: Optional[str] = None
        empty_markers = {
            "<ConstraintsIntersection object>",
            "<ConstraintsIntersection object, consts >",
        }
        if constraints and repr_text not in empty_markers:
            constraints_repr = repr_text
        return size, constraints, constraints_repr

    @staticmethod
    def _filter_constraints_by_size(
        size: Optional[JsonDict],
        constraints: List[JsonDict],
    ) -> List[JsonDict]:
        if size is None:
            return constraints

        size_type = size.get("type")
        if size_type == "range":
            s_min = size.get("min")
            s_max = size.get("max")
            if not isinstance(s_min, int) or not isinstance(s_max, int):
                return constraints

            filtered: List[JsonDict] = []
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
            if not isinstance(allowed, list) or not all(
                isinstance(x, int) for x in allowed
            ):
                return constraints

            allowed_set = set(cast(List[int], allowed))
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
        constraints: List[JsonDict],
        enums: Optional[List[JsonDict]],
    ) -> List[JsonDict]:
        if not enums:
            return constraints

        out: List[JsonDict] = []
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
    def _is_textual_convention_symbol(sym_obj: object) -> bool:
        """
        Compiled MIB textual conventions appear in mibSymbols as classes
        (eg class DisplayString(TextualConvention, OctetString): ...)

        OBJECT-TYPEs appear as instances (eg MibScalar/MibTableColumn/etc).
        """
        if not inspect.isclass(sym_obj):
            return False

        try:
            # TextualConvention is not in pysnmp.proto.rfc1902, it's defined in compiled MIBs.
            # Check if 'TextualConvention' appears in the class's MRO by name.
            cls = cast(type, sym_obj)
            return any(base.__name__ == "TextualConvention" for base in cls.__mro__)
        except (TypeError, AttributeError):
            return False

    @staticmethod
    def _is_abstract_type(type_name: str, sym_obj: object = None) -> bool:
        """
        Determine if a type is abstract (structural/not used directly in OBJECT-TYPEs).

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
        KNOWN_ABSTRACT = {
            "ObjectSyntax",  # ASN.1 CHOICE type
            "SimpleSyntax",  # ASN.1 CHOICE type
            "ApplicationSyntax",  # ASN.1 CHOICE type
            "ObjectName",  # Alias for ObjectIdentifier
            "NotificationName",  # Alias for ObjectIdentifier
            "Null",  # Not used in SNMP
        }

        if type_name in KNOWN_ABSTRACT:
            return True

        # Check if it's a CHOICE type by inspecting MRO
        # Use 'is not None' instead of truthiness to avoid triggering __bool__ on ASN.1 objects
        if sym_obj is not None:
            try:
                if inspect.isclass(sym_obj):
                    cls = cast(type, sym_obj)
                    mro_names = [base.__name__ for base in cls.__mro__]
                    if "Choice" in mro_names:
                        return True
            except (TypeError, AttributeError):
                pass

        return False

    @staticmethod
    def _canonicalise_constraints(
        size: Optional[JsonDict],
        constraints: List[JsonDict],
        enums: Optional[List[JsonDict]],
        constraints_repr: Optional[str],
        *,
        drop_repr: bool,
    ) -> Tuple[Optional[JsonDict], List[JsonDict], Optional[str]]:
        """
        Applies your post-processing rules and drops constraints_repr if it could
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
        """
        Infer the ASN.1 base type from a type's MRO.

        Returns one of: 'INTEGER', 'OCTET STRING', 'OBJECT IDENTIFIER'
        """
        # Check MRO for ASN.1 base type indicators
        mro_names = [base.__name__ for base in type_class.__mro__]

        # Map based on what we find in the MRO
        if "OctetString" in mro_names:
            return "OCTET STRING"
        elif "Integer" in mro_names or "Integer32" in mro_names:
            return "INTEGER"
        elif "ObjectIdentifier" in mro_names:
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
        elif "object" in type_lower or "oid" in type_lower:
            return "OBJECT IDENTIFIER"
        else:
            return "INTEGER"  # Default fallback

    def _seed_base_types(self) -> Dict[str, TypeEntry]:
        """
        Create canonical entries for SNMP application types from SNMPv2-SMI so later
        OBJECT-TYPE instances cannot accidentally tighten them
        (eg sysServices constraining Integer32 to 0..127).

        Set base_type to the actual ASN.1 base type (INTEGER, OCTET STRING, OBJECT IDENTIFIER).
        """
        seeded: Dict[str, TypeEntry] = {}
        snmp_types = self.get_snmpv2_smi_types()

        for name in sorted(snmp_types):
            ctor = getattr(_rfc1902, name, None)
            if ctor is None or not callable(ctor):
                continue
            try:
                syntax_obj = ctor()
            except Exception:
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
            if inspect.isclass(ctor):
                asn1_base_type = self._infer_asn1_base_type(name, ctor)
            else:
                asn1_base_type = "INTEGER"  # Fallback

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

    @staticmethod
    def _has_single_value_constraint(constraints: List[JsonDict]) -> bool:
        for c in constraints:
            if c.get("type") == "SingleValueConstraint":
                return True
        return False

    @staticmethod
    def _is_value_range_constraint(c: JsonDict) -> bool:
        return c.get("type") == "ValueRangeConstraint"

    @staticmethod
    def _drop_dominated_value_ranges(constraints: List[JsonDict]) -> List[JsonDict]:
        ranges: List[Tuple[int, int]] = []
        for c in constraints:
            if TypeRecorder._is_value_range_constraint(c):
                min_val = c["min"]
                max_val = c["max"]
                if isinstance(min_val, int) and isinstance(max_val, int):
                    ranges.append((min_val, max_val))
                else:
                    ranges.append((int(str(min_val)), int(str(max_val))))
        if len(ranges) < 2:
            return constraints
        dominated: set[Tuple[int, int]] = set()
        for a_min, a_max in ranges:
            for b_min, b_max in ranges:
                if (a_min, a_max) == (b_min, b_max):
                    continue
                if a_min <= b_min and a_max >= b_max:
                    dominated.add((a_min, a_max))
        if not dominated:
            return constraints
        out: List[JsonDict] = []
        for c in constraints:
            if TypeRecorder._is_value_range_constraint(c):
                min_val = c["min"]
                max_val = c["max"]
                if isinstance(min_val, int) and isinstance(max_val, int):
                    rng = (min_val, max_val)
                else:
                    rng = (int(str(min_val)), int(str(max_val)))
                if rng in dominated:
                    continue
            out.append(c)
        return out

    @staticmethod
    def _drop_redundant_base_value_range(
        base_type: Optional[str],
        constraints: List[JsonDict],
        types: Mapping[str, TypeEntry],
    ) -> List[JsonDict]:
        """
        Drop inherited ValueRangeConstraint if a stricter range exists in constraints.
        Only applies if base_type is known and both have ValueRangeConstraint.
        """
        if base_type is None:
            return constraints
        base_entry = types.get(base_type)
        if not base_entry:
            return constraints
        base_ranges = [
            (
                c["min"] if isinstance(c["min"], int) else int(str(c["min"])),
                c["max"] if isinstance(c["max"], int) else int(str(c["max"])),
            )
            for c in base_entry.get("constraints", [])
            if c.get("type") == "ValueRangeConstraint"
        ]
        if not base_ranges:
            return constraints
        # Find all ValueRangeConstraint in constraints
        value_ranges = [
            (
                c["min"] if isinstance(c["min"], int) else int(str(c["min"])),
                c["max"] if isinstance(c["max"], int) else int(str(c["max"])),
            )
            for c in constraints
            if c.get("type") == "ValueRangeConstraint"
        ]
        # If any range in constraints is strictly tighter than a base range, drop the base range
        out = []
        for c in constraints:
            if c.get("type") == "ValueRangeConstraint":
                min_val = c["min"]
                max_val = c["max"]
                if isinstance(min_val, int) and isinstance(max_val, int):
                    rng = (min_val, max_val)
                else:
                    rng = (int(str(min_val)), int(str(max_val)))
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
        base_type: Optional[str],
        constraints: List[JsonDict],
        enums: Optional[List[JsonDict]],
        types: Mapping[str, TypeEntry],
    ) -> List[JsonDict]:
        if base_type is None:
            return constraints
        if not enums and not TypeRecorder._has_single_value_constraint(constraints):
            return constraints
        base_entry = types.get(base_type)
        if not base_entry:
            return constraints
        base_ranges = {
            (
                c["min"] if isinstance(c["min"], int) else int(str(c["min"])),
                c["max"] if isinstance(c["max"], int) else int(str(c["max"])),
            )
            for c in base_entry.get("constraints", [])
            if TypeRecorder._is_value_range_constraint(c)
        }
        if not base_ranges:
            return constraints
        out = []
        for c in constraints:
            if TypeRecorder._is_value_range_constraint(c):
                min_val = c["min"]
                max_val = c["max"]
                if isinstance(min_val, int) and isinstance(max_val, int):
                    rng = (min_val, max_val)
                else:
                    rng = (int(str(min_val)), int(str(max_val)))
                if rng in base_ranges:
                    continue
            out.append(c)
        return out

    def build(self) -> None:
        types: Dict[str, TypeEntry] = self._seed_base_types()

        snmp_engine = cast(Any, _engine.SnmpEngine())
        mib_builder = cast(Any, snmp_engine.get_mib_builder())
        mib_builder.add_mib_sources(_builder.DirMibSource(str(self.compiled_dir)))

        for path in self.compiled_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            try:
                mib_builder.load_modules(path.stem)
            except Exception:
                continue

        mib_symbols = cast(Mapping[str, Mapping[str, object]], mib_builder.mibSymbols)

        for mib_name, symbols in mib_symbols.items():
            if self._progress_callback:
                self._progress_callback(mib_name)

            for sym_name, sym_obj in symbols.items():
                # First, check if this is a TEXTUAL-CONVENTION class definition
                is_tc_class = self._is_textual_convention_symbol(sym_obj)

                if is_tc_class:
                    # This is a TC class definition - extract type info from the class itself
                    tc_class = cast(type, sym_obj)

                    # Infer base type from the class MRO
                    base_type_name: Optional[str] = None
                    snmp_types = self.get_snmpv2_smi_types()
                    for base in tc_class.__mro__[1:]:  # Skip the TC class itself
                        if base.__name__ in snmp_types:
                            base_type_name = base.__name__
                            break

                    # Try to get display hint and constraints from class attributes
                    display_hint = getattr(tc_class, "displayHint", None)
                    if display_hint and not isinstance(display_hint, str):
                        display_hint = None

                    # Get subtypeSpec from class if available
                    subtype_spec = getattr(tc_class, "subtypeSpec", None)
                    tc_size: Optional[JsonDict] = None
                    tc_constraints: List[JsonDict] = []
                    tc_constraints_repr: Optional[str] = None
                    if subtype_spec is not None:
                        subtype_repr = repr(subtype_spec)
                        tc_size, tc_constraints = self.parse_constraints_from_repr(
                            subtype_repr
                        )
                        # Set constraints_repr if there are actual constraints
                        if tc_constraints or tc_size:
                            tc_constraints_repr = subtype_repr

                    if sym_name not in types:
                        # TEXTUAL-CONVENTIONs are concrete types, not abstract
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
                        # Update the defined_in field if not already set
                        types[sym_name]["defined_in"] = mib_name
                        # Also update base_type if not set
                        if (
                            types[sym_name]["base_type"] is None
                            and base_type_name is not None
                        ):
                            types[sym_name]["base_type"] = base_type_name
                    continue

                # Now process OBJECT-TYPE instances
                if not hasattr(sym_obj, "getSyntax"):
                    continue

                snmp_obj = cast(HasGetSyntax, sym_obj)
                try:
                    syntax = snmp_obj.getSyntax()
                except Exception:
                    continue

                if syntax is None:
                    continue

                t_name, base_type_raw, base_obj = self.unwrap_syntax(syntax)

                # Keep base_type even if it equals type name - plugins need it to match types.
                # For SNMP application types (Counter32, Integer32, etc.), base_type should be the same as t_name.
                # For TEXTUAL-CONVENTIONs, base_type will differ from t_name.
                base_type_out: Optional[str] = base_type_raw if base_type_raw else None

                is_tc_def = self._is_textual_convention_symbol(sym_obj)
                is_application_type = t_name in self.get_snmpv2_smi_types()

                allow_metadata = is_tc_def or not is_application_type

                display: Optional[str]
                enums: Optional[List[JsonDict]]
                size: Optional[JsonDict]
                constraints: List[JsonDict]
                constraints_repr: Optional[str]

                if not allow_metadata:
                    display = None
                    enums = None
                    size = None
                    constraints = []
                    constraints_repr = None
                else:
                    if base_type_out is None:
                        display = None
                        enums = None
                        size, constraints, constraints_repr = self.extract_constraints(
                            syntax
                        )
                    else:
                        display = self.extract_display_hint(syntax)

                        size, constraints, constraints_repr = self.extract_constraints(
                            syntax
                        )
                        if base_obj is not syntax:
                            size2, constraints2, repr2 = self.extract_constraints(
                                base_obj
                            )
                            if not constraints and constraints2:
                                size, constraints, constraints_repr = (
                                    size2,
                                    constraints2,
                                    repr2,
                                )

                        enums = self.extract_enums_list(syntax)
                        if enums is None and base_obj is not syntax:
                            enums = self.extract_enums_list(base_obj)

                    size, constraints, constraints_repr = (
                        self._canonicalise_constraints(
                            size=size,
                            constraints=constraints,
                            enums=enums,
                            constraints_repr=constraints_repr,
                            drop_repr=(base_type_out is not None),
                        )
                    )

                if base_type_out is not None and constraints:
                    constraints = self._drop_redundant_base_value_range(
                        base_type=base_type_out,
                        constraints=constraints,
                        types=types,
                    )
                    constraints = self._drop_dominated_value_ranges(constraints)
                    if base_type_out is not None:
                        constraints = self._drop_redundant_base_range_for_enums(
                            base_type=base_type_out,
                            constraints=constraints,
                            enums=enums,
                            types=types,
                        )

                # Check if this type is abstract (CHOICE types, aliases, etc.)
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

                # If this is a TEXTUAL-CONVENTION definition, record where it's defined
                if is_tc_def and entry["defined_in"] is None:
                    entry["defined_in"] = mib_name

                # Update base_type if it's not set (for TC placeholders)
                if entry["base_type"] is None and base_type_out is not None:
                    entry["base_type"] = base_type_out

                if allow_metadata:
                    if entry["display_hint"] is None and display is not None:
                        entry["display_hint"] = display
                    if entry["size"] is None and size is not None:
                        entry["size"] = size
                    if entry["enums"] is None and enums is not None:
                        entry["enums"] = enums

                    if (
                        entry["constraints_repr"] is None
                        and constraints_repr is not None
                    ):
                        entry["constraints_repr"] = constraints_repr
                    if not entry["constraints"] and constraints:
                        entry["constraints"] = constraints

                entry["used_by"].append(f"{mib_name}::{sym_name}")

        self._registry = types

    @property
    def registry(self) -> Dict[str, TypeEntry]:
        if self._registry is None:
            raise RuntimeError(
                "TypeRecorder: build() must be called before accessing registry."
            )
        return self._registry

    def export_to_json(self, path: str = "types.json") -> None:
        if self._registry is None:
            raise RuntimeError("TypeRecorder: build() must be called before export.")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self._registry, fh, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("compiled_dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("types.json"))
    args = parser.parse_args()

    recorder = TypeRecorder(args.compiled_dir)
    recorder.build()
    recorder.export_to_json(str(args.output))
    print(f"Wrote {len(recorder.registry)} types to {args.output}")


if __name__ == "__main__":
    main()
