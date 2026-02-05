"""SNMP Agent Application Package."""

from pathlib import Path
from typing import Dict, Any, Optional, Callable
from app.snmp_agent import SNMPAgent
from app.type_registry import TypeRegistry
from app.compiler import MibCompiler, MibCompilationError
from app.generator import BehaviourGenerator


def build_type_registry(
    compiled_mibs_dir: str | Path = "compiled-mibs",
    output_path: str = "data/types.json",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Build the type registry from compiled MIBs and export to JSON.

    This is a convenience function that handles the complete type registration process:
    1. Discovers SNMP types from compiled MIBs
    2. Builds the type registry
    3. Exports to JSON file
    4. Returns the registry dictionary

    Args:
        compiled_mibs_dir: Directory containing compiled MIB .py files
        output_path: Path where the type registry JSON should be saved
        progress_callback: Optional callback function called with MIB name as it's processed

    Returns:
        Dictionary containing the type registry

    Example:
        >>> from app import build_type_registry
        >>> registry = build_type_registry()
        >>> print(f"Built registry with {len(registry)} types")
    """
    compiled_dir = Path(compiled_mibs_dir)

    # Build the type registry
    type_registry = TypeRegistry(compiled_dir)
    type_registry.build(progress_callback=progress_callback)

    # Export to JSON
    type_registry.export_to_json(output_path)

    # Return the registry dictionary
    return type_registry.registry


__all__ = [
    "SNMPAgent",
    "MibCompiler",
    "MibCompilationError",
    "BehaviourGenerator",
    "TypeRegistry",
    "build_type_registry",
]
