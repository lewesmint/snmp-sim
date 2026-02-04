"""
MibTable: Represents a MIB table (collection of rows/columns).
"""
from typing import Any, List
from .mib_object import MibObject

class MibTable:
    def __init__(self, oid: str, columns: List[MibObject]) -> None:
        self.oid = oid
        self.columns = columns
        self.rows: List[List[Any]] = []

    def add_row(self, row: List[Any]) -> None:
        self.rows.append(row)

    def get_rows(self) -> List[List[Any]]:
        return self.rows
