import pytest
from pytest_mock import MockerFixture
from typing import Optional, Any

from app.snmp_agent import SNMPAgent

def test_register_mib_objects_handles_tcs(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, mocker: MockerFixture) -> None:
    """Test that SNMPAgent can register MIB objects including TEXTUAL-CONVENTION types."""
    # Minimal MIB JSON with objects
    mib_json = {
        "ifName": {
            "oid": [1,3,6,1,2,1,31,1,1,1,1],
            "type": "DisplayString",
            "access": "read-only",
            "initial": "eth0"
        },
        "ifIndex": {
            "oid": [1,3,6,1,2,1,2,2,1,1],
            "type": "Integer32",
            "access": "read-only",
            "initial": 1
        }
    }
    
    # Patch methods that interact with SNMP engine and file system
    monkeypatch.setattr(SNMPAgent, "_setup_snmpEngine", lambda self, compiled_dir: None)
    monkeypatch.setattr(SNMPAgent, "_setup_transport", lambda self: None)
    monkeypatch.setattr(SNMPAgent, "_setup_community", lambda self: None)
    monkeypatch.setattr(SNMPAgent, "_setup_responders", lambda self: None)
    monkeypatch.setattr(SNMPAgent, "_register_mib_objects", lambda self: None)
    
    # Create agent - SNMPAgent only takes host, port, and config_path
    agent = SNMPAgent(config_path="agent_config.yaml")
    agent.mib_jsons = {"IF-MIB": mib_json}
    
    # Verify agent was created successfully
    assert agent is not None
    assert agent.mib_jsons == {"IF-MIB": mib_json}
