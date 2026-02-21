"""
Unit tests for TypeRecorder module.
"""

from pathlib import Path
from typing import Any, List, TypedDict, Dict, cast
from types import SimpleNamespace
import pytest

from app.type_recorder import TypeRecorder

JsonDict = Dict[str, object]


class ValueRangeConstraintDict(TypedDict, total=False):
    """Type definition for a value range constraint dictionary."""

    type: str
    min: int | None
    max: int | None


class ValueSizeConstraintDict(TypedDict, total=False):
    """Type definition for a value size constraint dictionary."""

    type: str
    size: int | None


class SingleValueConstraintDict(TypedDict, total=False):
    """Type definition for a single value constraint dictionary."""

    type: str
    values: List[Any]


class TypeEntryDict(TypedDict, total=False):
    """Type definition for a type registry entry dictionary."""

    base_type: str | None
    display_hint: str | None
    size: int | None
    constraints: List[
        ValueRangeConstraintDict | ValueSizeConstraintDict | SingleValueConstraintDict
    ]
    constraints_repr: str | None
    enums: dict[str, int] | None
    defined_in: str | None
    abstract: bool | None
    used_by: List[str]


class TestSafeCallZeroArg:
    """Test safe_call_zero_arg static method"""

    def test_not_callable(self, mocker: Any) -> None:
        """If attribute is not callable, return None"""
        obj = mocker.Mock()
        obj.method = "not a function"
        result = TypeRecorder.safe_call_zero_arg(obj, "method")
        assert result is None

    def test_missing_attribute(self, mocker: Any) -> None:
        """If attribute does not exist, return None"""
        obj = mocker.Mock(spec=[])
        result = TypeRecorder.safe_call_zero_arg(obj, "missing")
        assert result is None

    def test_signature_inspection_fails(self, mocker: Any) -> None:
        """If signature inspection fails, return None"""
        obj = mocker.Mock()
        obj.method = mocker.Mock(side_effect=TypeError("inspection failed"))

        # Make inspect.signature fail
        mocker.patch("inspect.signature", side_effect=TypeError)
        result = TypeRecorder.safe_call_zero_arg(obj, "method")
        assert result is None

    def test_required_parameters(self, mocker: Any) -> None:
        """If method requires parameters, return None"""
        obj = mocker.Mock()

        def requires_param(x: Any) -> Any:
            return x

        obj.method = requires_param
        result = TypeRecorder.safe_call_zero_arg(obj, "method")
        assert result is None

    def test_call_raises_type_error(self, mocker: Any) -> None:
        """If call raises TypeError, return None"""
        obj = mocker.Mock()
        obj.method = mocker.Mock(side_effect=TypeError("bad call"))
        result = TypeRecorder.safe_call_zero_arg(obj, "method")
        assert result is None

    def test_successful_zero_arg_call(self, mocker: Any) -> None:
        """If method is callable with no args, return result"""
        obj = mocker.Mock()
        obj.method = mocker.Mock(return_value="success")
        result = TypeRecorder.safe_call_zero_arg(obj, "method")
        assert result == "success"


class TestInferBaseTypeFromMRO:
    """Test infer_base_type_from_mro static method"""

    def test_finds_known_base_type(self, mocker: Any) -> None:
        """Should find ASN1 base type in MRO"""
        # Create a type dynamically with proper __name__
        OctetString = type("OctetString", (), {})
        CustomType = type("CustomType", (OctetString,), {})

        instance = CustomType()
        result = TypeRecorder.infer_base_type_from_mro(instance)
        assert result == "OctetString"

    def test_no_known_base_type(self, mocker: Any) -> None:
        """Should return None if no known base type in MRO"""
        UnknownType = type("UnknownType", (), {})

        instance = UnknownType()
        result = TypeRecorder.infer_base_type_from_mro(instance)
        assert result is None


class TestUnwrapSyntax:
    """Test unwrap_syntax static method"""

    def test_with_get_syntax(self, mocker: Any) -> None:
        """Should use getSyntax() if available"""
        BaseType = type("Integer32", (), {})

        def get_syntax_impl(_self: Any) -> Any:
            return BaseType()

        DisplayString = type("DisplayString", (), {"getSyntax": get_syntax_impl})

        syntax = DisplayString()
        syntax_type, base_type, base_obj = TypeRecorder.unwrap_syntax(syntax)
        assert syntax_type == "DisplayString"
        assert base_type == "Integer32"
        assert isinstance(base_obj, BaseType)

    def test_without_get_syntax(self, mocker: Any) -> None:
        """Should infer from MRO if getSyntax not available"""
        Counter32 = type("Counter32", (), {})
        CustomCounter = type("CustomCounter", (Counter32,), {})

        syntax = CustomCounter()
        syntax_type, base_type, base_obj = TypeRecorder.unwrap_syntax(syntax)
        assert syntax_type == "CustomCounter"
        assert base_type == "Counter32"
        assert base_obj is syntax

    def test_no_base_type(self, mocker: Any) -> None:
        """Should return syntax_type for both if no base found"""

        class UnknownType:
            __name__ = "UnknownType"

        syntax = UnknownType()
        syntax_type, base_type, base_obj = TypeRecorder.unwrap_syntax(syntax)
        assert syntax_type == "UnknownType"
        assert base_type == "UnknownType"
        assert base_obj is syntax


