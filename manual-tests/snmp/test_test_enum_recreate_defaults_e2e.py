#!/usr/bin/env python3
"""Live E2E for TEST-ENUM RowStatus recreate/defaults behavior.

Scenario:
1) Create row with explicit values (colour=2, priority=20, status=createAndGo)
2) Verify row values, destroy row, verify noSuchInstance
3) Recreate new row with index-only createAndGo on RowStatus
4) Verify default values are readable over SNMP GET

This test is intentionally diagnostic:
- It tries a multi-varbind GET first
- If that times out/fails, it probes single-varbind GETs to isolate behavior
"""

# ruff:,D103,E501,EM101,EM102,EXE001,N818,PLR0915,PLW2901,T201,TRY003,TRY300

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
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
AGENT_E2E_LOG = REPO_ROOT / "logs" / "test-enum-e2e-agent.log"
SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"

TEST_ROW_COLOUR_OID = "1.3.6.1.4.1.99998.1.2.1.2"
TEST_ROW_PRIORITY_OID = "1.3.6.1.4.1.99998.1.2.1.3"
TEST_ROW_STATUS_OID = "1.3.6.1.4.1.99998.1.2.1.4"

CREATE_AND_GO = 4
ACTIVE = 1
DESTROY = 6


class E2EFailure(RuntimeError):
    """Raised when an E2E validation step fails."""


def _safe_pretty(value: object) -> str:
    pretty = getattr(value, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(value)


def _row_oid(base: str, index: int) -> str:
    return f"{base}.{index}"


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return sorted(set(pids))


async def _snmp_set(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await set_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            *var_binds,
        ),
    )


async def _snmp_get(
    host: str,
    port: int,
    community: str,
    var_binds: list[ObjectType],
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            *var_binds,
        ),
    )


async def _wait_for_agent(host: str, port: int, timeout_seconds: float = 25.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        err_ind, err_stat, _idx, _vbs = await _snmp_get(
            host,
            port,
            "public",
            [ObjectType(ObjectIdentity(SYS_NAME_OID))],
        )
        if not err_ind and not err_stat:
            return
        await asyncio.sleep(0.25)
    raise E2EFailure(f"Agent did not become ready within {timeout_seconds}s")


def _start_agent() -> subprocess.Popen[bytes]:
    AGENT_E2E_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fp = AGENT_E2E_LOG.open("ab")
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "run_agent_with_rest.py"],
        cwd=str(REPO_ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=False,
    )
    setattr(proc, "_agent_log_fp", log_fp)
    return proc


def _stop_agent(proc: subprocess.Popen[bytes]) -> None:
    log_fp = getattr(proc, "_agent_log_fp", None)

    if proc.poll() is not None:
        if log_fp is not None:
            with contextlib.suppress(Exception):
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
            with contextlib.suppress(Exception):
                log_fp.close()


