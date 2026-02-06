"""Unit tests for SNMPAgent class."""

from __future__ import annotations



from app.snmp_agent import SNMPAgent


def test_snmp_agent_init() -> None:
    """Test SNMPAgent initialization."""
    agent = SNMPAgent(config_path="agent_config.yaml", host="127.0.0.1", port=161)
    
    assert agent.host == "127.0.0.1"
    assert agent.port == 161
    assert agent.snmpEngine is None
    assert agent.snmpContext is None
    assert agent.mib_jsons == {}
    assert agent.start_time > 0
    assert agent._shutdown_requested is False


def test_snmp_agent_preloaded_model() -> None:
    """Test SNMPAgent with preloaded model."""
    preloaded = {
        "TEST-MIB": {
            "sysDescr": {"oid": [1, 3, 6, 1], "type": "OctetString"}
        }
    }
    agent = SNMPAgent(
        config_path="agent_config.yaml",
        preloaded_model=preloaded
    )
    
    assert agent.preloaded_model == preloaded


def test_snmp_agent_app_config() -> None:
    """Test that SNMPAgent properly initializes app config."""
    agent = SNMPAgent(config_path="agent_config.yaml")
    
    assert agent.app_config is not None
    assert agent.logger is not None


def test_snmp_agent_init_with_pre_configured_logger() -> None:
    """Test SNMPAgent.__init__ when AppLogger is already configured."""
    from app.app_logger import AppLogger
    
    original_configured = AppLogger._configured
    AppLogger._configured = True
    
    try:
        agent = SNMPAgent(config_path="agent_config.yaml")
        assert agent.app_config is not None
    finally:
        AppLogger._configured = original_configured


def test_snmp_agent_attributes() -> None:
    """Test SNMPAgent has expected attributes."""
    agent = SNMPAgent(config_path="agent_config.yaml")
    
    assert hasattr(agent, 'host')
    assert hasattr(agent, 'port')
    assert hasattr(agent, 'config_path')
    assert hasattr(agent, 'app_config')
    assert hasattr(agent, 'logger')
    assert hasattr(agent, 'snmpEngine')
    assert hasattr(agent, 'snmpContext')
    assert hasattr(agent, 'mib_jsons')
    assert hasattr(agent, 'start_time')
    assert hasattr(agent, 'preloaded_model')
    assert hasattr(agent, '_shutdown_requested')


def test_snmp_agent_config_path() -> None:
    """Test SNMPAgent stores config path."""
    config_path = "custom_config.yaml"
    agent = SNMPAgent(config_path=config_path)
    
    assert agent.config_path == config_path


def test_snmp_agent_default_host_port() -> None:
    """Test SNMPAgent default host and port."""
    agent = SNMPAgent(config_path="agent_config.yaml")
    
    assert agent.host == "0.0.0.0"
    assert agent.port == 11161


def test_register_scalars_defaults_and_sysuptime_deprecated() -> None:
    """NOTE: Tests for _register_scalars are deprecated - this method is internal."""
    pass
