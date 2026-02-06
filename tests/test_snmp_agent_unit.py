from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from app.snmp_agent import SNMPAgent


class _FakeType:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeMibBuilder:
    def __init__(self) -> None:
        self.exported: list[Any] = []
        self.import_calls: list[tuple[str, str]] = []

    def import_symbols(self, mib_name: str, symbol_name: str) -> list[type[_FakeType]]:
        self.import_calls.append((mib_name, symbol_name))
        if symbol_name == "BadType":
            raise Exception("not found")
        return [_FakeType]

    def export_symbols(self, _mib: str, *symbols: Any) -> None:
        self.exported.extend(symbols)


def _make_agent() -> SNMPAgent:
    agent = SNMPAgent(config_path="agent_config.yaml")
    agent.logger = logging.getLogger("test")
    agent.mib_builder = _FakeMibBuilder()
    agent.MibScalar = lambda oid, value: ("scalar", oid, value)
    agent.MibScalarInstance = lambda oid, _zero, value: ("instance", oid, value)
    return agent


def test_register_scalars_defaults_and_sysuptime() -> None:
    agent = _make_agent()
    agent.start_time = 0.0

    mib_json = {
        "sysUpTime": {
            "oid": [1, 3, 6],
            "type": "TimeTicks",
            "access": "read-only",
            "initial": None,
        },
        "sysDescr": {
            "oid": [1, 3, 6, 1],
            "type": "OctetString",
            "access": "read-only",
            "initial": None,
        },
        "tableEntry": {
            "oid": [1, 3, 6, 2],
            "type": "Integer32",
            "access": "read-only",
        },
    }
    table_related = {"tableEntry"}
    type_registry = {
        "TimeTicks": {"base_type": "TimeTicks"},
        "OctetString": {"base_type": "OctetString"},
    }

    agent._register_scalars("TEST-MIB", mib_json, table_related, type_registry)
    assert len(agent.mib_builder.exported) == 4


