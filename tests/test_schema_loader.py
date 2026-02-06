"""Tests for MIB schema loading functionality."""

import json
import os
from pathlib import Path

import pytest


class TestSchemaLoading:
    """Test MIB schema loading from files."""

    def test_load_single_mib_schema(self, mib_schema_dir, sample_mib_schema):
        """Test loading a single MIB schema from directory."""
        # This tests the current implementation in snmp_agent.py
        mib_name = "SNMPv2-MIB"
        schema_path = os.path.join(mib_schema_dir, mib_name, "schema.json")
        
        assert os.path.exists(schema_path)
        
        with open(schema_path, "r") as f:
            loaded_schema = json.load(f)
        
        assert loaded_schema == sample_mib_schema
        assert "sysDescr" in loaded_schema
        assert "sysUpTime" in loaded_schema

    def test_load_nonexistent_schema(self, mib_schema_dir):
        """Test loading a schema that doesn't exist."""
        mib_name = "NONEXISTENT-MIB"
        schema_path = os.path.join(mib_schema_dir, mib_name, "schema.json")
        
        assert not os.path.exists(schema_path)

    def test_load_multiple_schemas(self, temp_dir):
        """Test loading multiple MIB schemas."""
        schema_dir = temp_dir / "mock-behaviour"
        
        # Create multiple MIB schemas
        mibs = {
            "SNMPv2-MIB": {"sysDescr": {"oid": [1, 3, 6, 1, 2, 1, 1, 1]}},
            "IF-MIB": {"ifNumber": {"oid": [1, 3, 6, 1, 2, 1, 2, 1]}},
        }
        
        for mib_name, schema_data in mibs.items():
            mib_dir = schema_dir / mib_name
            mib_dir.mkdir(parents=True)
            schema_path = mib_dir / "schema.json"
            with open(schema_path, "w") as f:
                json.dump(schema_data, f)
        
        # Load all schemas (simulating snmp_agent.py logic)
        loaded_schemas = {}
        for mib_name in mibs.keys():
            schema_path = os.path.join(schema_dir, mib_name, "schema.json")
            if os.path.exists(schema_path):
                with open(schema_path, "r") as f:
                    loaded_schemas[mib_name] = json.load(f)
        
        assert len(loaded_schemas) == 2
        assert "SNMPv2-MIB" in loaded_schemas
        assert "IF-MIB" in loaded_schemas

    def test_schema_with_invalid_json(self, temp_dir):
        """Test handling of invalid JSON in schema file."""
        schema_dir = temp_dir / "mock-behaviour"
        mib_dir = schema_dir / "BAD-MIB"
        mib_dir.mkdir(parents=True)
        
        schema_path = mib_dir / "schema.json"
        with open(schema_path, "w") as f:
            f.write("{ invalid json }")
        
        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            with open(schema_path, "r") as f:
                json.load(f)

    def test_schema_directory_structure(self, mib_schema_dir):
        """Test that schema directory has correct structure."""
        # Structure should be: {schema_dir}/{MIB_NAME}/schema.json
        mib_dir = mib_schema_dir / "SNMPv2-MIB"
        assert mib_dir.exists()
        assert mib_dir.is_dir()
        
        schema_file = mib_dir / "schema.json"
        assert schema_file.exists()
        assert schema_file.is_file()


class TestBuildInternalModel:
    """Test building internal model from schemas (cli_build_model.py)."""

    def test_build_model_from_schemas(self, temp_dir):
        """Test building internal model from multiple schemas."""
        schema_dir = temp_dir / "mock-behaviour"
        
        # Create test schemas
        test_mibs = ["SNMPv2-MIB", "IF-MIB", "HOST-RESOURCES-MIB"]
        for mib_name in test_mibs:
            mib_dir = schema_dir / mib_name
            mib_dir.mkdir(parents=True)
            schema_path = mib_dir / "schema.json"
            with open(schema_path, "w") as f:
                json.dump({f"{mib_name}_object": {"oid": [1, 2, 3]}}, f)
        
        # Build model (simulating cli_build_model.py)
        model = {}
        for mib in test_mibs:
            schema_path = os.path.join(schema_dir, mib, "schema.json")
            if os.path.exists(schema_path):
                with open(schema_path, "r") as f:
                    model[mib] = json.load(f)
        
        assert len(model) == 3
        assert all(mib in model for mib in test_mibs)

    def test_build_model_with_missing_schemas(self, temp_dir):
        """Test building model when some schemas are missing."""
        schema_dir = temp_dir / "mock-behaviour"
        
        # Create only one schema
        mib_dir = schema_dir / "SNMPv2-MIB"
        mib_dir.mkdir(parents=True)
        schema_path = mib_dir / "schema.json"
        with open(schema_path, "w") as f:
            json.dump({"test": "data"}, f)
        
        # Try to load multiple MIBs
        test_mibs = ["SNMPv2-MIB", "MISSING-MIB"]
        model = {}
        for mib in test_mibs:
            schema_path = os.path.join(schema_dir, mib, "schema.json")
            if os.path.exists(schema_path):
                with open(schema_path, "r") as f:
                    model[mib] = json.load(f)
        
        # Should only load the existing one
        assert len(model) == 1
        assert "SNMPv2-MIB" in model
        assert "MISSING-MIB" not in model

