"""Integration test for RowStatus createAndGo lifecycle on TEST-ENUM-MIB."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    set_cmd,
)
from pysnmp.proto.rfc1902 import Integer

from app.generator import BehaviourGenerator
from app.snmp_agent import SNMPAgent

TEST_ROW_COLOUR_OID = "1.3.6.1.4.1.99998.1.2.1.2"
TEST_ROW_PRIORITY_OID = "1.3.6.1.4.1.99998.1.2.1.3"
TEST_ROW_STATUS_OID = "1.3.6.1.4.1.99998.1.2.1.4"

CREATE_AND_GO = 4
ACTIVE = 1
DESTROY = 6
MIB_STATE_PATH = Path("agent-model") / "mib_state.json"


def _snapshot_and_clear_mib_state() -> bytes | None:
    """Return previous mib_state bytes and remove the file for test isolation."""
    if not MIB_STATE_PATH.exists():
        return None
    try:
        snapshot = MIB_STATE_PATH.read_bytes()
    except OSError:
        return None
    try:
        MIB_STATE_PATH.unlink()
    except OSError:
        pass
    return snapshot


def _restore_mib_state(snapshot: bytes | None) -> None:
    """Restore mib_state to pre-test content or remove it if none existed."""
    try:
        if snapshot is None:
            if MIB_STATE_PATH.exists():
                MIB_STATE_PATH.unlink()
            return

        MIB_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MIB_STATE_PATH.write_bytes(snapshot)
    except OSError:
        pass


def _ensure_test_enum_schema_ready() -> None:
    schema_path = Path("agent-model") / "TEST-ENUM-MIB" / "schema.json"
    compiled_path = Path("compiled-mibs") / "TEST-ENUM-MIB.py"

    if not compiled_path.exists():
        raise AssertionError(f"Missing compiled TEST-ENUM MIB: {compiled_path}")

    needs_regen = True
    if schema_path.exists():
        try:
            schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
            objects = schema_data.get("objects") if isinstance(schema_data, dict) else None
            needs_regen = not (isinstance(objects, dict) and objects)
        except (OSError, TypeError, ValueError):
            needs_regen = True

    if needs_regen:
        generator = BehaviourGenerator("agent-model")
        generator.generate(
            str(compiled_path),
            mib_name="TEST-ENUM-MIB",
            force_regenerate=True,
        )


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_minimal_mibs(agent: SNMPAgent) -> None:
    original_get: Callable[[str, object], object] = agent.app_config.get

    def patched_get(key: str, default: object = None) -> object:
        if key == "mibs":
            return ["SNMPv2-MIB", "TEST-ENUM-MIB"]
        return original_get(key, default)

    agent.app_config.get = patched_get  # type: ignore[method-assign]


def _row_oid(base: str, index: int) -> str:
    return f"{base}.{index}"


def _run_agent_with_event_loop(agent: SNMPAgent) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        agent.run()
    finally:
        try:
            loop.close()
        except (OSError, RuntimeError, TypeError, ValueError):
            pass


async def _snmp_set(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
) -> tuple[Any, Any, Any, tuple[ObjectType, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[ObjectType, ...]]",
        await set_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *var_binds,
        ),
    )


async def _snmp_get(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
) -> tuple[Any, Any, Any, tuple[ObjectType, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[ObjectType, ...]]",
        await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *var_binds,
        ),
    )


def _wait_for_row_get(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
    timeout_seconds: float = 12.0,
) -> tuple[Any, Any, Any, tuple[ObjectType, ...]]:
    deadline = time.time() + timeout_seconds
    last_result: tuple[Any, Any, Any, tuple[ObjectType, ...]] | None = None

    while time.time() < deadline:
        result = asyncio.run(_snmp_get(host, port, community, var_binds))
        last_result = result
        err_ind, err_stat, _err_idx, _vbs = result
        if not err_ind and not err_stat:
            return result
        time.sleep(0.25)

    if last_result is None:
        raise AssertionError("No SNMP GET attempts were performed")
    return last_result


def _wait_for_agent(host: str, port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    probe_oid = "1.3.6.1.2.1.1.1.0"

    while time.time() < deadline:
        try:
            err_ind, err_stat, _err_idx, _vbs = asyncio.run(
                _snmp_get(
                    host,
                    port,
                    "public",
                    [ObjectType(ObjectIdentity(probe_oid))],
                )
            )
            if not err_ind and not err_stat:
                return
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        time.sleep(0.25)

    raise AssertionError(f"SNMP agent did not become ready on {host}:{port}")


def test_create_and_go_row_lifecycle(monkeypatch: Any) -> None:
    """createAndGo should create/activate row and destroy should remove it."""
    monkeypatch.setattr(SNMPAgent, "_setup_signal_handlers", lambda self: None)
    state_snapshot = _snapshot_and_clear_mib_state()
    _ensure_test_enum_schema_ready()

    host = "127.0.0.1"
    port = _free_udp_port()
    row_index = 6421

    agent = SNMPAgent(host=host, port=port, config_path="agent_config.yaml")
    _configure_minimal_mibs(agent)

    agent_thread = threading.Thread(target=_run_agent_with_event_loop, args=(agent,), daemon=True)
    agent_thread.start()

    try:
        _wait_for_agent(host, port)

        colour_oid = _row_oid(TEST_ROW_COLOUR_OID, row_index)
        priority_oid = _row_oid(TEST_ROW_PRIORITY_OID, row_index)
        status_oid = _row_oid(TEST_ROW_STATUS_OID, row_index)

        err_ind, err_stat, err_idx, set_vbs = asyncio.run(
            _snmp_set(
                host,
                port,
                "private",
                [
                    ObjectType(ObjectIdentity(colour_oid), Integer(2)),
                    ObjectType(ObjectIdentity(priority_oid), Integer(20)),
                    ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO)),
                ],
            )
        )

        assert not err_ind, f"SET transport/protocol error: {err_ind}"
        assert not err_stat, f"SET SNMP error at {err_idx}: {err_stat.prettyPrint()}"
        assert int(set_vbs[2][1]) == ACTIVE

        err_ind, err_stat, err_idx, get_vbs = asyncio.run(
            _snmp_get(
                host,
                port,
                "public",
                [
                    ObjectType(ObjectIdentity(colour_oid)),
                    ObjectType(ObjectIdentity(priority_oid)),
                    ObjectType(ObjectIdentity(status_oid)),
                ],
            )
        )

        assert not err_ind, f"GET transport/protocol error: {err_ind}"
        assert not err_stat, f"GET SNMP error at {err_idx}: {err_stat.prettyPrint()}"
        assert int(get_vbs[0][1]) == 2
        assert int(get_vbs[1][1]) == 20
        assert int(get_vbs[2][1]) == ACTIVE

        err_ind, err_stat, err_idx, _destroy_vbs = asyncio.run(
            _snmp_set(
                host,
                port,
                "private",
                [ObjectType(ObjectIdentity(status_oid), Integer(DESTROY))],
            )
        )

        assert not err_ind, f"DESTROY transport/protocol error: {err_ind}"
        assert not err_stat, f"DESTROY SNMP error at {err_idx}: {err_stat.prettyPrint()}"

        err_ind, err_stat, _err_idx, get_after_destroy = asyncio.run(
            _snmp_get(
                host,
                port,
                "public",
                [ObjectType(ObjectIdentity(status_oid))],
            )
        )
        assert not err_ind
        assert not err_stat
        assert get_after_destroy, "Expected GET response varbind"
        assert "No Such Instance" in get_after_destroy[0][1].prettyPrint()

        defaults_row_index = row_index + 1
        defaults_colour_oid = _row_oid(TEST_ROW_COLOUR_OID, defaults_row_index)
        defaults_priority_oid = _row_oid(TEST_ROW_PRIORITY_OID, defaults_row_index)
        defaults_status_oid = _row_oid(TEST_ROW_STATUS_OID, defaults_row_index)

        err_ind, err_stat, err_idx, defaults_set_vbs = asyncio.run(
            _snmp_set(
                host,
                port,
                "private",
                [ObjectType(ObjectIdentity(defaults_status_oid), Integer(CREATE_AND_GO))],
            )
        )

        assert not err_ind, f"Default create transport/protocol error: {err_ind}"
        assert not err_stat, f"Default create SNMP error at {err_idx}: {err_stat.prettyPrint()}"
        assert int(defaults_set_vbs[0][1]) in {ACTIVE, CREATE_AND_GO}

        err_ind, err_stat, err_idx, defaults_get_vbs = _wait_for_row_get(
            host,
            port,
            "public",
            [
                ObjectType(ObjectIdentity(defaults_colour_oid)),
                ObjectType(ObjectIdentity(defaults_priority_oid)),
                ObjectType(ObjectIdentity(defaults_status_oid)),
            ],
        )

        assert not err_ind, f"Default GET transport/protocol error: {err_ind}"
        assert not err_stat, f"Default GET SNMP error at {err_idx}: {err_stat.prettyPrint()}"
        assert int(defaults_get_vbs[0][1]) == 1
        assert int(defaults_get_vbs[1][1]) == 10
        assert int(defaults_get_vbs[2][1]) == ACTIVE
    finally:
        if agent.snmp_engine is not None and hasattr(agent.snmp_engine, "transport_dispatcher"):
            try:
                agent.snmp_engine.transport_dispatcher.close_dispatcher()
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                pass
        agent_thread.join(timeout=3.0)
        _restore_mib_state(state_snapshot)
