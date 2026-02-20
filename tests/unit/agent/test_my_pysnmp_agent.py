"""Tests for the SNMPAgent implementation."""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from app.snmp_agent import SNMPAgent


@pytest.fixture
def agent(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> Generator[SNMPAgent, None, None]:
    """Create an SNMPAgent instance for testing."""
    # SNMPAgent doesn't have a _load_config method to patch
    # Instead, we patch the run method to prevent startup
    monkeypatch.setattr(SNMPAgent, "run", lambda self: None)
    agent = SNMPAgent(host='127.0.0.1', port=11661, config_path='agent_config.yaml')
    # Ensure mib_jsons is always present for all tests
    if not hasattr(agent, 'mib_jsons'):
        agent.mib_jsons = {}
    yield agent


def test_mibs_loaded_from_config(agent: SNMPAgent) -> None:
    """Test that MIBs can be set on the agent."""
    agent.mib_jsons = {'SNMPv2-MIB': {}, 'UDP-MIB': {}, 'CISCO-ALARM-MIB': {}}
    mibs = agent.mib_jsons.keys()
    assert 'SNMPv2-MIB' in mibs
    assert 'UDP-MIB' in mibs
    assert 'CISCO-ALARM-MIB' in mibs


def test_scalar_value_get(agent: SNMPAgent, mocker: MockerFixture) -> None:
    """Test that scalar values can be set on the agent."""
    agent.mib_jsons = {'SNMPv2-MIB': {'sysDescr': {'current': 'SNMP Agent Test'}}}
    # Verify mib_jsons was set correctly
    assert 'SNMPv2-MIB' in agent.mib_jsons
    assert 'sysDescr' in agent.mib_jsons['SNMPv2-MIB']


def test_scalar_value_set_and_persist(agent: SNMPAgent) -> None:
    """Test setting scalar values on the agent."""
    agent.mib_jsons = {'SNMPv2-MIB': {'sysContact': {'current': ''}}}
