from typing import Mapping, cast
from app.type_recorder import TypeRecorder, TypeEntry


def test_parse_constraints_from_repr_size_range_and_single() -> None:
    rep = (
        "ValueSizeConstraint object, consts 2, 4 "
        "ValueRangeConstraint object, consts 0, 10 "
        "SingleValueConstraint object, consts 1, 3, 5"
    )
    size, constraints = TypeRecorder.parse_constraints_from_repr(rep)
    assert isinstance(constraints, list)
    # size should be a range covering 2..4
    assert size == {"type": "range", "min": 2, "max": 4}
    # constraints should include the three types
    types = {c["type"] for c in constraints}
    assert "ValueSizeConstraint" in types
    assert "ValueRangeConstraint" in types
    assert "SingleValueConstraint" in types


def test_extract_constraints_with_subtypeobj() -> None:
    class S:
        def __repr__(self) -> str:
            return "ValueSizeConstraint object, consts 3, 3"

    class Syntax:
        subtypeSpec = S()

    size, constraints, reprt = TypeRecorder.extract_constraints(Syntax())
    assert size == {"type": "set", "allowed": [3]}
    assert any(c.get("type") == "ValueSizeConstraint" for c in constraints)
    assert reprt is not None


def test_filter_constraints_by_size_range_and_set() -> None:
    size_range = {"type": "range", "min": 1, "max": 5}
    constraints = [
        {"type": "ValueSizeConstraint", "min": 1, "max": 5},
        {"type": "ValueSizeConstraint", "min": 2, "max": 4},
    ]
    filtered = TypeRecorder._filter_constraints_by_size(size_range, constraints)
    # only exact matching 1..5 should remain
    assert any(c["min"] == 1 and c["max"] == 5 for c in filtered)

    size_set = {"type": "set", "allowed": [3, 4]}
    constraints2 = [
        {"type": "ValueSizeConstraint", "min": 3, "max": 3},
        {"type": "ValueSizeConstraint", "min": 4, "max": 4},
        {"type": "ValueSizeConstraint", "min": 5, "max": 5},
    ]
    filtered2 = TypeRecorder._filter_constraints_by_size(size_set, constraints2)
    assert all(
        c["min"] in (3, 4) for c in filtered2 if c["type"] == "ValueSizeConstraint"
    )


def test_compact_single_value_constraints_if_enums_present() -> None:
    constraints = [{"type": "SingleValueConstraint", "values": [1, 2, 3]}]
    enums = [{"value": 1, "name": "one"}]
    out = TypeRecorder._compact_single_value_constraints_if_enums_present(
        constraints, enums
    )
    assert out[0].get("count") == 3


def test_drop_dominated_value_ranges() -> None:
    constraints = [
        {"type": "ValueRangeConstraint", "min": 0, "max": 10},
        {"type": "ValueRangeConstraint", "min": 2, "max": 8},
        {"type": "ValueRangeConstraint", "min": 3, "max": 5},
    ]
    out = TypeRecorder._drop_dominated_value_ranges(constraints)
    # dominated ranges (0,10) should be removed
    assert not any(c["min"] == 0 and c["max"] == 10 for c in out)


def test_drop_redundant_base_value_range() -> None:
    base = "BaseType"
    types = {
        base: {"constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]}
    }
    constraints = [
        {"type": "ValueRangeConstraint", "min": 0, "max": 100},
        {"type": "ValueRangeConstraint", "min": 10, "max": 90},
    ]
    out = TypeRecorder._drop_redundant_base_value_range(
        base, constraints, cast(Mapping[str, TypeEntry], types)
    )
    # the broader base range should be dropped because a tighter range exists
    assert not any(c["min"] == 0 and c["max"] == 100 for c in out)


def test_drop_redundant_base_range_for_enums() -> None:
    base = "BaseType"
    types = {
        base: {"constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 5}]}
    }
    constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 5}]
    enums = [{"value": 1, "name": "one"}]
    out = TypeRecorder._drop_redundant_base_range_for_enums(
        base, constraints, enums, cast(Mapping[str, TypeEntry], types)
    )
    # since enums present, identical base range should be dropped
    assert out == []


def test_is_textual_convention_and_abstract_type_checks() -> None:
    class TextualConvention:
        pass

    class DisplayString(TextualConvention):
        pass

    assert TypeRecorder._is_textual_convention_symbol(DisplayString)

    class Choice:
        pass

    class SomeChoice(Choice):
        pass

    assert TypeRecorder._is_abstract_type("ObjectName")
    assert TypeRecorder._is_abstract_type("SomeChoice", SomeChoice)


def test_infer_asn1_base_type() -> None:
    class OctetString:
        pass

    class MyType(OctetString):
        pass

    assert TypeRecorder._infer_asn1_base_type("MyType", MyType) == "OCTET STRING"
