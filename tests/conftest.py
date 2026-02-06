import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def mock_logger():
    """Provide a mock logger fixture."""
    return MagicMock()


@pytest.fixture
def type_registry_file():
    """Create a temporary type registry file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        type_registry = {
            "TimeTicks": {"base_type": "TimeTicks"},
            "OctetString": {"base_type": "OctetString"},
            "Integer32": {"base_type": "Integer32"},
            "Counter32": {"base_type": "Counter32"},
        }
        json.dump(type_registry, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def sample_type_registry():
    """Provide sample type registry data."""
    return {
        "TimeTicks": {"base_type": "TimeTicks"},
        "OctetString": {"base_type": "OctetString"},
        "Integer32": {"base_type": "Integer32"},
        "Counter32": {"base_type": "Counter32"},
        "DisplayString": {"base_type": "OctetString"},
        "IPAddress": {"base_type": "OctetString"},
    }


@pytest.fixture
def mib_json_fixture():
    """Provide sample MIB JSON data."""
    return {
        "sysDescr": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 1],
            "type": "OctetString",
            "access": "read-only",
            "initial": None,
        },
        "sysUpTime": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 3],
            "type": "TimeTicks",
            "access": "read-only",
            "initial": None,
        },
        "sysContact": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 4],
            "type": "OctetString",
            "access": "read-write",
            "initial": "contact@example.com",
        },
    }


@pytest.fixture
def sample_mib_schema():
    """Provide sample MIB schema data."""
    return {
        "TEST-MIB": {
            "sysDescr": {
                "oid": [1, 3, 6, 1, 2, 1, 1, 1],
                "type": "OctetString",
                "access": "read-only",
            },
            "sysUpTime": {
                "oid": [1, 3, 6, 1, 2, 1, 1, 3],
                "type": "TimeTicks",
                "access": "read-only",
            },
        }
    }


@pytest.fixture
def mib_schema_dir(tmp_path: Path):
    """Create a temporary MIB schema directory."""
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    
    # Create a sample schema file
    mib_schema = {
        "TEST-MIB": {
            "sysDescr": {"oid": [1, 3, 6, 1], "type": "OctetString"}
        }
    }
    
    schema_file = schema_dir / "TEST-MIB.json"
    schema_file.write_text(json.dumps(mib_schema))
    
    return schema_dir


@pytest.fixture
def temp_dir(tmp_path: Path):
    """Alias for tmp_path for backward compatibility."""
    return tmp_path

