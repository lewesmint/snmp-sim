"""Canonical type registry for the SNMP agent.

Matches the output of tools/record_types.py and manages build, export, and
access to the registry after MIB compilation.
"""

import json
from collections.abc import Callable
from pathlib import Path

# Import the TypeRecorder from app.type_recorder
from app.type_recorder import TypeEntry, TypeRecorder


class TypeRegistry:
    """Facade for building, accessing, and exporting the canonical type registry."""

    def __init__(self, compiled_mibs_dir: Path | None = None) -> None:
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
            msg = "Type registry has not been built yet. Call build() after compiling MIBs."
            raise RuntimeError(msg)
        return self._registry

    def export_to_json(self, path: str = "data/types.json") -> None:
        """Export the type registry to a JSON file in the data folder by default."""
        if self._registry is None:
            msg = "Type registry has not been built yet. Call build() first."
            raise RuntimeError(msg)
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2)
