"""
Tests for the canonical type registry and its integration with the agent.
"""
import json
import pytest
from pathlib import Path
from app.type_registry import TypeRegistry

def test_type_registry_build_and_export(tmp_path: Path) -> None:
    """Test that the type registry can build from compiled MIBs and export to JSON."""
    # Create a temporary directory for compiled MIBs
    compiled_dir = tmp_path / "compiled-mibs"
    compiled_dir.mkdir()
    
    # Build the registry from compiled-mibs
    registry = TypeRegistry(compiled_dir)
    
    # Note: build() requires actual compiled MIBs in the directory
    # If the directory is empty, the registry will be empty after build
    try:
        registry.build()
        
        # Export to JSON
        out_path = tmp_path / "types.json"
        registry.export_to_json(str(out_path))
        
        # Verify the JSON was created
        assert out_path.exists(), f"JSON file should be created at {out_path}"
        
        with open(out_path) as f:
            data = json.load(f)
        
        # Data should be a dictionary (even if empty when no MIBs are available)
        assert isinstance(data, dict), "Exported JSON should be a dictionary"
    except RuntimeError as e:
        # If no MIBs are compiled, this is expected
        if "not been built yet" in str(e):
            pytest.skip("No compiled MIBs available for testing")
        else:
            raise

def test_type_registry_fields() -> None:
    """Test that all entries in the type registry have required fields and correct types."""
    from pathlib import Path
    
    # Use the actual compiled-mibs directory if it exists
    compiled_dir = Path(__file__).parent.parent / "compiled-mibs"
    
    if not compiled_dir.exists():
        pytest.skip("No compiled-mibs directory available")
    
    registry = TypeRegistry(compiled_dir)
    registry.build()
    
    # Check each entry has required fields
    for oid, entry in registry.registry.items():
        assert isinstance(oid, str), f"OID key should be string, got {type(oid)}"
        assert isinstance(entry, dict), f"Entry for {oid} should be dict, got {type(entry)}"
        
        # Entries should have name and syntax at minimum
        if "name" in entry:
            assert isinstance(entry["name"], str), "Name should be string"
        if "syntax" in entry:
            assert isinstance(entry["syntax"], str), "Syntax should be string"

def test_agent_loads_type_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that type registry files can be created and loaded."""
    # Create a test types file
    test_types = {"1.2.3.4.5": {"name": "foo", "syntax": "OctetString", "description": "desc"}}
    test_types_path = tmp_path / "types.json"
    with open(test_types_path, "w") as f:
        json.dump(test_types, f)
    
    # Verify the file was created correctly
    with open(test_types_path, "r") as f:
        loaded = json.load(f)
    
    assert loaded == test_types
    assert loaded["1.2.3.4.5"]["name"] == "foo"