class TestExtractDisplayHint:
    """Test extract_display_hint static method"""

    def test_from_get_display_hint_method(self, mocker: Any) -> None:
        """Should extract from getDisplayHint() method"""
        syntax = mocker.Mock()
        syntax.getDisplayHint = mocker.Mock(return_value="1x:")
        result = TypeRecorder.extract_display_hint(syntax)
        assert result == "1x:"

    def test_from_instance_attribute(self, mocker: Any) -> None:
        """Should extract from instance displayHint attribute"""
        syntax = mocker.Mock()
        syntax.getDisplayHint = mocker.Mock(return_value=None)
        syntax.displayHint = "2d-1d-1d,1d:1d:1d.1d,1a1d:1d"
        result = TypeRecorder.extract_display_hint(syntax)
        assert result == "2d-1d-1d,1d:1d:1d.1d,1a1d:1d"

    def test_from_class_attribute(self, mocker: Any) -> None:
        """Should extract from class displayHint attribute"""

        class CustomType:
            displayHint = "255a"

        syntax = CustomType()
        result = TypeRecorder.extract_display_hint(syntax)
        assert result == "255a"

    def test_empty_string(self, mocker: Any) -> None:
        """Should return None for empty display hint"""
        syntax = mocker.Mock()
        syntax.getDisplayHint = mocker.Mock(return_value="")
        result = TypeRecorder.extract_display_hint(syntax)
        assert result is None

    def test_no_display_hint(self, mocker: Any) -> None:
        """Should return None if no display hint found"""
        syntax = mocker.Mock(spec=[])
        result = TypeRecorder.extract_display_hint(syntax)
        assert result is None

    def test_instance_blank_class_non_blank(self, mocker: Any) -> None:
        """Should skip blank instance displayHint and use class value"""

        class CustomType:
            displayHint = "1x:"

        syntax = CustomType()
        syntax.displayHint = "   "

        result = TypeRecorder.extract_display_hint(syntax)
        assert result == "1x:"


class TestExtractEnumsList:
    """Test extract_enums_list static method"""

    def test_from_named_values(self, mocker: Any) -> None:
        """Should extract enums from namedValues"""
        named_values = mocker.Mock()
        named_values.items = mocker.Mock(
            return_value=[("active", 1), ("notInService", 2), ("notReady", 3)]
        )

        syntax = mocker.Mock()
        syntax.namedValues = named_values

        result = TypeRecorder.extract_enums_list(syntax)
        assert result == [
            {"value": 1, "name": "active"},
            {"value": 2, "name": "notInService"},
            {"value": 3, "name": "notReady"},
        ]

    def test_sorts_by_value(self, mocker: Any) -> None:
        """Should sort enums by value"""
        named_values = mocker.Mock()
        named_values.items = mocker.Mock(
            return_value=[("down", 2), ("up", 1), ("testing", 3)]
        )

        syntax = mocker.Mock()
        syntax.namedValues = named_values

        result = TypeRecorder.extract_enums_list(syntax)
        assert result is not None
        assert [e["value"] for e in result] == [1, 2, 3]

    def test_no_named_values(self, mocker: Any) -> None:
        """Should return None if no namedValues"""
        syntax = mocker.Mock(spec=[])
        result = TypeRecorder.extract_enums_list(syntax)
        assert result is None

    def test_named_values_not_callable(self, mocker: Any) -> None:
        """Should return None if namedValues.items not callable"""
        syntax = mocker.Mock()
        syntax.namedValues = mocker.Mock()
        syntax.namedValues.items = "not callable"
        result = TypeRecorder.extract_enums_list(syntax)
        assert result is None

    def test_items_raises_exception(self, mocker: Any) -> None:
        """Should return None if items() raises exception"""
        named_values = mocker.Mock()
        named_values.items = mocker.Mock(side_effect=Exception("error"))

        syntax = mocker.Mock()
        syntax.namedValues = named_values

        result = TypeRecorder.extract_enums_list(syntax)
        assert result is None

    def test_invalid_types_in_pairs(self, mocker: Any) -> None:
        """Should skip invalid pairs"""
        named_values = mocker.Mock()
        named_values.items = mocker.Mock(
            return_value=[("valid", 1), (123, "invalid"), ("another", 2)]
        )

        syntax = mocker.Mock()
        syntax.namedValues = named_values

        result = TypeRecorder.extract_enums_list(syntax)
        assert result == [
            {"value": 1, "name": "valid"},
            {"value": 2, "name": "another"},
        ]

    def test_from_class_named_values(self, mocker: Any) -> None:
        """Should extract from class namedValues if instance has none"""

        class CustomType:
            class NamedValues:
                @staticmethod
                def items() -> List[tuple[str, int]]:
                    return [("true", 1), ("false", 2)]

            namedValues = NamedValues()

        syntax = CustomType()
        result = TypeRecorder.extract_enums_list(syntax)
        assert result is not None
        assert len(result) == 2


