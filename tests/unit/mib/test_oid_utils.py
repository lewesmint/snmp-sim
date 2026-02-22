"""Tests for test oid utils."""

from typing import Any

import pytest

from app.oid_utils import normalize_oid, oid_str_to_tuple, oid_tuple_to_str


def test_oid_str_to_tuple_formats() -> None:
    """Test case for test_oid_str_to_tuple_formats."""
    assert oid_str_to_tuple("1.3.6.1.2.1.1.1.0") == (1, 3, 6, 1, 2, 1, 1, 1, 0)
    assert oid_str_to_tuple(".1.3.6.1.2.1.1.1.0") == (1, 3, 6, 1, 2, 1, 1, 1, 0)
    assert oid_str_to_tuple("  .1.3.6.1  ") == (1, 3, 6, 1)
    assert oid_str_to_tuple("") == ()


def test_oid_str_to_tuple_invalid_component() -> None:
    """Test case for test_oid_str_to_tuple_invalid_component."""
    with pytest.raises(ValueError):
        oid_str_to_tuple("1.3.bad.6")


def test_oid_tuple_to_str() -> None:
    """Test case for test_oid_tuple_to_str."""
    assert oid_tuple_to_str((1, 3, 6, 1)) == "1.3.6.1"
    assert oid_tuple_to_str(()) == ""


def test_normalize_oid_supported_types() -> None:
    """Test case for test_normalize_oid_supported_types."""
    assert normalize_oid("1.3.6.1") == (1, 3, 6, 1)
    assert normalize_oid([1, 3, 6, 1]) == (1, 3, 6, 1)
    assert normalize_oid((1, 3, 6, 1)) == (1, 3, 6, 1)


def test_normalize_oid_invalid_type() -> None:
    """Test case for test_normalize_oid_invalid_type."""
    with pytest.raises(TypeError):
        normalize_oid(cast_any(12345))


def cast_any(value: Any) -> Any:
    """Test case for cast_any."""
    return value
