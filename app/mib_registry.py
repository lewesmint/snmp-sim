"""
MibRegistry: Manages OID-to-type mappings and type lookups.
"""
from typing import Dict, Any

class MibRegistry:
    def __init__(self) -> None:
        self.types: Dict[str, Dict[str, Any]] = {}

    def load_from_json(self, path: str) -> None:
        # ...load types from JSON...
        pass

    def get_type(self, oid: str) -> Dict[str, Any]:
        # ...lookup type info...
        return self.types.get(oid, {})
