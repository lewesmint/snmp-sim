"""
Shared type aliases for the SNMP agent application.

This module provides common type aliases used throughout the codebase
to ensure consistency and improve type safety.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Type information dictionary - represents a SINGLE type entry in the registry
# Contains: base_type, display_hint, size, constraints, enums, used_by, defined_in, abstract
TypeInfo = Dict[str, Any]

# Type registry - the FULL registry mapping type names to their TypeInfo entries
# Example: {"Integer32": {...}, "DisplayString": {...}, ...}
TypeRegistry = Dict[str, TypeInfo]

# JSON-compatible dictionary type
JsonDict = Dict[str, Any]

# OID type - can be tuple or list of integers
OidType = Union[Tuple[int, ...], List[int]]

# Type encoder function signature
TypeEncoder = Callable[[Any], Any]

# Default value plugin function signature
DefaultValuePlugin = Callable[[TypeInfo, str], Optional[Any]]
