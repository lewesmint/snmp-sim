"""MibRegistry: Manages OID-to-type mappings and type lookups."""

class MibRegistry:
    """Manages OID-to-type mappings and type lookups."""

    def __init__(self) -> None:
        """Initialize an empty MIB registry."""
        self.types: dict[str, dict[str, object]] = {}

    def load_from_json(self, path: str) -> None:
        """Load types from JSON file."""
        # ...load types from JSON...

    def get_type(self, oid: str) -> dict[str, object]:
        """Get type information for an OID."""
        # ...lookup type info...
        return self.types.get(oid, {})
