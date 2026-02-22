"""Canonical type registry for the SNMP agent, matching the output of tools/record_types.py.
Manages build, export, and access to the registry after MIB compilation.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path

# Import the TypeRecorder from app.type_recorder
from app.type_recorder import TypeEntry, TypeRecorder


class TypeRegistry:
    """Facade for building, accessing, and exporting the canonical type registry."""

    def __init__(self, compiled_mibs_dir: Path | None = None):
        """Initialize registry state and compiled-MIB source directory."""
        self.compiled_mibs_dir = compiled_mibs_dir or (
            Path(__file__).parent.parent / "compiled-mibs"
        )
        self._registry: dict[str, TypeEntry] | None = None

    def build(self, progress_callback: Callable[[str], None] | None = None) -> None:
        """Build the canonical type registry from compiled-mibs using TypeRecorder."""
        recorder = TypeRecorder(self.compiled_mibs_dir, progress_callback=progress_callback)
        recorder.build()
        self._registry = recorder.registry

    @property
    def registry(self) -> dict[str, TypeEntry]:
        """Return the built registry data."""
        if self._registry is None:
            raise RuntimeError(
                "Type registry has not been built yet. Call build() after compiling MIBs."
            )
        return self._registry

    def export_to_json(self, path: str = "data/types.json") -> None:
        """Export the type registry to a JSON file in the data folder by default."""
        if self._registry is None:
            raise RuntimeError("Type registry has not been built yet. Call build() first.")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2)