def test_register_scalars_invalid_type_skipped(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    mib_json = {
        "badType": {
            "oid": [1, 3, 6, 9],
            "type": None,
            "access": "read-only",
            "initial": 1,
        }
    }
    with caplog.at_level(logging.WARNING):
        agent._register_scalars("TEST-MIB", mib_json, set(), {})
    assert "invalid type" in caplog.text


def test_register_scalars_unresolved_type(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    mib_json = {
        "badType": {
            "oid": [1, 3, 6, 9],
            "type": "BadType",
            "access": "read-only",
            "initial": 1,
        }
    }
    with caplog.at_level(logging.ERROR):
        agent._register_scalars("TEST-MIB", mib_json, set(), {"BadType": {"base_type": "BadType"}})
    assert "Error registering" in caplog.text


def test_register_scalars_skips_access_and_no_defaults(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    mib_json = {
        "notAccessible": {
            "oid": [1, 3, 6, 1],
            "type": "Integer32",
            "access": "not-accessible",
            "initial": 5,
        },
        "notifyOnly": {
            "oid": [1, 3, 6, 2],
            "type": "Integer32",
            "access": "accessible-for-notify",
            "initial": 5,
        },
        "unknownType": {
            "oid": [1, 3, 6, 3],
            "type": "Unknown",
            "access": "read-only",
            "initial": None,
        },
    }
    with caplog.at_level(logging.WARNING):
        agent._register_scalars("TEST-MIB", mib_json, set(), {"Unknown": {"base_type": "Mystery"}})
    assert "no value and no default" in caplog.text


def test_register_scalars_type_registry_missing_warning(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    mib_json = {
        "sysDescr": {
            "oid": [1, 3, 6, 1],
            "type": "OctetString",
            "access": "read-only",
            "initial": "ok",
        }
    }
    with caplog.at_level(logging.WARNING):
        agent._register_scalars("TEST-MIB", mib_json, set(), {})
    assert "not found in type registry" in caplog.text


def test_register_scalars_invalid_base_type(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    mib_json = {
        "badBase": {
            "oid": [1, 3, 6, 9],
            "type": "Weird",
            "access": "read-only",
            "initial": 1,
        }
    }
    with caplog.at_level(logging.WARNING):
        agent._register_scalars("TEST-MIB", mib_json, set(), {"Weird": {"base_type": 123}})
    assert "invalid type" in caplog.text


def test_register_scalars_no_symbols_exported() -> None:
    agent = _make_agent()
    mib_json = {
        "notAccessible": {
            "oid": [1, 3, 6, 1],
            "type": "Integer32",
            "access": "not-accessible",
            "initial": 5,
        }
    }
    agent._register_scalars("TEST-MIB", mib_json, set(), {"Integer32": {"base_type": "Integer32"}})
    assert agent.mib_builder.exported == []


def test_register_scalars_export_error(caplog: pytest.LogCaptureFixture) -> None:
    agent = _make_agent()
    agent.mib_builder.export_symbols = lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("boom"))

    mib_json = {
        "sysDescr": {
            "oid": [1, 3, 6, 1],
            "type": "OctetString",
            "access": "read-only",
            "initial": "ok",
        }
    }
    with caplog.at_level(logging.ERROR):
        agent._register_scalars("TEST-MIB", mib_json, set(), {"OctetString": {"base_type": "OctetString"}})
    assert "Error exporting symbols" in caplog.text


def test_setup_transport_requires_engine() -> None:
    agent = _make_agent()
    agent.snmpEngine = None
    with pytest.raises(RuntimeError):
        agent._setup_transport()


def test_setup_community_requires_engine() -> None:
    agent = _make_agent()
    agent.snmpEngine = None
    with pytest.raises(RuntimeError):
        agent._setup_community()


def test_setup_responders_requires_engine() -> None:
    agent = _make_agent()
    agent.snmpEngine = None
    with pytest.raises(RuntimeError):
        agent._setup_responders()


def test_setup_snmp_engine_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()

    class _FakeEngineMibBuilder:
        def __init__(self) -> None:
            self.sources: list[str] = []

        def add_mib_sources(self, source: str) -> None:
            self.sources.append(source)

        def import_symbols(self, _mib: str, *symbols: str) -> tuple[Any, ...]:
            return tuple(object() for _ in symbols)

    class _FakeEngine:
        def __init__(self) -> None:
            self._builder = _FakeEngineMibBuilder()

        def get_mib_builder(self) -> _FakeEngineMibBuilder:
            return self._builder

    monkeypatch.setattr("pysnmp.entity.engine.SnmpEngine", _FakeEngine)
    monkeypatch.setattr("pysnmp.smi.builder.DirMibSource", lambda path: path)

    agent._setup_snmpEngine("/tmp/compiled")
    assert agent.snmpEngine is not None
    assert agent.mib_builder is not None


def test_setup_transport_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()

    class _FakeTransport:
        def open_server_mode(self, _addr: Any) -> "_FakeTransport":
            return self

    class _FakeUdp:
        DOMAIN_NAME = "udp"
        UdpTransport = _FakeTransport

    calls: list[tuple[Any, Any, Any]] = []

    def fake_add_transport(engine: Any, domain: Any, transport: Any) -> None:
        calls.append((engine, domain, transport))

    agent.snmpEngine = object()
    monkeypatch.setattr("pysnmp.carrier.asyncio.dgram.udp.DOMAIN_NAME", _FakeUdp.DOMAIN_NAME)
    monkeypatch.setattr("pysnmp.carrier.asyncio.dgram.udp.UdpTransport", _FakeTransport)
    monkeypatch.setattr("pysnmp.entity.config.add_transport", fake_add_transport)

    agent._setup_transport()
    assert calls


def test_setup_community_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    agent.snmpEngine = object()

    calls: list[str] = []

    monkeypatch.setattr("pysnmp.entity.config.add_v1_system", lambda *_args, **_kwargs: calls.append("v1"))
    monkeypatch.setattr("pysnmp.entity.config.add_context", lambda *_args, **_kwargs: calls.append("ctx"))
    monkeypatch.setattr("pysnmp.entity.config.add_vacm_group", lambda *_args, **_kwargs: calls.append("group"))
    monkeypatch.setattr("pysnmp.entity.config.add_vacm_view", lambda *_args, **_kwargs: calls.append("view"))
    monkeypatch.setattr("pysnmp.entity.config.add_vacm_access", lambda *_args, **_kwargs: calls.append("access"))

    agent._setup_community()
    assert "v1" in calls and "access" in calls


def test_setup_responders_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    agent.snmpEngine = object()

    calls: list[str] = []

    class _FakeContext:
        def __init__(self, _engine: Any) -> None:
            calls.append("context")

    class _Responder:
        def __init__(self, _engine: Any, _context: Any) -> None:
            calls.append(self.__class__.__name__)

    monkeypatch.setattr("pysnmp.entity.rfc3413.context.SnmpContext", _FakeContext)
    monkeypatch.setattr("pysnmp.entity.rfc3413.cmdrsp.GetCommandResponder", _Responder)
    monkeypatch.setattr("pysnmp.entity.rfc3413.cmdrsp.NextCommandResponder", _Responder)
    monkeypatch.setattr("pysnmp.entity.rfc3413.cmdrsp.BulkCommandResponder", _Responder)
    monkeypatch.setattr("pysnmp.entity.rfc3413.cmdrsp.SetCommandResponder", _Responder)

    agent._setup_responders()
    assert "context" in calls


def test_run_happy_path_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    agent = _make_agent()
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: ["TEST-MIB"] if key == "mibs" else default)

    compiled_dir = tmp_path / "compiled"
    json_dir = tmp_path / "mock-behaviour"
    compiled_dir.mkdir()
    json_dir.mkdir()

    def fake_abspath(path: str) -> str:
        if "compiled-mibs" in path:
            return str(compiled_dir)
        if "mock-behaviour" in path:
            return str(json_dir)
        return path

    monkeypatch.setattr("app.snmp_agent.os.path.abspath", fake_abspath)

    monkeypatch.setattr("app.snmp_agent.MibCompiler.compile", lambda _self, _p: str(compiled_dir / "TEST-MIB.py"))

    class _FakeTypeRegistry:
        def __init__(self, _path: Any) -> None:
            self._registry = {"x": 1}

        def build(self) -> None:
            return None

        def export_to_json(self, _path: str) -> None:
            return None

        @property
        def registry(self) -> dict[str, Any]:
            return self._registry

    monkeypatch.setattr("app.type_registry.TypeRegistry", _FakeTypeRegistry)
    monkeypatch.setattr("app.snmp_agent.subprocess.run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.generator.BehaviourGenerator.generate", lambda _self, _p: None)

    (json_dir / "TEST-MIB_behaviour.json").write_text("{}")

    class _Dispatcher:
        def __init__(self) -> None:
            self.started = False
            self.closed = False

        def job_started(self, _n: int) -> None:
            self.started = True

    class _FakeEngine:
        def __init__(self) -> None:
            self.transport_dispatcher = _Dispatcher()
            self.closed = False

        def open_dispatcher(self) -> None:
            raise KeyboardInterrupt()

        def close_dispatcher(self) -> None:
            self.closed = True

    def fake_setup_engine(_compiled_dir: str) -> None:
        agent.snmpEngine = _FakeEngine()

    monkeypatch.setattr(agent, "_setup_snmpEngine", fake_setup_engine)
    monkeypatch.setattr(agent, "_setup_transport", lambda: None)
    monkeypatch.setattr(agent, "_setup_community", lambda: None)
    monkeypatch.setattr(agent, "_setup_responders", lambda: None)
    monkeypatch.setattr(agent, "_register_mib_objects", lambda: None)

    agent.run()
    assert agent.snmpEngine is not None
    assert agent.snmpEngine.transport_dispatcher.started is True
    assert agent.snmpEngine.closed is True


def test_init_with_pre_configured_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SNMPAgent.__init__ when AppLogger is already configured"""
    # Set AppLogger as already configured
    from app.app_logger import AppLogger
    original_configured = AppLogger._configured
    AppLogger._configured = True
    
    try:
        agent = SNMPAgent(config_path="agent_config.yaml")
        # Should not raise an error, should create AppConfig anyway
        assert agent.app_config is not None
    finally:
        AppLogger._configured = original_configured


def test_run_compile_mib_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test run() when MIB compilation fails"""
    agent = _make_agent()
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: ["BAD-MIB"] if key == "mibs" else default)

    compiled_dir = tmp_path / "compiled"
    json_dir = tmp_path / "mock-behaviour"
    compiled_dir.mkdir()
    json_dir.mkdir()

    def fake_abspath(path: str) -> str:
        if "compiled-mibs" in path:
            return str(compiled_dir)
        if "mock-behaviour" in path:
            return str(json_dir)
        return path

    monkeypatch.setattr("app.snmp_agent.os.path.abspath", fake_abspath)
    
    def compile_fail(_self: Any, _p: str) -> str:
        raise Exception("compilation failed")
    
    monkeypatch.setattr("app.snmp_agent.MibCompiler.compile", compile_fail)

    class _FakeTypeRegistry:
        def __init__(self, _path: Any) -> None:
            self._registry = {"x": 1}

        def build(self) -> None:
            return None

        def export_to_json(self, _path: str) -> None:
            return None

        @property
        def registry(self) -> dict[str, Any]:
            return self._registry

    monkeypatch.setattr("app.type_registry.TypeRegistry", _FakeTypeRegistry)
    
    # Stop early before trying to setup SNMP engine
    def fake_setup_engine(_compiled_dir: str) -> None:
        return None
    
    monkeypatch.setattr(agent, "_setup_snmpEngine", fake_setup_engine)
    
    with caplog.at_level(logging.ERROR):
        agent.run()
    
    assert "Failed to compile BAD-MIB" in caplog.text


def test_run_validation_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test run() when type registry validation fails"""
    agent = _make_agent()
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: ["TEST-MIB"] if key == "mibs" else default)

    compiled_dir = tmp_path / "compiled"
    json_dir = tmp_path / "mock-behaviour"
    compiled_dir.mkdir()
    json_dir.mkdir()

    def fake_abspath(path: str) -> str:
        if "compiled-mibs" in path:
            return str(compiled_dir)
        if "mock-behaviour" in path:
            return str(json_dir)
        return path

    monkeypatch.setattr("app.snmp_agent.os.path.abspath", fake_abspath)
    monkeypatch.setattr("app.snmp_agent.MibCompiler.compile", lambda _self, _p: str(compiled_dir / "TEST-MIB.py"))

    class _FakeTypeRegistry:
        def __init__(self, _path: Any) -> None:
            self._registry = {"x": 1}

        def build(self) -> None:
            return None

        def export_to_json(self, _path: str) -> None:
            return None

        @property
        def registry(self) -> dict[str, Any]:
            return self._registry

    monkeypatch.setattr("app.type_registry.TypeRegistry", _FakeTypeRegistry)
    
    # Make validation fail
    import subprocess
    monkeypatch.setattr("app.snmp_agent.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "cmd")))

    with caplog.at_level(logging.ERROR):
        agent.run()
    
    assert "Type registry validation failed" in caplog.text


def test_run_generate_json_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test run() when JSON generation fails"""
    agent = _make_agent()
    monkeypatch.setattr(agent.app_config, "get", lambda key, default=None: ["TEST-MIB"] if key == "mibs" else default)

    compiled_dir = tmp_path / "compiled"
    json_dir = tmp_path / "mock-behaviour"
    compiled_dir.mkdir()
    json_dir.mkdir()

    def fake_abspath(path: str) -> str:
        if "compiled-mibs" in path:
            return str(compiled_dir)
        if "mock-behaviour" in path:
            return str(json_dir)
        return path

    monkeypatch.setattr("app.snmp_agent.os.path.abspath", fake_abspath)
    monkeypatch.setattr("app.snmp_agent.MibCompiler.compile", lambda _self, _p: str(compiled_dir / "TEST-MIB.py"))

    class _FakeTypeRegistry:
        def __init__(self, _path: Any) -> None:
            self._registry = {"x": 1}

        def build(self) -> None:
            return None

        def export_to_json(self, _path: str) -> None:
            return None

        @property
        def registry(self) -> dict[str, Any]:
            return self._registry

    monkeypatch.setattr("app.type_registry.TypeRegistry", _FakeTypeRegistry)
    monkeypatch.setattr("app.snmp_agent.subprocess.run", lambda *_args, **_kwargs: None)
    
    # Make generator.generate fail
    def generate_fail(_self: Any, _p: str) -> None:
        raise Exception("generation failed")
    
    monkeypatch.setattr("app.generator.BehaviourGenerator.generate", generate_fail)
    
    # Stop early before trying to load JSON files
    def fake_setup_engine(_compiled_dir: str) -> None:
        return None
    
    monkeypatch.setattr(agent, "_setup_snmpEngine", fake_setup_engine)

    with caplog.at_level(logging.ERROR):
        agent.run()
    
    assert "Failed to generate behavior JSON" in caplog.text


def test_register_mib_objects_no_json_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _register_mib_objects when no JSON files are loaded"""
    agent = _make_agent()
    agent.mib_jsons = {}  # Empty mib_jsons
    agent.snmpEngine = {"mib_builder": None}
    agent.MibTable = lambda *args: None
    agent.MibTableRow = lambda *args: None
    agent.MibTableColumn = lambda *args: None
    
    # Should complete without error even with no JSON files
    agent._register_mib_objects()
    # Just verify it doesn't crash
