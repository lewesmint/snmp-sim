"""MibTable: Represents a MIB table (collection of rows/columns)."""

from .mib_object import MibObject


class MibTable:
    """Represents a MIB table (collection of rows/columns)."""

    def __init__(self, oid: str, columns: list[MibObject]) -> None:
        """Initialize a MIB table with OID and columns."""
        self.oid = oid
        self.columns = columns
        self.rows: list[list[object]] = []

    def add_row(self, row: list[object]) -> None:
        """Add a row to the table."""
        self.rows.append(row)

    def get_rows(self) -> list[list[object]]:
        """Get all rows in the table."""
        return self.rows