async def _run_flow(host: str, port: int) -> None:
    base = int(time.time()) % 100000
    row_a = base
    row_b = base + 1

    colour_a = _row_oid(TEST_ROW_COLOUR_OID, row_a)
    priority_a = _row_oid(TEST_ROW_PRIORITY_OID, row_a)
    status_a = _row_oid(TEST_ROW_STATUS_OID, row_a)

    colour_b = _row_oid(TEST_ROW_COLOUR_OID, row_b)
    priority_b = _row_oid(TEST_ROW_PRIORITY_OID, row_b)
    status_b = _row_oid(TEST_ROW_STATUS_OID, row_b)

    print("[step] create row A with explicit values")
    err_ind, err_stat, err_idx, set_vbs = await _snmp_set(
        host,
        port,
        "private",
        [
            ObjectType(ObjectIdentity(colour_a), Integer(2)),
            ObjectType(ObjectIdentity(priority_a), Integer(20)),
            ObjectType(ObjectIdentity(status_a), Integer(CREATE_AND_GO)),
        ],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"row A create failed: errInd={err_ind}, errStat={_safe_pretty(err_stat)} idx={_safe_pretty(err_idx)}"
        )
    if int(set_vbs[2][1]) != ACTIVE:
        raise E2EFailure(f"row A status expected active(1), got {_safe_pretty(set_vbs[2][1])}")

    print("[step] verify row A values")
    err_ind, err_stat, err_idx, get_a = await _snmp_get(
        host,
        port,
        "public",
        [
            ObjectType(ObjectIdentity(colour_a)),
            ObjectType(ObjectIdentity(priority_a)),
            ObjectType(ObjectIdentity(status_a)),
        ],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"row A GET failed: errInd={err_ind}, errStat={_safe_pretty(err_stat)} idx={_safe_pretty(err_idx)}"
        )
    if [int(get_a[0][1]), int(get_a[1][1]), int(get_a[2][1])] != [2, 20, ACTIVE]:
        raise E2EFailure(f"row A values unexpected: {[ _safe_pretty(v[1]) for v in get_a ]}")

    print("[step] destroy row A")
    err_ind, err_stat, err_idx, _destroy = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_a), Integer(DESTROY))],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"row A destroy failed: errInd={err_ind}, errStat={_safe_pretty(err_stat)} idx={_safe_pretty(err_idx)}"
        )

    err_ind, err_stat, _idx, post = await _snmp_get(
        host,
        port,
        "public",
        [ObjectType(ObjectIdentity(status_a))],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"row A post-destroy GET failed: errInd={err_ind}, errStat={_safe_pretty(err_stat)}"
        )
    if "No Such Instance" not in _safe_pretty(post[0][1]):
        raise E2EFailure(f"row A expected No Such Instance, got {_safe_pretty(post[0][1])}")

    print("[step] create row B with index-only RowStatus createAndGo")
    err_ind, err_stat, err_idx, set_b = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_b), Integer(CREATE_AND_GO))],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"row B create failed: errInd={err_ind}, errStat={_safe_pretty(err_stat)} idx={_safe_pretty(err_idx)}"
        )
    if int(set_b[0][1]) not in {ACTIVE, CREATE_AND_GO}:
        raise E2EFailure(f"row B status response unexpected: {_safe_pretty(set_b[0][1])}")

    print("[step] verify row B defaults via multi-varbind GET")
    deadline = time.monotonic() + 12.0
    last: tuple[Any, Any, Any, tuple[Any, ...]] | None = None
    while time.monotonic() < deadline:
        last = await _snmp_get(
            host,
            port,
            "public",
            [
                ObjectType(ObjectIdentity(colour_b)),
                ObjectType(ObjectIdentity(priority_b)),
                ObjectType(ObjectIdentity(status_b)),
            ],
        )
        err_ind, err_stat, _idx, multi_vbs = last
        if not err_ind and not err_stat:
            got = [int(multi_vbs[0][1]), int(multi_vbs[1][1]), int(multi_vbs[2][1])]
            if got == [1, 10, ACTIVE]:
                print("[pass] row B defaults confirmed via multi-varbind GET: [1, 10, 1]")
                return
        await asyncio.sleep(0.25)

    print("[diag] multi-varbind GET did not confirm defaults; probing single-varbind GETs")
    single_results: list[tuple[str, tuple[Any, Any, Any, tuple[Any, ...]]]] = []
    for label, oid in (("colour", colour_b), ("priority", priority_b), ("status", status_b)):
        result = await _snmp_get(host, port, "public", [ObjectType(ObjectIdentity(oid))])
        single_results.append((label, result))

    for label, result in single_results:
        s_err_ind, s_err_stat, s_err_idx, s_vbs = result
        if s_err_ind or s_err_stat:
            print(
                f"[diag] {label}: errInd={s_err_ind} errStat={_safe_pretty(s_err_stat)} idx={_safe_pretty(s_err_idx)}"
            )
            continue
        if s_vbs:
            print(f"[diag] {label}: {_safe_pretty(s_vbs[0][1])}")

    raise E2EFailure(
        "row B default verification failed over SNMP (see diagnostics above)."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TEST-ENUM recreate/defaults live E2E")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11161, help="SNMP agent UDP port")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    os.chdir(REPO_ROOT)

    host = args.host
    port = args.port

    in_use = _find_udp_port_pids(port)
    if in_use:
        print(f"[fail] UDP port {port} already in use by PID(s): {in_use}")
        return 1

    print(f"[start] host={host} port={port}")
    proc = _start_agent()
    try:
        asyncio.run(_wait_for_agent(host, port))
        asyncio.run(_run_flow(host, port))
        print("[pass] TEST-ENUM recreate/defaults E2E passed")
        return 0
    except E2EFailure as exc:
        print(f"[fail] {exc}")
        return 1
    finally:
        _stop_agent(proc)


if __name__ == "__main__":
    raise SystemExit(main())