class TestParseConstraintsFromRepr:
    """Test parse_constraints_from_repr class method"""

    def test_value_size_constraint(self) -> None:
        """Should parse ValueSizeConstraint"""
        repr_text = "ValueSizeConstraint object, consts 0, 255"
        _size, constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert len(constraints) == 1
        assert constraints[0] == {"type": "ValueSizeConstraint", "min": 0, "max": 255}

    def test_value_range_constraint(self) -> None:
        """Should parse ValueRangeConstraint"""
        repr_text = "ValueRangeConstraint object, consts 0, 127"
        _size, constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert len(constraints) == 1
        assert constraints[0] == {"type": "ValueRangeConstraint", "min": 0, "max": 127}

    def test_single_value_constraint(self) -> None:
        """Should parse SingleValueConstraint"""
        repr_text = "SingleValueConstraint object, consts 1, 2, 3"
        _size, constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert len(constraints) == 1
        assert constraints[0] == {"type": "SingleValueConstraint", "values": [1, 2, 3]}

    def test_exact_size_creates_size_set(self) -> None:
        """Should create size set for exact sizes"""
        repr_text = "ValueSizeConstraint object, consts 6, 6"
        size, _constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert size == {"type": "set", "allowed": [6]}

    def test_multiple_size_ranges_creates_size_range(self) -> None:
        """Should create size range from multiple ranges"""
        repr_text = "ValueSizeConstraint object, consts 1, 64 ValueSizeConstraint object, consts 0, 32"
        size, _constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert size is not None
        assert size["type"] == "range"
        assert size["min"] == 1  # max of mins
        assert size["max"] == 32  # min of maxs

    def test_conflicting_ranges_creates_union(self) -> None:
        """Should create union for conflicting ranges"""
        repr_text = "ValueSizeConstraint object, consts 10, 20 ValueSizeConstraint object, consts 30, 40"
        size, _constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        # eff_min (30) > eff_max (20), so should create union
        assert size is not None
        assert size["type"] == "union"

    def test_deduplicates_constraints(self) -> None:
        """Should deduplicate exact duplicates"""
        repr_text = "ValueRangeConstraint object, consts 0, 100 ValueRangeConstraint object, consts 0, 100"
        _size, constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert len(constraints) == 1

    def test_negative_range(self) -> None:
        """Should handle negative ranges"""
        repr_text = "ValueRangeConstraint object, consts -100, 100"
        _size, constraints = TypeRecorder.parse_constraints_from_repr(repr_text)
        assert constraints[0] == {
            "type": "ValueRangeConstraint",
            "min": -100,
            "max": 100,
        }


class TestExtractConstraints:
    """Test extract_constraints class method"""

    def test_no_subtype_spec(self, mocker: Any) -> None:
        """Should return empty if no subtypeSpec"""
        syntax = mocker.Mock(spec=[])
        size, constraints, repr_text = TypeRecorder.extract_constraints(syntax)
        assert size is None
        assert constraints == []
        assert repr_text is None

    def test_with_constraints(self, mocker: Any) -> None:
        """Should extract constraints from subtypeSpec"""

        class FakeSubtypeSpec:
            def __repr__(self) -> str:
                return "ValueRangeConstraint object, consts 1, 100"

        syntax = mocker.Mock()
        syntax.subtypeSpec = FakeSubtypeSpec()

        _size, constraints, repr_text = TypeRecorder.extract_constraints(syntax)
        assert len(constraints) == 1
        assert constraints[0]["type"] == "ValueRangeConstraint"
        assert repr_text == "ValueRangeConstraint object, consts 1, 100"

    def test_empty_constraints_intersection(self, mocker: Any) -> None:
        """Should not set repr_text for empty constraint markers"""

        class FakeSubtypeSpec:
            def __repr__(self) -> str:
                return "<ConstraintsIntersection object>"

        syntax = mocker.Mock()
        syntax.subtypeSpec = FakeSubtypeSpec()

        _size, constraints, repr_text = TypeRecorder.extract_constraints(syntax)
        assert constraints == []
        assert repr_text is None


