#!/usr/bin/env python3
# ruff: noqa: T201,D103,TRY003,TRY301,EM101,EM102,TRY300,SLF001,PLR2004,S310,RET504,E501
"""E2E test for FOOBAR managerRegistration row persistence across agent restart.

Flow:
1) Purge FOOBAR artifacts (compiled MIB, schema, state)
2) Start agent and wait for readiness
3) createAndGo a row indexed by managerIpAddress + managerSendPort
4) Update managerTrapPort for that row
5) Assert row exists in persisted agent model state (mib_state.json)
6) Restart agent
7) Verify row and trap port still readable over SNMP
8) Verify row values are browsable over REST /value endpoint
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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

REPO_ROOT = Path(__file__).resolve().parents[2]
REST_READY_URL = "http://127.0.0.1:8800/ready"
REST_VALUE_URL = "http://127.0.0.1:8800/value"
REST_TABLE_SCHEMA_URL = "http://127.0.0.1:8800/table-schema"
AGENT_READY_TIMEOUT_SECONDS = 180.0
AGENT_E2E_LOG = REPO_ROOT / "logs" / "foobar-manager-registration-persistence-e2e-agent.log"

COMPILED_MIB = REPO_ROOT / "compiled-mibs" / "FOOBAR-MANAGER-REGISTRATION-MIB.py"
COMPILED_PYCACHE = REPO_ROOT / "compiled-mibs" / "__pycache__"
SCHEMA_DIR = REPO_ROOT / "agent-model" / "FOOBAR-MANAGER-REGISTRATION-MIB"
MIB_STATE = REPO_ROOT / "agent-model" / "mib_state.json"

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"

BASE_PREFIX = "1.3.6.1.4.1.8998.321654.1.1.1"
TABLE_OID = "1.3.6.1.4.1.8998.321654.1.1"
MANAGER_TRAP_PORT_OID = BASE_PREFIX + ".3"
MANAGER_ROWSTATUS_OID = BASE_PREFIX + ".4"

INDEX_IP = (127, 0, 0, 1)
INDEX_SEND_PORT = 2000
INDEX_SUFFIX = (*INDEX_IP, INDEX_SEND_PORT)

CREATE_AND_GO = 4
ACTIVE = 1
UPDATED_TRAP_PORT = 9162


class E2EFailure(RuntimeError):  # noqa: N818
    """Raised when any check in this E2E flow fails."""


def _find_udp_port_pids(port: int) -> list[int]:
    try:
        out = subprocess.check_output(  # noqa: S603
            ["lsof", "-nP", f"-iUDP:{port}", "-t"],  # noqa: S607
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    pids: list[int] = []
    for line in out.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        try:
            pids.append(int(line_stripped))
        except ValueError:
            continue
    return sorted(set(pids))


def _ensure_port_ready(port: int, force_kill_port_owner: bool) -> None:
    existing = _find_udp_port_pids(port)
    if not existing:
        return

    if not force_kill_port_owner:
        msg = (
            f"UDP port {port} already in use by PID(s) {existing}. "
            "Stop existing agent or re-run with --force-kill-port-owner."
        )
        raise E2EFailure(msg)

    print(f"[prep] Killing existing UDP:{port} owner(s): {existing}")
    for pid in existing:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _find_udp_port_pids(port):
            return
        time.sleep(0.2)

    msg = f"Failed to free UDP port {port} after terminating existing owner(s)"
    raise E2EFailure(msg)


def _purge_foobar_artifacts() -> None:
    print("[purge] Removing FOOBAR compiled/schema/state artifacts")

    if COMPILED_MIB.exists():
        COMPILED_MIB.unlink()
        print(f"  removed: {COMPILED_MIB}")

    if COMPILED_PYCACHE.exists():
        for pyc in COMPILED_PYCACHE.glob("FOOBAR-MANAGER-REGISTRATION-MIB*.pyc"):
            pyc.unlink()
            print(f"  removed: {pyc}")

    if SCHEMA_DIR.exists():
        for p in sorted(SCHEMA_DIR.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        SCHEMA_DIR.rmdir()
        print(f"  removed dir: {SCHEMA_DIR}")

    if MIB_STATE.exists():
        MIB_STATE.unlink()
        print(f"  removed: {MIB_STATE}")


def _safe_pretty(value: object) -> str:
    pretty = getattr(value, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(value)


async def _snmp_get(
    host: str,
    port: int,
    community: str,
    *oids: str,
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    result = cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
        ),
    )
    return result


async def _snmp_set(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    result = cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await set_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            *var_binds,
        ),
    )
    return result


def _rest_agent_ready() -> bool:
    try:
        with urllib.request.urlopen(REST_READY_URL, timeout=1.0) as response:
            return response.status == 200
    except (TimeoutError, OSError, urllib.error.HTTPError, urllib.error.URLError):
        return False


async def _wait_for_agent(
    host: str,
    port: int,
    timeout_seconds: float = AGENT_READY_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status = "no probe result yet"
    while time.monotonic() < deadline:
        result = await _snmp_get(host, port, "public", SYS_NAME_OID)
        err_ind, err_stat, _err_idx, _vbs = result
        if not err_ind and not err_stat:
            return
        rest_ready = _rest_agent_ready()
        last_status = (
            f"snmp errInd={err_ind!r} errStat={_safe_pretty(err_stat)} restReady={rest_ready}"
        )
        await asyncio.sleep(0.25)

    msg = f"Agent did not become ready within {timeout_seconds:.1f}s ({last_status})"
    raise E2EFailure(msg)


def _start_agent_process() -> subprocess.Popen[str]:
    AGENT_E2E_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fp = AGENT_E2E_LOG.open("w", encoding="utf-8")
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "run_agent_with_rest.py"],
        cwd=str(REPO_ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    proc._agent_log_fp = log_fp  # type: ignore[attr-defined]
    proc._agent_log_path = AGENT_E2E_LOG  # type: ignore[attr-defined]
    return proc


def _stop_agent_process(proc: subprocess.Popen[str]) -> None:
    log_fp = getattr(proc, "_agent_log_fp", None)

    if proc.poll() is not None:
        if log_fp is not None:
            log_fp.close()
        return

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    finally:
        if log_fp is not None:
            log_fp.close()


def _expect_ok(tag: str, result: tuple[Any, Any, Any, tuple[Any, ...]]) -> tuple[Any, ...]:
    err_ind, err_stat, err_idx, var_binds = result
    if err_ind:
        raise E2EFailure(f"{tag}: transport/protocol error: {err_ind}")
    if err_stat:
        raise E2EFailure(f"{tag}: SNMP error: {_safe_pretty(err_stat)} at {_safe_pretty(err_idx)}")
    return var_binds


def _read_rest_value(oid: str) -> object:
    query = urllib.parse.urlencode({"oid": oid})
    url = f"{REST_VALUE_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise E2EFailure(f"REST value read failed for {oid}: {exc}") from exc

    if not isinstance(payload, dict) or "value" not in payload:
        raise E2EFailure(f"Unexpected REST /value payload for {oid}: {payload!r}")
    return payload["value"]


def _read_rest_table_schema(oid: str) -> dict[str, object]:
    query = urllib.parse.urlencode({"oid": oid})
    url = f"{REST_TABLE_SCHEMA_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise E2EFailure(f"REST table-schema read failed for {oid}: {exc}") from exc

    if not isinstance(payload, dict):
        raise E2EFailure(f"Unexpected REST /table-schema payload for {oid}: {payload!r}")
    return cast("dict[str, object]", payload)


def _try_int(value: object) -> int | None:
    try:
        return int(cast("Any", value))
    except (TypeError, ValueError):
        return None


def _assert_state_contains_row(instance_suffix: str, expected_trap_port: int) -> None:
    if not MIB_STATE.exists():
        raise E2EFailure(f"Persisted state file not found: {MIB_STATE}")

    try:
        state_data = json.loads(MIB_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise E2EFailure(f"Failed to read persisted state file: {exc}") from exc

    tables = state_data.get("tables") if isinstance(state_data, dict) else None
    if not isinstance(tables, dict):
        raise E2EFailure("Persisted state file has no 'tables' object")

    row_data: object | None = None
    table_data = tables.get(BASE_PREFIX)
    if isinstance(table_data, dict):
        row_data = table_data.get(instance_suffix)

    if row_data is None:
        for candidate_table in tables.values():
            if isinstance(candidate_table, dict) and instance_suffix in candidate_table:
                row_data = candidate_table[instance_suffix]
                break

    if not isinstance(row_data, dict):
        raise E2EFailure(f"Row {instance_suffix} not found in persisted state tables")

    column_values = row_data.get("column_values")
    if not isinstance(column_values, dict):
        raise E2EFailure(f"Persisted row {instance_suffix} missing column_values")

    trap_port = column_values.get("managerTrapPort")
    if int(cast("Any", trap_port)) != expected_trap_port:
        raise E2EFailure(
            f"Persisted row {instance_suffix} trap port expected {expected_trap_port}, got {trap_port!r}"
        )


async def _exercise_and_verify(host: str, port: int) -> None:
    idx_oid_suffix = ".".join(str(x) for x in INDEX_SUFFIX)
    status_oid = f"{MANAGER_ROWSTATUS_OID}.{idx_oid_suffix}"
    trap_port_oid = f"{MANAGER_TRAP_PORT_OID}.{idx_oid_suffix}"

    print(f"[debug] status_oid={status_oid}")
    print(f"[debug] trap_port_oid={trap_port_oid}")

    print("[step] createAndGo row")
    create_result = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO))],
    )
    create_vbs = _expect_ok("createAndGo", create_result)
    if int(create_vbs[0][1]) != ACTIVE:
        raise E2EFailure(f"createAndGo expected active(1), got {_safe_pretty(create_vbs[0][1])}")

    print(f"[step] update managerTrapPort to {UPDATED_TRAP_PORT}")
    set_port_result = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(trap_port_oid), Integer(UPDATED_TRAP_PORT))],
    )
    _expect_ok("set trap port", set_port_result)

    print("[step] verify row via SNMP before restart")
    get_result = await _snmp_get(host, port, "public", status_oid, trap_port_oid)
    get_vbs = _expect_ok("get row pre-restart", get_result)
    if int(get_vbs[0][1]) != ACTIVE:
        raise E2EFailure(f"pre-restart RowStatus expected active(1), got {_safe_pretty(get_vbs[0][1])}")
    if int(get_vbs[1][1]) != UPDATED_TRAP_PORT:
        raise E2EFailure(
            f"pre-restart managerTrapPort expected {UPDATED_TRAP_PORT}, got {_safe_pretty(get_vbs[1][1])}"
        )

    print("[step] verify row persisted in agent model state")
    _assert_state_contains_row(idx_oid_suffix, UPDATED_TRAP_PORT)


async def run_flow(host: str, port: int, force_kill_port_owner: bool) -> int:
    _ensure_port_ready(port, force_kill_port_owner)
    _purge_foobar_artifacts()

    print("[start] Launching agent (phase 1)")
    proc = _start_agent_process()

    idx_oid_suffix = ".".join(str(x) for x in INDEX_SUFFIX)
    status_oid = f"{MANAGER_ROWSTATUS_OID}.{idx_oid_suffix}"
    trap_port_oid = f"{MANAGER_TRAP_PORT_OID}.{idx_oid_suffix}"

    try:
        await _wait_for_agent(host, port)
        print("[start] Agent ready (phase 1)")

        await _exercise_and_verify(host, port)

        print("[restart] Stopping agent for reboot check")
        _stop_agent_process(proc)
        proc = _start_agent_process()

        await _wait_for_agent(host, port)
        print("[start] Agent ready (phase 2)")

        print("[step] verify row via SNMP after restart")
        post_result = await _snmp_get(host, port, "public", status_oid, trap_port_oid)
        post_vbs = _expect_ok("get row post-restart", post_result)
        if int(post_vbs[0][1]) != ACTIVE:
            raise E2EFailure(
                f"post-restart RowStatus expected active(1), got {_safe_pretty(post_vbs[0][1])}"
            )
        post_trap_port = _try_int(post_vbs[1][1])
        if post_trap_port is None:
            raise E2EFailure(
                "post-restart managerTrapPort not materialized as int: "
                f"{_safe_pretty(post_vbs[1][1])}"
            )

        print("[step] verify row via REST /table-schema (UI browse proxy)")
        schema_payload = _read_rest_table_schema(TABLE_OID)
        instances = schema_payload.get("instances", [])
        if not isinstance(instances, list) or idx_oid_suffix not in instances:
            raise E2EFailure(
                f"REST table-schema instances missing row {idx_oid_suffix}: {instances!r}"
            )

        print("[step] verify row status via REST /value")
        rest_status = _read_rest_value(status_oid)

        if int(cast("Any", rest_status)) != ACTIVE:
            raise E2EFailure(
                f"REST status value expected active(1), got {rest_status!r}"
            )

        if post_trap_port != UPDATED_TRAP_PORT:
            raise E2EFailure(
                "post-restart managerTrapPort expected "
                f"{UPDATED_TRAP_PORT}, got {post_trap_port}"
            )

        print("[pass] FOOBAR row persistence E2E passed")
        return 0

    except E2EFailure as exc:
        print(f"[fail] {exc}")
        return 1

    finally:
        print("[stop] Stopping agent")
        _stop_agent_process(proc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="E2E for FOOBAR managerRegistration persistence over restart"
    )
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP agent UDP port")
    parser.add_argument(
        "--force-kill-port-owner",
        action="store_true",
        help="Terminate existing UDP listener(s) on the SNMP port before running",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    return asyncio.run(
        run_flow(
            host=args.host,
            port=args.port,
            force_kill_port_owner=args.force_kill_port_owner,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
