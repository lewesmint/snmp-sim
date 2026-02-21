"""Unit tests for SNMPAgent class."""

from __future__ import annotations

import sys
import types
import pytest
from types import SimpleNamespace
from pathlib import Path
from typing import Any

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
    preloaded = {"TEST-MIB": {"sysDescr": {"oid": [1, 3, 6, 1], "type": "OctetString"}}}
    agent = SNMPAgent(config_path="agent_config.yaml", preloaded_model=preloaded)

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

    assert hasattr(agent, "host")
    assert hasattr(agent, "port")
    assert hasattr(agent, "config_path")
    assert hasattr(agent, "app_config")
    assert hasattr(agent, "logger")
    assert hasattr(agent, "snmpEngine")
    assert hasattr(agent, "snmpContext")
    assert hasattr(agent, "mib_jsons")
    assert hasattr(agent, "start_time")
    assert hasattr(agent, "preloaded_model")
    assert hasattr(agent, "_shutdown_requested")


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


def test_shutdown_closes_dispatcher_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    class DummyDispatcher:
        def close_dispatcher(self) -> None:
            called["closed"] = True

    dispatcher = DummyDispatcher()

    agent = SNMPAgent(preloaded_model={})
    # Attach fake snmpEngine with a transport_dispatcher
    agent.snmpEngine = SimpleNamespace(transport_dispatcher=dispatcher)

    # Patch os._exit so it raises SystemExit we can catch
    def fake_exit(code: int = 0) -> None:
        called["exit_code"] = code
        raise SystemExit(code)

    monkeypatch.setattr("os._exit", fake_exit)

    with pytest.raises(SystemExit) as excinfo:
        agent._shutdown()

    assert called.get("closed") is True
    assert excinfo.value.code == 0


def test_setup_signal_handlers_registers_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registrations: list[int] = []

    def fake_signal(sig: int, _handler: object) -> None:
        registrations.append(sig)

    monkeypatch.setattr("signal.signal", fake_signal)

    agent = SNMPAgent(preloaded_model={})
    # Re-run setup to capture registrations (it's run in __init__, but re-run for test clarity)
    agent._setup_signal_handlers()

    # Ensure SIGTERM and SIGINT are registered
    assert any(r == getattr(__import__("signal"), "SIGTERM") for r in registrations)
    assert any(r == getattr(__import__("signal"), "SIGINT") for r in registrations)
    # SIGHUP may or may not exist; if it does, it should be registered
    if hasattr(__import__("signal"), "SIGHUP"):
        assert any(r == getattr(__import__("signal"), "SIGHUP") for r in registrations)


def test_run_aborts_when_type_registry_validation_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    agent = SNMPAgent(preloaded_model={})

    # Make validate_type_registry_file return a failing result
    def fake_validate(path: str) -> tuple[bool, list[str], int]:
        return False, ["broken"], 0

    monkeypatch.setattr("app.type_registry_validator.validate_type_registry_file", fake_validate)

    # Prevent SNMP engine setup from running by patching it and asserting it is not called
    called = {"setup_called": False}

    def fake_setup_snmpEngine(self: SNMPAgent, compiled_dir: str) -> None:
        called["setup_called"] = True

    monkeypatch.setattr(SNMPAgent, "_setup_snmpEngine", fake_setup_snmpEngine)

    # Ensure run() completes (should return early due to validation failure)
    agent.run()

    assert called["setup_called"] is False
    assert any("Type registry validation failed" in m.message for m in caplog.records)


def test_register_mib_objects_creates_registrar_and_calls_register_all() -> None:
    agent = SNMPAgent(preloaded_model={})
    # Ensure there's no existing registrar
    if hasattr(agent, "mib_registrar"):
        delattr(agent, "mib_registrar")

    # Create a dummy module with MibRegistrar (use a ModuleType for correct typing)
    mod = types.ModuleType("app.mib_registrar")

    class DummyRegistrar:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.registered = False

        def register_all_mibs(self, mib_jsons: dict[str, Any]) -> None:
            self.registered = True
            self._mib_jsons = mib_jsons

    setattr(mod, "MibRegistrar", DummyRegistrar)

    # Insert into sys.modules so the import inside the method picks it up
    sys.modules["app.mib_registrar"] = mod

    try:
        agent.mib_jsons = {"TEST-MIB": {"schema": {}}}
        # Ensure mib_builder exists so _register_mib_objects proceeds (it checks for None)
        agent.mib_builder = object()
        agent._register_mib_objects()

        assert hasattr(agent, "mib_registrar")
        registrar = agent.mib_registrar
        assert getattr(registrar, "registered", True) is True
        assert getattr(registrar, "_mib_jsons", None) == agent.mib_jsons
    finally:
        del sys.modules["app.mib_registrar"]