class TestFilterConstraintsBySize:
    """Test _filter_constraints_by_size static method"""

    def test_no_size_returns_unchanged(self) -> None:
        """Should return constraints unchanged if no size"""
        constraints = [{"type": "ValueSizeConstraint", "min": 0, "max": 255}]
        result = TypeRecorder._filter_constraints_by_size(None, constraints)
        assert result == constraints

    def test_filters_by_range_size(self) -> None:
        """Should filter constraints matching range size"""
        size = {"type": "range", "min": 1, "max": 64}
        constraints = [
            {"type": "ValueSizeConstraint", "min": 1, "max": 64},
            {"type": "ValueSizeConstraint", "min": 0, "max": 255},
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
        ]
        result = TypeRecorder._filter_constraints_by_size(size, constraints)
        assert len(result) == 2
        assert constraints[0] in result  # matching size kept
        assert constraints[2] in result  # non-size constraint kept

    def test_filters_by_set_size(self) -> None:
        """Should filter constraints matching set size"""
        size = cast(dict[str, object], {"type": "set", "allowed": [6, 8]})
        constraints = [
            {"type": "ValueSizeConstraint", "min": 6, "max": 6},
            {"type": "ValueSizeConstraint", "min": 10, "max": 10},
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
        ]
        result = TypeRecorder._filter_constraints_by_size(size, constraints)
        assert len(result) == 2
        assert constraints[0] in result  # in allowed set
        assert constraints[2] in result  # non-size constraint kept

    def test_invalid_size_type_returns_unchanged(self) -> None:
        """Should return constraints unchanged for invalid size format"""
        size = cast(
            dict[str, object], {"type": "range", "min": "not an int", "max": "also not"}
        )
        constraints = [{"type": "ValueSizeConstraint", "min": 0, "max": 255}]
        result = TypeRecorder._filter_constraints_by_size(size, constraints)
        assert result == constraints

    def test_invalid_set_allowed_returns_unchanged(self) -> None:
        """Should return constraints unchanged for invalid set"""
        size = cast(dict[str, object], {"type": "set", "allowed": "not a list"})
        constraints = [{"type": "ValueSizeConstraint", "min": 6, "max": 6}]
        result = TypeRecorder._filter_constraints_by_size(size, constraints)
        assert result == constraints

    def test_unknown_size_type_returns_unchanged(self) -> None:
        """Should return constraints unchanged for unknown size type"""
        size = cast(
            dict[str, object], {"type": "union", "ranges": [{"min": 1, "max": 2}]}
        )
        constraints = [{"type": "ValueSizeConstraint", "min": 1, "max": 2}]
        result = TypeRecorder._filter_constraints_by_size(size, constraints)
        assert result == constraints


class TestCompactSingleValueConstraintsIfEnumsPresent:
    """Test _compact_single_value_constraints_if_enums_present static method"""

    def test_no_enums_returns_unchanged(self) -> None:
        """Should return constraints unchanged if no enums"""
        constraints: list[dict[str, object]] = [
            {"type": "SingleValueConstraint", "values": [1, 2, 3]}
        ]
        result = TypeRecorder._compact_single_value_constraints_if_enums_present(
            constraints, None
        )
        assert result == constraints

    def test_compacts_single_value_with_enums(self) -> None:
        """Should compact SingleValueConstraint when enums present"""
        constraints: list[dict[str, object]] = [
            {"type": "SingleValueConstraint", "values": [1, 2, 3, 4]}
        ]
        enums = [{"value": 1, "name": "a"}, {"value": 2, "name": "b"}]
        result = TypeRecorder._compact_single_value_constraints_if_enums_present(
            constraints, enums
        )
        assert result == [{"type": "SingleValueConstraint", "count": 4}]

    def test_keeps_non_single_value_constraints(self) -> None:
        """Should keep non-SingleValueConstraint unchanged"""
        constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
            {"type": "SingleValueConstraint", "values": [1, 2]},
        ]
        enums = [{"value": 1, "name": "a"}]
        result = TypeRecorder._compact_single_value_constraints_if_enums_present(
            constraints, enums
        )
        assert result[0] == constraints[0]
        assert result[1] == {"type": "SingleValueConstraint", "count": 2}

    def test_single_value_without_list_values(self) -> None:
        """Should compact SingleValueConstraint when values is not a list"""
        constraints: list[dict[str, object]] = [
            {"type": "SingleValueConstraint", "values": "1"}
        ]
        enums = [{"value": 1, "name": "a"}]
        result = TypeRecorder._compact_single_value_constraints_if_enums_present(
            constraints, enums
        )
        assert result == [{"type": "SingleValueConstraint"}]


class TestIsTextualConventionSymbol:
    """Test _is_textual_convention_symbol static method"""

    def test_not_a_class(self, mocker: Any) -> None:
        """Should return False for non-class objects"""
        obj = mocker.Mock()
        result = TypeRecorder._is_textual_convention_symbol(obj)
        assert result is False

    def test_class_with_textual_convention(self) -> None:
        """Should return True for class with TextualConvention in MRO"""

        class TextualConvention:
            pass

        class DisplayString(TextualConvention):
            pass

        result = TypeRecorder._is_textual_convention_symbol(DisplayString)
        assert result is True

    def test_class_without_textual_convention(self) -> None:
        """Should return False for class without TextualConvention"""

        class RegularClass:
            pass

        result = TypeRecorder._is_textual_convention_symbol(RegularClass)
        assert result is False

    def test_class_mro_access_raises(self) -> None:
        """Should return False if MRO access raises errors"""

        class BadMeta(type):
            def __getattribute__(self, name: str) -> Any:
                if name == "__mro__":
                    raise AttributeError("boom")
                return super().__getattribute__(name)

        class BadClass(metaclass=BadMeta):
            pass

        result = TypeRecorder._is_textual_convention_symbol(BadClass)
        assert result is False


