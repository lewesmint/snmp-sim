"""
MibTable: Represents a MIB table (collection of rows/columns).
"""

from typing import Any, List
from .mib_object import MibObject


class MibTable:
    """Represents a MIB table (collection of rows/columns)."""

    def __init__(self, oid: str, columns: List[MibObject]) -> None:
        """Initialize a MIB table with OID and columns."""
        self.oid = oid
        self.columns = columns
        self.rows: List[List[Any]] = []

    def add_row(self, row: List[Any]) -> None:
        """Add a row to the table."""
        self.rows.append(row)

    def get_rows(self) -> List[List[Any]]:
        """Get all rows in the table."""
        return self.rows
