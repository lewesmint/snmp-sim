"""OID utility functions for consistent OID handling across the application.

This module provides centralized OID conversion functions to eliminate duplicate
code and ensure consistent OID representation. OIDs are represented as tuples
of integers throughout the application.
"""



def oid_str_to_tuple(oid_str: str) -> tuple[int, ...]:
    """Convert OID string to tuple of integers.

    Handles various OID string formats:
    - With leading dot: ".1.3.6.1.2.1.1.1.0"
    - Without leading dot: "1.3.6.1.2.1.1.1.0"
    - Empty strings return empty tuple

    Args:
        oid_str: OID string with dot-separated integers

    Returns:
        Tuple of integers representing the OID

    Examples:
        >>> oid_str_to_tuple("1.3.6.1.2.1.1.1.0")
        (1, 3, 6, 1, 2, 1, 1, 1, 0)
        >>> oid_str_to_tuple(".1.3.6.1.2.1.1.1.0")
        (1, 3, 6, 1, 2, 1, 1, 1, 0)
        >>> oid_str_to_tuple("")
        ()

    """
    oid_str = oid_str.strip()
    oid_str = oid_str.removeprefix(".")
    if not oid_str:
        return ()
    return tuple(int(x) for x in oid_str.split("."))


def oid_tuple_to_str(oid_tuple: tuple[int, ...]) -> str:
    """Convert OID tuple to dot-separated string.

    Args:
        oid_tuple: Tuple of integers representing the OID

    Returns:
        Dot-separated string representation of the OID

    Examples:
        >>> oid_tuple_to_str((1, 3, 6, 1, 2, 1, 1, 1, 0))
        "1.3.6.1.2.1.1.1.0"
        >>> oid_tuple_to_str(())
        ""

    """
    return ".".join(str(x) for x in oid_tuple)


def normalize_oid(oid: object) -> tuple[int, ...]:
    """Normalize OID to tuple format regardless of input type.

    Accepts OIDs in various formats and returns a consistent tuple representation.

    Args:
        oid: OID in string, tuple, or list format

    Returns:
        Tuple of integers representing the OID

    Examples:
        >>> normalize_oid("1.3.6.1.2.1.1.1.0")
        (1, 3, 6, 1, 2, 1, 1, 1, 0)
        >>> normalize_oid([1, 3, 6, 1, 2, 1, 1, 1, 0])
        (1, 3, 6, 1, 2, 1, 1, 1, 0)
        >>> normalize_oid((1, 3, 6, 1, 2, 1, 1, 1, 0))
        (1, 3, 6, 1, 2, 1, 1, 1, 0)

    """
    if isinstance(oid, str):
        return oid_str_to_tuple(oid)
    if isinstance(oid, list):
        return tuple(oid)
    if isinstance(oid, tuple):
        return oid
    msg = f"OID must be string, tuple, or list, got {type(oid)}"
    raise TypeError(msg)