class TestCanonicaliseConstraints:
    """Test _canonicalise_constraints static method"""

    def test_drops_repr_when_requested(self) -> None:
        """Should drop constraints_repr when drop_repr=True"""
        size = None
        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        constraints_repr = "some repr"

        _result_size, _result_constraints, result_repr = (
            TypeRecorder._canonicalise_constraints(
                size, constraints, None, constraints_repr, drop_repr=True
            )
        )
        assert result_repr is None

    def test_keeps_repr_when_unchanged(self) -> None:
        """Should keep constraints_repr when constraints unchanged"""
        size = None
        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        constraints_repr = "original repr"

        _result_size, _result_constraints, result_repr = (
            TypeRecorder._canonicalise_constraints(
                size, constraints, None, constraints_repr, drop_repr=False
            )
        )
        assert result_repr == "original repr"

    def test_drops_repr_when_constraints_changed(self) -> None:
        """Should drop constraints_repr when constraints are modified"""
        size = None
        constraints: list[dict[str, object]] = [
            {"type": "SingleValueConstraint", "values": [1, 2, 3]}
        ]
        enums = [{"value": 1, "name": "a"}]
        constraints_repr = "original"

        # The compact function will change constraints
        _result_size, _result_constraints, result_repr = (
            TypeRecorder._canonicalise_constraints(
                size, constraints, enums, constraints_repr, drop_repr=False
            )
        )
        # Should drop repr since constraints were compacted
        assert result_repr is None


class TestSeedBaseTypes:
    """Test _seed_base_types class method"""

    def test_creates_entries_for_base_types(self, mocker: Any) -> None:
        """Should create entries for all ASN1 base types"""
        mock_rfc = mocker.patch("app.type_recorder._rfc1902")
        # mocker.Mock constructors for base types
        for name in ["Integer32", "OctetString", "Counter32"]:
            mock_obj = mocker.Mock()
            mock_obj.subtypeSpec = None
            setattr(mock_rfc, name, mocker.Mock(return_value=mock_obj))

        seeded = TypeRecorder._seed_base_types()

        # Should have entries
        assert isinstance(seeded, dict)
        # Each entry should have the required structure
        for entry in seeded.values():
            assert "base_type" in entry
            assert "display_hint" in entry
            assert "size" in entry
            assert "constraints" in entry
            assert "constraints_repr" in entry
            assert "enums" in entry
            assert "used_by" in entry

    def test_skips_unavailable_types(self, mocker: Any) -> None:
        """Should skip base types that aren't available in rfc1902"""
        mock_rfc = mocker.patch("app.type_recorder._rfc1902")
        # Only provide some base types
        mock_obj = mocker.Mock()
        mock_obj.subtypeSpec = None
        mock_rfc.Integer32 = mocker.Mock(return_value=mock_obj)
        # Others will be None or missing

        seeded = TypeRecorder._seed_base_types()
        # Should only have the available ones
        assert isinstance(seeded, dict)

    def test_handles_constructor_exceptions(self, mocker: Any) -> None:
        """Should skip types whose constructor raises exceptions"""
        mock_rfc = mocker.patch("app.type_recorder._rfc1902")
        mock_rfc.Integer32 = mocker.Mock(side_effect=Exception("construction failed"))

        seeded = TypeRecorder._seed_base_types()
        # Should not crash, should skip this type
        assert isinstance(seeded, dict)

    def test_skips_non_callable_or_missing_constructor(self, mocker: Any) -> None:
        """Should skip base types with no callable constructor"""
        mock_obj = mocker.Mock()
        mock_obj.subtypeSpec = None
        fake_rfc = SimpleNamespace(Integer32=mocker.Mock(return_value=mock_obj))

        mocker.patch("app.type_recorder._rfc1902", new=fake_rfc)
        seeded = TypeRecorder._seed_base_types()

        assert "Integer32" in seeded
        assert "OctetString" not in seeded


class TestDropDominatedValueRanges:
    """Test _drop_dominated_value_ranges static method"""

    def test_drops_dominated_range(self) -> None:
        """Should drop ranges dominated by others"""
        constraints = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
            {"type": "ValueRangeConstraint", "min": 10, "max": 50},
        ]
        result = TypeRecorder._drop_dominated_value_ranges(constraints)
        # The wider range (0, 100) should be dropped
        assert len(result) == 1
        assert result[0]["min"] == 10

    def test_keeps_non_range_constraints(self) -> None:
        """Should keep non-ValueRangeConstraint unchanged"""
        constraints = [
            {"type": "ValueSizeConstraint", "min": 0, "max": 255},
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
        ]
        result = TypeRecorder._drop_dominated_value_ranges(constraints)
        assert constraints[0] in result

    def test_no_domination_keeps_all(self) -> None:
        """Should keep all ranges if none dominated"""
        constraints = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 50},
            {"type": "ValueRangeConstraint", "min": 51, "max": 100},
        ]
        result = TypeRecorder._drop_dominated_value_ranges(constraints)
        assert len(result) == 2

    def test_handles_string_min_max(self) -> None:
        """Should handle string min/max values"""
        constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": "0", "max": "100"},
            {"type": "ValueRangeConstraint", "min": "10", "max": "50"},
        ]
        result = TypeRecorder._drop_dominated_value_ranges(constraints)
        # Should convert strings to ints and process
        assert len(result) == 1
        assert result[0]["min"] == "10"

    def test_dominated_and_non_dominated_ranges(self) -> None:
        """Should drop dominated range and keep non-dominated ranges"""
        constraints = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
            {"type": "ValueRangeConstraint", "min": 10, "max": 50},
            {"type": "ValueRangeConstraint", "min": 200, "max": 300},
        ]
        result = TypeRecorder._drop_dominated_value_ranges(constraints)
        assert len(result) == 2
        assert result[0]["min"] in {10, 200}


