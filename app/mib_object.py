"""
MibObject: Represents a single MIB object (scalar or table column).
"""
from typing import Any

class MibObject:
    def __init__(self, oid: str, type_info: dict[str, Any], value: Any = None) -> None:
        self.oid = oid
        self.type_info = type_info
        self.value = value

    def get_value(self) -> Any:
        return self.value

    def set_value(self, value: Any) -> None:
        self.value = value
