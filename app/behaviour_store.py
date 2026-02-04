"""
BehaviourStore: Manages persistent/mock data for MIB objects.
"""
from typing import Dict, Any

class BehaviourStore:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}

    def load(self, path: str) -> None:
        # ...load data from file...
        pass

    def save(self, path: str) -> None:
        # ...save data to file...
        pass

    def get(self, oid: str) -> Any:
        return self.data.get(oid)

    def set(self, oid: str, value: Any) -> None:
        self.data[oid] = value