class TestDropRedundantBaseValueRange:
    """Test _drop_redundant_base_value_range static method"""

    def test_no_base_type_returns_unchanged(self) -> None:
        """Should return constraints unchanged if no base type"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        types: Mapping[str, TypeEntry] = {}
        result = TypeRecorder._drop_redundant_base_value_range(None, constraints, types)
        assert result == constraints

    def test_drops_redundant_base_range(self) -> None:
        """Should drop base range when stricter range exists"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        base_constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100}
        ]
        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": base_constraints,
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }

        constraints = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},  # from base
            {"type": "ValueRangeConstraint", "min": 0, "max": 50},  # stricter
        ]

        result = TypeRecorder._drop_redundant_base_value_range(
            "Integer32", constraints, types
        )
        # Should drop the base range since stricter exists
        assert len(result) == 1
        assert result[0]["max"] == 50

    def test_base_entry_missing_returns_unchanged(self) -> None:
        """Should return constraints unchanged if base entry not found"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        types: Mapping[str, TypeEntry] = {}
        result = TypeRecorder._drop_redundant_base_value_range(
            "Missing", constraints, types
        )
        assert result == constraints

    def test_string_min_max_base_range_dropped(self) -> None:
        """Should drop base range with string min/max when tighter range exists"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        base_constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": "0", "max": "100"}
        ]
        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": base_constraints,
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }

        constraints: List[JsonDict] = [
            {"type": "ValueRangeConstraint", "min": "0", "max": "100"},
            {"type": "ValueRangeConstraint", "min": 0, "max": 50},
        ]

        result = TypeRecorder._drop_redundant_base_value_range(
            "Integer32", constraints, types
        )
        assert len(result) == 1
        assert result[0]["max"] == 50


class TestDropRedundantBaseRangeForEnums:
    """Test _drop_redundant_base_range_for_enums static method"""

    def test_no_base_type_returns_unchanged(self) -> None:
        """Should return constraints unchanged if no base type"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        types: Mapping[str, TypeEntry] = {}
        result = TypeRecorder._drop_redundant_base_range_for_enums(
            None, constraints, None, types
        )
        assert result == constraints

    def test_drops_base_range_with_enums(self) -> None:
        """Should drop base range when enums present"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        base_constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100}
        ]
        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": base_constraints,
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }

        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        enums = [{"value": 1, "name": "a"}, {"value": 2, "name": "b"}]

        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Integer32", constraints, enums, types
        )
        assert len(result) == 0

    def test_drops_base_range_with_single_value_constraint(self) -> None:
        """Should drop base range when SingleValueConstraint present"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        base_constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100}
        ]
        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": base_constraints,
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }

        constraints: list[dict[str, object]] = [
            {"type": "ValueRangeConstraint", "min": 0, "max": 100},
            {"type": "SingleValueConstraint", "values": [1, 2, 3]},
        ]

        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Integer32", constraints, None, types
        )
        # Should drop the base range
        assert len(result) == 1
        assert result[0]["type"] == "SingleValueConstraint"

    def test_base_entry_missing_returns_unchanged(self) -> None:
        """Should return constraints unchanged if base entry not found"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        types: Mapping[str, TypeEntry] = {}
        enums = [{"value": 1, "name": "a"}]
        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Missing", constraints, enums, types
        )
        assert result == constraints

    def test_base_ranges_empty_returns_unchanged(self) -> None:
        """Should return constraints unchanged if base ranges empty"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": [{"type": "ValueSizeConstraint", "min": 1, "max": 1}],
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }
        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        enums = [{"value": 1, "name": "a"}]
        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Integer32", constraints, enums, types
        )
        assert result == constraints

    def test_string_min_max_base_range_dropped(self) -> None:
        """Should drop base range with string min/max when enums present"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": [
                    {"type": "ValueRangeConstraint", "min": "0", "max": "100"}
                ],
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }
        constraints: List[JsonDict] = [
            {"type": "ValueRangeConstraint", "min": "0", "max": "100"}
        ]
        enums = [{"value": 1, "name": "a"}]

        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Integer32", constraints, enums, types
        )
        assert len(result) == 0

    def test_base_range_not_dropped_when_not_matching(self) -> None:
        """Should keep ranges not in base ranges"""
        from typing import Mapping
        from app.type_recorder import TypeEntry

        types: Mapping[str, TypeEntry] = {
            "Integer32": {
                "base_type": None,
                "display_hint": None,
                "size": None,
                "constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 100}],
                "constraints_repr": None,
                "enums": None,
                "defined_in": None,
                "abstract": False,
                "used_by": [],
            }
        }
        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 50}]
        enums = [{"value": 1, "name": "a"}]

        result = TypeRecorder._drop_redundant_base_range_for_enums(
            "Integer32", constraints, enums, types
        )
        assert result == constraints


