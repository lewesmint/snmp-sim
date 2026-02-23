"""MibObject: Represents a single MIB object (scalar or table column)."""

class MibObject:
    """Represents a single MIB object (scalar or table column)."""

    def __init__(self, oid: str, type_info: dict[str, object], value: object = None) -> None:
        """Initialize a MIB object with OID, type info, and optional value."""
        self.oid = oid
        self.type_info = type_info
        self.value = value

    def get_value(self) -> object:
        """Get the current value of this MIB object."""
        return self.value

    def set_value(self, value: object) -> None:
        """Set the value of this MIB object."""
        self.value = value
