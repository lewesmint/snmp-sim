"""Canonical type registry for the SNMP agent.

Matches the output of tools/record_types.py and manages build, export, and
access to the registry after MIB compilation.
"""

import json
from collections.abc import Callable
from pathlib import Path

# Import the TypeRecorder from app.type_recorder
from app.model_paths import TYPE_REGISTRY_FILE
from app.type_recorder import TypeEntry, TypeRecorder


class TypeRegistry:
    """Facade for building, accessing, and exporting the canonical type registry."""

    def __init__(
        self,
        compiled_mibs_dir: Path | None = None,
        include_modules: set[str] | None = None,
    ) -> None:
        """Initialize registry state and compiled-MIB source directory."""
        self.compiled_mibs_dir = compiled_mibs_dir or (
            Path(__file__).parent.parent / "compiled-mibs"
        )
        self.include_modules = include_modules
        self._registry: dict[str, TypeEntry] | None = None

    def build(self, progress_callback: Callable[[str], None] | None = None) -> None:
        """Build the canonical type registry from compiled-mibs using TypeRecorder."""
        recorder = TypeRecorder(
            self.compiled_mibs_dir,
            progress_callback=progress_callback,
            include_modules=self.include_modules,
        )
        recorder.build()
        self._registry = recorder.registry

    @property
    def registry(self) -> dict[str, TypeEntry]:
        """Return the built registry data."""
        if self._registry is None:
            msg = "Type registry has not been built yet. Call build() after compiling MIBs."
            raise RuntimeError(msg)
        return self._registry

    def export_to_json(self, path: str = str(TYPE_REGISTRY_FILE)) -> None:
        """Export the type registry to a JSON file in the config folder by default."""
        if self._registry is None:
            msg = "Type registry has not been built yet. Call build() first."
            raise RuntimeError(msg)
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2)