class TestHasSingleValueConstraint:
    """Test _has_single_value_constraint static method"""

    def test_returns_true_when_present(self) -> None:
        """Should return True when SingleValueConstraint present"""
        constraints: list[dict[str, object]] = [
            {"type": "SingleValueConstraint", "values": [1, 2, 3]}
        ]
        result = TypeRecorder._has_single_value_constraint(constraints)
        assert result is True

    def test_returns_false_when_absent(self) -> None:
        """Should return False when no SingleValueConstraint"""
        constraints = [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]
        result = TypeRecorder._has_single_value_constraint(constraints)
        assert result is False

    def test_returns_false_for_empty(self) -> None:
        """Should return False for empty constraints"""
        result = TypeRecorder._has_single_value_constraint([])
        assert result is False


class TestIsValueRangeConstraint:
    """Test _is_value_range_constraint static method"""

    def test_returns_true_for_value_range(self) -> None:
        """Should return True for ValueRangeConstraint"""
        c = {"type": "ValueRangeConstraint", "min": 0, "max": 100}
        result = TypeRecorder._is_value_range_constraint(c)
        assert result is True

    def test_returns_false_for_other_types(self) -> None:
        """Should return False for other constraint types"""
        c = {"type": "ValueSizeConstraint", "min": 0, "max": 255}
        result = TypeRecorder._is_value_range_constraint(c)
        assert result is False


class TestBuild:
    """Test build method"""

    def test_build_processes_mibs(self, mocker: Any) -> None:
        """Should process MIB files and build type registry"""
        compiled_dir = Path("/fake/compiled")
        recorder = TypeRecorder(compiled_dir)

        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")
        mock_glob = mocker.patch.object(Path, "glob")

        # Setup mocks
        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder

        # mocker.Mock glob to return no files (simplest case)
        mock_glob.return_value = []

        recorder.build()

        # Should have built registry (even if empty)
        assert recorder._registry is not None

    def test_build_handles_load_failure(self, mocker: Any) -> None:
        """Should handle MIB load failures gracefully"""
        compiled_dir = Path("/fake/compiled")
        recorder = TypeRecorder(compiled_dir)

        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")
        mock_glob = mocker.patch.object(Path, "glob")

        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {}
        mock_mib_builder.load_modules.side_effect = Exception("load failed")
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder

        fake_mib = mocker.Mock()
        fake_mib.name = "TEST-MIB.py"
        fake_mib.stem = "TEST-MIB"
        mock_glob.return_value = [fake_mib]

        # Should not crash
        recorder.build()
        assert recorder._registry is not None

    def test_build_skips_init_py(self, tmp_path: Path, mocker: Any) -> None:
        """Should skip __init__.py when loading MIBs"""
        compiled_dir = tmp_path
        (compiled_dir / "__init__.py").write_text("# init")
        (compiled_dir / "TEST-MIB.py").write_text("# mib")

        recorder = TypeRecorder(compiled_dir)

        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")

        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder

        recorder.build()

        called = [call.args[0] for call in mock_mib_builder.load_modules.call_args_list]
        assert "__init__" not in called
        assert "TEST-MIB" in called

    def test_build_updates_metadata_fields(self, mocker: Any) -> None:
        """Should update entry metadata fields when available"""
        compiled_dir = Path("/fake/compiled")
        recorder = TypeRecorder(compiled_dir)

        class DummySubtype:
            def __init__(self, text: str) -> None:
                self._text = text

            def __repr__(self) -> str:
                return self._text

        class NamedValues:
            @staticmethod
            def items() -> list[tuple[str, int]]:
                return [("one", 1)]

        class Integer32:
            def __init__(self) -> None:
                self.subtypeSpec = DummySubtype(
                    "ValueSizeConstraint object, consts 4, 4"
                )
                self.namedValues = NamedValues()

        class CustomType:
            def __init__(self) -> None:
                self.subtypeSpec = DummySubtype("<ConstraintsIntersection object>")
                self.namedValues = None

            def getSyntax(self) -> object:
                return Integer32()

            def getDisplayHint(self) -> str:
                return "1x:"

        class Symbol:
            def __init__(self) -> None:
                self._syntax = CustomType()

            def getSyntax(self) -> object:
                return self._syntax

        base_entry: TypeEntryDict = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 100}],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }
        custom_entry: TypeEntryDict = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }

        mocker.patch.object(
            TypeRecorder,
            "_seed_base_types",
            return_value={"Integer32": base_entry, "CustomType": custom_entry},
        )
        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")
        mock_glob = mocker.patch.object(Path, "glob")

        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"sym": Symbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        mock_glob.return_value = []

        recorder.build()

        entry = recorder.registry["CustomType"]
        assert entry["display_hint"] == "1x:"
        assert entry["size"] == {"type": "set", "allowed": [4]}
        assert entry["enums"] == [{"value": 1, "name": "one"}]
        assert entry["constraints"]

    def test_build_base_obj_constraints_empty_falls_through(self, mocker: Any) -> None:
        """Should fall through when base_obj constraints are empty"""
        compiled_dir = Path("/fake/compiled")
        recorder = TypeRecorder(compiled_dir)

        class DummySubtype:
            def __init__(self, text: str) -> None:
                self._text = text

            def __repr__(self) -> str:
                return self._text

        class Integer32:
            def __init__(self) -> None:
                self.subtypeSpec = DummySubtype("<ConstraintsIntersection object>")
                self.namedValues = None

        class CustomType:
            def __init__(self) -> None:
                self.subtypeSpec = DummySubtype("<ConstraintsIntersection object>")
                self.namedValues = None

            def getSyntax(self) -> object:
                return Integer32()

        class Symbol:
            def __init__(self) -> None:
                self._syntax = CustomType()

            def getSyntax(self) -> object:
                return self._syntax

        custom_entry: TypeEntryDict = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }

        mocker.patch.object(
            TypeRecorder, "_seed_base_types", return_value={"CustomType": custom_entry}
        )
        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")
        mock_glob = mocker.patch.object(Path, "glob")

        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"sym": Symbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        mock_glob.return_value = []

        recorder.build()

        entry = recorder.registry["CustomType"]
        assert entry["constraints"] == []

    def test_build_base_type_out_none_keeps_constraints_repr(self, mocker: Any) -> None:
        """Should keep constraints_repr when base_type_out is None"""
        compiled_dir = Path("/fake/compiled")
        recorder = TypeRecorder(compiled_dir)

        class DummySubtype:
            def __init__(self, text: str) -> None:
                self._text = text

            def __repr__(self) -> str:
                return self._text

        class CustomNoBase:
            def __init__(self) -> None:
                self.subtypeSpec = DummySubtype(
                    "ValueRangeConstraint object, consts 0, 10"
                )

        class Symbol:
            def __init__(self) -> None:
                self._syntax = CustomNoBase()

            def getSyntax(self) -> object:
                return self._syntax

        custom_entry: TypeEntryDict = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }

        mocker.patch.object(
            TypeRecorder,
            "_seed_base_types",
            return_value={"CustomNoBase": custom_entry},
        )
        mock_engine = mocker.patch("app.type_recorder._engine.SnmpEngine")
        mocker.patch("app.type_recorder._builder.DirMibSource")
        mock_glob = mocker.patch.object(Path, "glob")

        mock_mib_builder = mocker.MagicMock()
        mock_mib_builder.mibSymbols = {"TEST-MIB": {"sym": Symbol()}}
        mock_engine.return_value.get_mib_builder.return_value = mock_mib_builder
        mock_glob.return_value = []

        recorder.build()

        entry = recorder.registry["CustomNoBase"]
        assert entry["constraints_repr"] is not None
        assert entry["constraints"]