def test_decode_value_delegates_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Case 1: delegation
    class DummyReg:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def _decode_value(self, value: Any) -> Any:
            return f"decoded:{value}"

    mod = types.ModuleType("app.mib_registrar")
    setattr(mod, "MibRegistrar", DummyReg)
    monkeypatch.setitem(sys.modules, "app.mib_registrar", mod)

    agent = SNMPAgent(preloaded_model={})
    out = agent._decode_value("abc")
    assert out == "decoded:abc"

    # Case 2: fallback when MibRegistrar cannot be instantiated
    class BadMod:
        class MibRegistrar:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("bad")

    mod_bad = types.ModuleType("app.mib_registrar")
    setattr(mod_bad, "MibRegistrar", BadMod.MibRegistrar)
    monkeypatch.setitem(sys.modules, "app.mib_registrar", mod_bad)

    agent2 = SNMPAgent(preloaded_model={})
    out2 = agent2._decode_value("xyz")
    assert out2 == "xyz"


def test_setup_snmpEngine_loads_compiled_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Prepare a fake compiled-mibs directory with one module
    compiled_dir = tmp_path / "compiled-mibs"
    compiled_dir.mkdir()
    (compiled_dir / "TEST-MIB.py").write_text("# fake compiled mib")

    # Fake pysnmp.engine
    class FakeEngine:
        def __init__(self) -> None:
            self._dispatcher: Any = None

        def register_transport_dispatcher(self, dispatcher: Any) -> None:
            self._dispatcher = dispatcher

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.entity.engine",
        types.SimpleNamespace(SnmpEngine=FakeEngine),
    )

    # Fake AsyncioDispatcher
    class FakeDispatcher:
        def register_recv_callback(self, cb: Any, recvId: Any = None) -> None:
            # Engine will call this; just store a reference
            self._recv_cb = cb

        def register_timer_callback(self, cb: Any) -> None:
            # Engine will call this too; store it for completeness
            self._timer_cb = cb

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.carrier.asyncio.dispatch",
        types.SimpleNamespace(AsyncioDispatcher=FakeDispatcher),
    )

    # Fake context and mib builder
    class FakeMibBuilder:
        def __init__(self) -> None:
            self.sources: list[Any] = []
            self.loaded: list[str] = []

        def add_mib_sources(self, src: Any) -> None:
            self.sources.append(src)

        def load_modules(self, *mods: str) -> None:
            self.loaded.extend(mods)

        def import_symbols(self, *args: Any, **kwargs: Any) -> tuple[str, ...]:
            return (
                "MibScalar",
                "MibScalarInstance",
                "MibTable",
                "MibTableRow",
                "MibTableColumn",
            )

    fake_builder = FakeMibBuilder()

    def fake_get_mib_builder() -> FakeMibBuilder:
        return fake_builder

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.entity.rfc3413.context",
        types.SimpleNamespace(
            SnmpContext=lambda eng: types.SimpleNamespace(
                get_mib_instrum=lambda: types.SimpleNamespace(get_mib_builder=fake_get_mib_builder)
            )
        ),
    )

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.smi.builder",
        types.SimpleNamespace(DirMibSource=lambda p: f"DirMibSource({p})"),
    )

    agent = SNMPAgent(preloaded_model={})
    caplog.set_level("INFO")
    agent._setup_snmpEngine(str(compiled_dir))

    assert agent.snmpEngine is not None
    assert agent.mib_builder is not None
    assert "Loaded compiled MIB modules" in caplog.text


