#!/usr/bin/env python3
# ruff: noqa: T201,D103,PLR0915,TRY003,EM101,EM102,TRY300,SLF001,PLR2004,S310,RET504
"""Verbose E2E test for FOOBAR managerRegistration createAndGo flow.

This test focuses on:
- OID prefix: 1.3.6.1.4.1.4045.750829.1.1.1
- Index: managerIpAddress=127.0.0.1, managerSendPort=2000
- RowStatus createAndGo on managerRowStatus(.4)

It prints detailed intermediate diagnostics for every SNMP call:
- request varbinds
- errorIndication / errorStatus / errorIndex
- response varbinds
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import time
import urllib.error
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
AGENT_READY_TIMEOUT_SECONDS = 180.0
AGENT_E2E_LOG = REPO_ROOT / "logs" / "foobar-manager-registration-e2e-agent.log"

COMPILED_MIB = REPO_ROOT / "compiled-mibs" / "FOOBAR-MANAGER-REGISTRATION-MIB.py"
COMPILED_PYCACHE = REPO_ROOT / "compiled-mibs" / "__pycache__"
SCHEMA_DIR = REPO_ROOT / "agent-model" / "FOOBAR-MANAGER-REGISTRATION-MIB"
MIB_STATE = REPO_ROOT / "agent-model" / "mib_state.json"

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"

BASE_PREFIX = "1.3.6.1.4.1.8998.321654.1.1.1"
MANAGER_IP_OID = BASE_PREFIX + ".1"
MANAGER_SEND_PORT_OID = BASE_PREFIX + ".2"
MANAGER_TRAP_PORT_OID = BASE_PREFIX + ".3"
MANAGER_ROWSTATUS_OID = BASE_PREFIX + ".4"

INDEX_IP = (127, 0, 0, 1)
INDEX_SEND_PORT = 2000
INDEX_SUFFIX = (*INDEX_IP, INDEX_SEND_PORT)

CREATE_AND_GO = 4
DESTROY = 6
ACTIVE = 1


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


def _oid_to_dotted(value: object) -> str:
    return ".".join(str(int(x)) for x in cast("Any", value))


def _print_response(tag: str, result: tuple[Any, Any, Any, tuple[Any, ...]]) -> None:
    err_ind, err_stat, err_idx, var_binds = result
    status_text = _safe_pretty(err_stat) if err_stat else "0"
    idx_text = _safe_pretty(err_idx)
    print(f"[{tag}] errorIndication={err_ind}")
    print(f"[{tag}] errorStatus={status_text}")
    print(f"[{tag}] errorIndex={idx_text}")
    for vb in var_binds:
        oid_text = _oid_to_dotted(vb[0])
        val_text = _safe_pretty(vb[1])
        print(f"[{tag}] varBind {oid_text} = {val_text}")


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


async def _run_foobar_create_and_go(host: str, port: int) -> None:
    idx_oid_suffix = ".".join(str(x) for x in INDEX_SUFFIX)
    status_oid = f"{MANAGER_ROWSTATUS_OID}.{idx_oid_suffix}"
    trap_port_oid = f"{MANAGER_TRAP_PORT_OID}.{idx_oid_suffix}"

    print("[debug] test inputs")
    print(f"[debug] BASE_PREFIX={BASE_PREFIX}")
    print(f"[debug] index_ip={INDEX_IP} index_send_port={INDEX_SEND_PORT}")
    print(f"[debug] status_oid={status_oid}")
    print(f"[debug] trap_port_oid={trap_port_oid}")

    print("[step] SET createAndGo on managerRowStatus")
    set_result = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO))],
    )
    _print_response("set:createAndGo", set_result)

    err_ind, err_stat, err_idx, set_vbs = set_result
    if err_ind:
        msg = f"createAndGo transport/protocol error: {err_ind}"
        raise E2EFailure(msg)
    if err_stat:
        msg = f"createAndGo SNMP error: {_safe_pretty(err_stat)} at {_safe_pretty(err_idx)}"
        raise E2EFailure(msg)
    if int(set_vbs[0][1]) != ACTIVE:
        msg = f"createAndGo response value expected active(1), got {_safe_pretty(set_vbs[0][1])}"
        raise E2EFailure(msg)

    print("[step] GET managerRowStatus and managerTrapPort for same index")
    get_result = await _snmp_get(host, port, "public", status_oid, trap_port_oid)
    _print_response("get:row", get_result)

    err_ind, err_stat, err_idx, get_vbs = get_result
    if err_ind:
        raise E2EFailure(f"GET transport/protocol error: {err_ind}")
    if err_stat:
        raise E2EFailure(
            f"GET SNMP error: {_safe_pretty(err_stat)} at {_safe_pretty(err_idx)}"
        )

    status_value = int(get_vbs[0][1])
    trap_port_value = int(get_vbs[1][1])
    if status_value != ACTIVE:
        raise E2EFailure(f"managerRowStatus expected 1, got {status_value}")
    if trap_port_value != 162:
        raise E2EFailure(f"managerTrapPort expected default 162, got {trap_port_value}")

    print("[step] SET destroy on managerRowStatus")
    destroy_result = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_oid), Integer(DESTROY))],
    )
    _print_response("set:destroy", destroy_result)

    err_ind, err_stat, err_idx, _destroy_vbs = destroy_result
    if err_ind:
        raise E2EFailure(f"destroy transport/protocol error: {err_ind}")
    if err_stat:
        raise E2EFailure(
            f"destroy SNMP error: {_safe_pretty(err_stat)} at {_safe_pretty(err_idx)}"
        )

    print("[step] GET managerRowStatus after destroy (expect noSuchInstance)")
    post_result = await _snmp_get(host, port, "public", status_oid)
    _print_response("get:post-destroy", post_result)

    err_ind, err_stat, err_idx, post_vbs = post_result
    if err_ind:
        raise E2EFailure(f"post-destroy GET transport/protocol error: {err_ind}")
    if err_stat:
        raise E2EFailure(
            f"post-destroy GET SNMP error: {_safe_pretty(err_stat)} at {_safe_pretty(err_idx)}"
        )

    if not post_vbs:
        raise E2EFailure("post-destroy GET returned no varbind")

    post_text = _safe_pretty(post_vbs[0][1])
    if "No Such Instance" not in post_text:
        raise E2EFailure(f"expected No Such Instance after destroy, got: {post_text}")


async def run_flow(
    host: str,
    port: int,
    force_kill_port_owner: bool,
    use_existing_agent: bool,
) -> int:
    proc: subprocess.Popen[str] | None = None

    if use_existing_agent:
        print("[start] Using already-running agent")
    else:
        _ensure_port_ready(port, force_kill_port_owner)
        _purge_foobar_artifacts()
        print("[start] Launching agent")
        proc = _start_agent_process()

    try:
        await _wait_for_agent(host, port)
        print("[start] Agent is ready")

        await _run_foobar_create_and_go(host, port)

        print("[pass] FOOBAR manager registration E2E passed")
        return 0

    except E2EFailure as exc:
        print(f"[fail] {exc}")
        return 1

    finally:
        if proc is not None:
            print("[stop] Stopping agent")
            _stop_agent_process(proc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verbose E2E for FOOBAR managerRegistration createAndGo"
    )
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP agent UDP port")
    parser.add_argument(
        "--force-kill-port-owner",
        action="store_true",
        help="Terminate existing UDP listener(s) on the SNMP port before running",
    )
    parser.add_argument(
        "--use-existing-agent",
        action="store_true",
        help="Run against an already-started agent instead of launching one",
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
            use_existing_agent=args.use_existing_agent,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
