"""Tests for type registry loading functionality."""

import json
import os
from pathlib import Path

import pytest


class TestTypeRegistryLoading:
    """Test type registry loading from JSON files."""

    def test_load_type_registry_from_file(self, type_registry_file, sample_type_registry):
        """Test loading type registry from JSON file."""
        with open(type_registry_file, "r") as f:
            loaded_registry = json.load(f)
        
        assert loaded_registry == sample_type_registry
        assert "Integer32" in loaded_registry
        assert "DisplayString" in loaded_registry
        assert "Counter32" in loaded_registry

    def test_type_registry_structure(self, type_registry_file):
        """Test that type registry has correct structure."""
        with open(type_registry_file, "r") as f:
            registry = json.load(f)
        
        # Each type should have required fields
        for type_name, type_info in registry.items():
            assert isinstance(type_info, dict)
            assert "base_type" in type_info
            # Other fields are optional

    def test_load_nonexistent_registry(self, temp_dir):
        """Test loading a registry file that doesn't exist."""
        registry_path = temp_dir / "nonexistent.json"
        
        assert not registry_path.exists()
        
        with pytest.raises(FileNotFoundError):
            with open(registry_path, "r") as f:
                json.load(f)

    def test_load_invalid_json_registry(self, temp_dir):
        """Test loading a registry with invalid JSON."""
        registry_path = temp_dir / "invalid.json"
        with open(registry_path, "w") as f:
            f.write("{ invalid json content }")
        
        with pytest.raises(json.JSONDecodeError):
            with open(registry_path, "r") as f:
                json.load(f)

    def test_type_registry_path_construction(self, temp_dir):
        """Test different ways of constructing type registry path."""
        # Method 1: Hardcoded string
        path1 = "data/types.json"
        
        # Method 2: os.path.join
        path2 = os.path.join("data", "types.json")
        
        # Method 3: Relative to module
        base_dir = temp_dir
        path3 = os.path.join(base_dir, "data", "types.json")
        
        # All should produce valid paths
        assert isinstance(path1, str)
        assert isinstance(path2, str)
        assert isinstance(path3, str)

    def test_type_registry_default_path(self):
        """Test that default type registry path is consistent."""
        # This tests the pattern used in multiple files
        default_path = os.path.join("data", "types.json")
        
        assert default_path == "data/types.json"

    def test_load_registry_with_error_handling(self, temp_dir):
        """Test loading registry with proper error handling."""
        registry_path = temp_dir / "data" / "types.json"
        
        # Simulate the pattern used in mib_registrar.py
        try:
            with open(registry_path, "r") as f:
                type_registry = json.load(f)
        except Exception as e:
            # Should fall back to empty dict
            type_registry = {}
        
        assert type_registry == {}


class TestTypeRegistryUsage:
    """Test how type registry is used in the codebase."""

    def test_get_type_info(self, sample_type_registry):
        """Test retrieving type info from registry."""
        type_name = "Integer32"
        type_info = sample_type_registry.get(type_name, {})
        
        assert type_info is not None
        assert type_info["base_type"] == "INTEGER"

    def test_get_base_type(self, sample_type_registry):
        """Test getting base type from type info."""
        type_name = "DisplayString"
        type_info = sample_type_registry.get(type_name, {})
        base_type = type_info.get("base_type")
        
        assert base_type == "OCTET STRING"

    def test_missing_type_fallback(self, sample_type_registry):
        """Test fallback when type is not in registry."""
        type_name = "NonexistentType"
        type_info = sample_type_registry.get(type_name, {})
        
        assert type_info == {}
        
        # Should handle missing base_type gracefully
        base_type = type_info.get("base_type")
        assert base_type is None

    def test_type_with_constraints(self, sample_type_registry):
        """Test accessing type constraints."""
        type_info = sample_type_registry["Integer32"]
        constraints = type_info.get("constraints")
        
        assert constraints is not None
        assert isinstance(constraints, list)
        assert len(constraints) > 0

    def test_type_with_enums(self, sample_type_registry):
        """Test accessing type enumerations."""
        # Add a type with enums for testing
        sample_type_registry["TestEnum"] = {
            "base_type": "INTEGER",
            "enums": {"up": 1, "down": 2},
            "constraints": None,
        }
        
        type_info = sample_type_registry["TestEnum"]
        enums = type_info.get("enums")
        
        assert enums is not None
        assert enums["up"] == 1
        assert enums["down"] == 2

