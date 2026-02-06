import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from typing import Generator, Any, Dict

import pytest
from app.types import TypeRegistry, JsonDict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def mock_logger() -> MagicMock:
    """Provide a mock logger fixture."""
    return MagicMock()


@pytest.fixture
def type_registry_file(sample_type_registry: TypeRegistry) -> Generator[str, None, None]:
    """Create a temporary type registry file using the canonical sample registry."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_type_registry, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def sample_type_registry() -> TypeRegistry:
    """Provide sample type registry data (normalized to ASN.1 base types)."""
    return {
        "TimeTicks": {"base_type": "TimeTicks"},
        "OctetString": {"base_type": "OCTET STRING"},
        "Integer32": {"base_type": "INTEGER", "constraints": [{"type": "ValueRangeConstraint", "min": 0, "max": 100}]},
        "Counter32": {"base_type": "INTEGER"},
        "DisplayString": {"base_type": "OCTET STRING"},
        "IPAddress": {"base_type": "OCTET STRING"},
    }


@pytest.fixture
def mib_json_fixture() -> JsonDict:
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
def sample_mib_schema() -> JsonDict:
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
def mib_schema_dir(tmp_path: Path, sample_mib_schema: JsonDict) -> Path:
    """Create a temporary MIB schema directory."""
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    
    # Preserve older style TEST-MIB.json for compatibility
    mib_schema = {
        "TEST-MIB": {
            "sysDescr": {"oid": [1, 3, 6, 1], "type": "OctetString"}
        }
    }
    schema_file = schema_dir / "TEST-MIB.json"
    schema_file.write_text(json.dumps(mib_schema))

    # Also create a proper MIB folder structure with schema.json for SNMPv2-MIB
    snmpv2_dir = schema_dir / "SNMPv2-MIB"
    snmpv2_dir.mkdir()
    schema_json_path = snmpv2_dir / "schema.json"
    schema_json_path.write_text(json.dumps(sample_mib_schema))

    return schema_dir


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Alias for tmp_path for backward compatibility."""
    return tmp_path


@pytest.fixture
def mib_class_mocks(agent: Any, mocker: Any) -> Dict[str, Any]:
    """Ensure MIB class mocks are present on the agent.

    Tests that exercise MIB registration can include this fixture to get
    `MibScalarInstance`, `MibTable`, `MibTableRow`, `MibTableColumn`, and
    `MibScalar` set as MagicMocks on the provided `agent` object using
    `setattr(...)` which avoids mypy `attr-defined` errors in tests.
    """
    mocks: Dict[str, Any] = {
        "MibScalarInstance": mocker.MagicMock(),
        "MibTable": mocker.MagicMock(),
        "MibTableRow": mocker.MagicMock(),
        "MibTableColumn": mocker.MagicMock(),
        "MibScalar": mocker.MagicMock(),
    }
    for name, value in mocks.items():
        setattr(agent, name, value)

    return mocks

