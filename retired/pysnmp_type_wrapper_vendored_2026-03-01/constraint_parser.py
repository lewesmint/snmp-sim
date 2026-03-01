"""Constraint parsing helpers for PySNMP subtypeSpec repr payloads."""

from __future__ import annotations

import re

_SIZE_RE = re.compile(r"ValueSizeConstraint object, consts (\d+), (\d+)")
_RANGE_RE = re.compile(r"ValueRangeConstraint object, consts ([-\d]+), ([-\d]+)")
_SINGLE_RE = re.compile(r"SingleValueConstraint object, consts ([\d,\s-]+)")

type ConstraintRecord = dict[str, object]
type SizeRecord = dict[str, object] | None


def parse_constraints_from_repr(  # pylint: disable=too-many-locals
    subtype_repr: str,
) -> tuple[SizeRecord, list[ConstraintRecord]]:
    """Parse subtypeSpec repr text into normalized size/constraint structures."""
    constraints: list[ConstraintRecord] = []
    size_ranges: list[tuple[int, int]] = []
    exact_sizes: list[int] = []

    for match in _SIZE_RE.finditer(subtype_repr):
        c_min = int(match.group(1))
        c_max = int(match.group(2))
        constraints.append({"type": "ValueSizeConstraint", "min": c_min, "max": c_max})
        size_ranges.append((c_min, c_max))
        if c_min == c_max:
            exact_sizes.append(c_min)

    for match in _RANGE_RE.finditer(subtype_repr):
        c_min = int(match.group(1))
        c_max = int(match.group(2))
        constraints.append({"type": "ValueRangeConstraint", "min": c_min, "max": c_max})

    for match in _SINGLE_RE.finditer(subtype_repr):
        raw = match.group(1)
        values = [int(part.strip()) for part in raw.split(",") if part.strip()]
        constraints.append({"type": "SingleValueConstraint", "values": values})

    seen: set[tuple[object, ...]] = set()
    deduped: list[ConstraintRecord] = []
    for constraint in constraints:
        values_obj = constraint.get("values")
        values_key: tuple[int, ...] | None = None
        if isinstance(values_obj, list) and all(isinstance(v, int) for v in values_obj):
            values_key = tuple(values_obj)

        key: tuple[object, ...] = (
            constraint.get("type"),
            constraint.get("min"),
            constraint.get("max"),
            values_key,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(constraint)

    size: SizeRecord = None
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