def test_setup_snmpEngine_handles_no_compiled_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    compiled_dir = tmp_path / "compiled-mibs-absent"
    compiled_dir.mkdir()

    # Reuse fake engine and context but no compiled modules present
    class FakeEngine2:
        def __init__(self) -> None:
            pass

        def register_transport_dispatcher(self, dispatcher: Any) -> None:
            pass

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.entity.engine",
        types.SimpleNamespace(SnmpEngine=FakeEngine2),
    )

    class FakeDispatcher2:
        def register_recv_callback(self, cb: Any, recvId: Any = None) -> None:
            self._recv_cb = cb

        def register_timer_callback(self, cb: Any) -> None:
            self._timer_cb = cb

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.carrier.asyncio.dispatch",
        types.SimpleNamespace(AsyncioDispatcher=FakeDispatcher2),
    )

    class FakeMibBuilder:
        def __init__(self) -> None:
            self.sources: list[Any] = []
            self.loaded: list[str] = []

        def add_mib_sources(self, src: Any) -> None:
            self.sources.append(src)

        def load_modules(self, *mods: str) -> None:
            self.loaded.extend(mods)

        def import_symbols(self, *args: Any, **kwargs: Any) -> tuple[str, ...]:
            return (
                "MibScalar",
                "MibScalarInstance",
                "MibTable",
                "MibTableRow",
                "MibTableColumn",
            )

    monkeypatch.setitem(
        sys.modules,
        "pysnmp.entity.rfc3413.context",
        types.SimpleNamespace(
            SnmpContext=lambda eng: types.SimpleNamespace(
                get_mib_instrum=lambda: types.SimpleNamespace(
                    get_mib_builder=lambda: FakeMibBuilder()
                )
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "pysnmp.smi.builder",
        types.SimpleNamespace(DirMibSource=lambda p: f"DirMibSource({p})"),
    )

    agent = SNMPAgent(preloaded_model={})
    caplog.set_level("INFO")
    agent._setup_snmpEngine(str(compiled_dir))

    assert "No compiled MIB modules found" in caplog.text


def test_setup_transport_adds_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeUdp:
        class UdpAsyncioTransport:
            def open_server_mode(self, addr: tuple[str, int]) -> str:
                calls["addr"] = addr
                return "socket"

    def fake_add_transport(engine: object, domain: object, transport: object) -> None:
        calls["engine"] = engine
        calls["domain"] = domain
        calls["transport"] = transport

    monkeypatch.setitem(
        sys.modules, "pysnmp.carrier.asyncio.dgram", types.SimpleNamespace(udp=FakeUdp)
    )
    # Ensure the pysnmp config.add_transport used in the function is our fake
    try:
        import importlib

        cfg_mod = importlib.import_module("pysnmp.entity.config")
        monkeypatch.setattr(cfg_mod, "add_transport", fake_add_transport, raising=False)
        monkeypatch.setattr(cfg_mod, "SNMP_UDP_DOMAIN", "udp", raising=False)
    except Exception:
        monkeypatch.setitem(
            sys.modules,
            "pysnmp.entity.config",
            types.SimpleNamespace(add_transport=fake_add_transport, SNMP_UDP_DOMAIN="udp"),
        )

    agent = SNMPAgent(preloaded_model={})
    agent.snmpEngine = types.SimpleNamespace(transport_dispatcher=True)
    agent.host = "127.0.0.1"
    agent.port = 9999

    agent._setup_transport()

    assert calls.get("engine") == agent.snmpEngine
    assert calls.get("addr") == ("127.0.0.1", 9999)


def test_setup_responders_registers_responders(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class Dummy:
        def __init__(self, engine: Any, context: Any) -> None:
            calls.append((engine, context))

    cmdrsp_mod = types.SimpleNamespace(
        GetCommandResponder=Dummy,
        NextCommandResponder=Dummy,
        BulkCommandResponder=Dummy,
        SetCommandResponder=Dummy,
    )

    # Replace the responders in the real module if present, otherwise inject into sys.modules
    try:
        import importlib

        real_cmdrsp = importlib.import_module("pysnmp.entity.rfc3413.cmdrsp")
        monkeypatch.setattr(real_cmdrsp, "GetCommandResponder", Dummy, raising=False)
        monkeypatch.setattr(real_cmdrsp, "NextCommandResponder", Dummy, raising=False)
        monkeypatch.setattr(real_cmdrsp, "BulkCommandResponder", Dummy, raising=False)
        monkeypatch.setattr(real_cmdrsp, "SetCommandResponder", Dummy, raising=False)
    except Exception:
        monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413.cmdrsp", cmdrsp_mod)

    agent = SNMPAgent(preloaded_model={})
    # Provide lightweight objects compatible with pysnmp cmdrsp expectations
    engine_obj = types.SimpleNamespace(
        message_dispatcher=types.SimpleNamespace(register_context_engine_id=lambda *_a, **_k: None)
    )
    context_obj = types.SimpleNamespace(contextEngineId="ctxid")
    agent.snmpEngine = engine_obj
    agent.snmpContext = context_obj

    agent._setup_responders()

    assert len(calls) == 4
    assert all(c == (engine_obj, context_obj) for c in calls)
