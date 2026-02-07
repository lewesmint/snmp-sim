"""Pytest configuration and shared fixtures."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_type_registry() -> Dict[str, Any]:
    """Sample type registry for testing."""
    return {
        "Integer32": {
            "base_type": "INTEGER",
            "display_hint": None,
            "constraints": [{"type": "range", "min": -2147483648, "max": 2147483647}],
            "enums": None,
        },
        "DisplayString": {
            "base_type": "OCTET STRING",
            "display_hint": "255a",
            "constraints": [{"type": "size", "min": 0, "max": 255}],
            "enums": None,
        },
        "Counter32": {
            "base_type": "Counter32",
            "display_hint": None,
            "constraints": [{"type": "range", "min": 0, "max": 4294967295}],
            "enums": None,
        },
        "TimeTicks": {
            "base_type": "TimeTicks",
            "display_hint": None,
            "constraints": None,
            "enums": None,
        },
    }


@pytest.fixture
def sample_mib_schema() -> Dict[str, Any]:
    """Sample MIB schema for testing."""
    return {
        "sysDescr": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 1],
            "type": "DisplayString",
            "access": "read-only",
            "initial": "Test SNMP Agent",
        },
        "sysUpTime": {
            "oid": [1, 3, 6, 1, 2, 1, 1, 3],
            "type": "TimeTicks",
            "access": "read-only",
            "initial": 0,
        },
        "ifNumber": {
            "oid": [1, 3, 6, 1, 2, 1, 2, 1],
            "type": "Integer32",
            "access": "read-only",
            "initial": 2,
        },
    }


@pytest.fixture
def type_registry_file(temp_dir: Path, sample_type_registry: Dict[str, Any]) -> Path:
    """Create a temporary type registry JSON file."""
    registry_path = temp_dir / "types.json"
    with open(registry_path, "w") as f:
        json.dump(sample_type_registry, f, indent=2)
    return registry_path


@pytest.fixture
def mib_schema_dir(temp_dir: Path, sample_mib_schema: Dict[str, Any]) -> Path:
    """Create a temporary MIB schema directory structure."""
    schema_dir = temp_dir / "mock-behaviour"
    mib_dir = schema_dir / "SNMPv2-MIB"
    mib_dir.mkdir(parents=True)
    
    schema_path = mib_dir / "schema.json"
    with open(schema_path, "w") as f:
        json.dump(sample_mib_schema, f, indent=2)
    
    return schema_dir


@pytest.fixture
def mock_logger(mocker: Any) -> Any:
    """Create a mock logger for testing."""
    logger = mocker.Mock()
    logger.debug = mocker.Mock()
    logger.info = mocker.Mock()
    logger.warning = mocker.Mock()
    logger.error = mocker.Mock()
    return logger