class TestRegistry:
    """Test registry property"""

    def test_raises_if_not_built(self) -> None:
        """Should raise if build() not called"""
        recorder = TypeRecorder(Path("/fake"))
        with pytest.raises(RuntimeError, match="build.*must be called"):
            _ = recorder.registry

    def test_returns_registry_after_build(self) -> None:
        """Should return registry after build()"""
        from app.type_recorder import TypeEntry

        recorder = TypeRecorder(Path("/fake"))
        test_entry: TypeEntry = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }
        recorder._registry = {"test": test_entry}
        result = recorder.registry
        assert result == {"test": test_entry}


class TestExportToJson:
    """Test export_to_json method"""

    def test_raises_if_not_built(self) -> None:
        """Should raise if build() not called"""
        recorder = TypeRecorder(Path("/fake"))
        with pytest.raises(RuntimeError, match="build.*must be called"):
            recorder.export_to_json("out.json")

    def test_exports_registry(self, mocker: Any) -> None:
        """Should export registry to JSON file"""
        from app.type_recorder import TypeEntry

        recorder = TypeRecorder(Path("/fake"))
        int32_entry: TypeEntry = {
            "base_type": None,
            "display_hint": None,
            "size": None,
            "constraints": [],
            "constraints_repr": None,
            "enums": None,
            "defined_in": None,
            "abstract": False,
            "used_by": [],
        }
        recorder._registry = {"Integer32": int32_entry}

        m = mocker.mock_open()
        mocker.patch("builtins.open", m)
        recorder.export_to_json("types.json")

        m.assert_called_once_with("types.json", "w", encoding="utf-8")
        # Verify json.dump was called
        handle = m()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        assert "Integer32" in written_data


class TestMain:
    """Test main function"""

    def test_main_function(self, mocker: Any) -> None:
        """Should parse args and run recorder"""
        from app.type_recorder import main

        mocker.patch(
            "sys.argv", ["type_recorder.py", "compiled-mibs", "-o", "out.json"]
        )
        mocker.patch.object(TypeRecorder, "build")
        mocker.patch.object(TypeRecorder, "export_to_json")
        mocker.patch.object(TypeRecorder, "registry", {"type1": {}})
        mocker.patch("builtins.print")

        main()
