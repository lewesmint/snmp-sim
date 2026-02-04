
"""
Canonical type registry for the SNMP agent, matching the output of tools/record_types.py.
Manages build, export, and access to the registry after MIB compilation.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Import the TypeRecorder from app.type_recorder
from app.type_recorder import TypeRecorder

class TypeRegistry:
    def __init__(self, compiled_mibs_dir: Optional[Path] = None):
        self.compiled_mibs_dir = compiled_mibs_dir or (Path(__file__).parent.parent / "compiled-mibs")
        self._registry: Optional[Dict[str, Any]] = None

    def build(self) -> None:
        """Build the canonical type registry from compiled-mibs using TypeRecorder."""
        recorder = TypeRecorder(self.compiled_mibs_dir)
        recorder.build()
        self._registry = recorder.registry

    @property
    def registry(self) -> Dict[str, Any]:
        if self._registry is None:
            raise RuntimeError("Type registry has not been built yet. Call build() after compiling MIBs.")
        return self._registry

    def export_to_json(self, path: str = "data/types.json") -> None:
        """Export the type registry to a JSON file in the data folder by default."""
        if self._registry is None:
            raise RuntimeError("Type registry has not been built yet. Call build() first.")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._registry, f, indent=2)