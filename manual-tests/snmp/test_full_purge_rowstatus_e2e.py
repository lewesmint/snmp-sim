#!/usr/bin/env python3
"""End-to-end purge-and-validate run for TEST-ENUM-MIB RowStatus behavior.

What this script does:
1) Purges TEST-ENUM artifacts (compiled MIB, schema, state)
2) Starts snmp-sim agent
3) Verifies baseline OID shape (including IpAddress index expansion)
4) Validates create/destroy on single-index RowStatus table
5) Validates create/destroy on multi-index RowStatus table (IpAddress + slot)
6) Stops the agent

Run from repo root:
    python manual-tests/snmp/test_full_purge_rowstatus_e2e.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
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
    next_cmd,
    set_cmd,
)
from pysnmp.proto.rfc1902 import Integer

REPO_ROOT = Path(__file__).resolve().parents[2]

COMPILED_TEST_ENUM = REPO_ROOT / "compiled-mibs" / "TEST-ENUM-MIB.py"
COMPILED_TEST_ENUM_PYCACHE = REPO_ROOT / "compiled-mibs" / "__pycache__"
SCHEMA_DIR = REPO_ROOT / "agent-model" / "TEST-ENUM-MIB"
MIB_STATE = REPO_ROOT / "agent-model" / "mib_state.json"

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"

TEST_ROW_COLOUR_OID = "1.3.6.1.4.1.99998.1.2.1.2"
TEST_ROW_PRIORITY_OID = "1.3.6.1.4.1.99998.1.2.1.3"
TEST_ROW_STATUS_OID = "1.3.6.1.4.1.99998.1.2.1.4"

ENDPOINT_NAME_OID = "1.3.6.1.4.1.99998.1.3.1.3"

ADDR_STATUS_COLOUR_OID = "1.3.6.1.4.1.99998.1.7.1.3"
ADDR_STATUS_PRIORITY_OID = "1.3.6.1.4.1.99998.1.7.1.4"
ADDR_STATUS_ROWSTATUS_OID = "1.3.6.1.4.1.99998.1.7.1.5"

TEST_ENUM_TABLE_OID = "1.3.6.1.4.1.99998.1.2"
ADDR_STATUS_TABLE_OID = "1.3.6.1.4.1.99998.1.7"

CREATE_AND_GO = 4
DESTROY = 6
ACTIVE = 1


class E2EFailure(RuntimeError):
    """Raised when an assertion in the end-to-end flow fails."""


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


def _ensure_port_ready(port: int, force_kill_port_owner: bool) -> None:
    existing = _find_udp_port_pids(port)
    if not existing:
        return

    if not force_kill_port_owner:
        raise E2EFailure(
            f"UDP port {port} already in use by PID(s) {existing}. "
            "Stop existing agent or re-run with --force-kill-port-owner."
        )

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

    raise E2EFailure(f"Failed to free UDP port {port} after terminating existing owner(s)")


def _row_oid(base_oid: str, *index_parts: int) -> str:
    suffix = ".".join(str(x) for x in index_parts)
    return f"{base_oid}.{suffix}" if suffix else base_oid


def _oid_to_dotted(value: object) -> str:
    try:
        return ".".join(str(int(x)) for x in cast("Any", value))
    except Exception as exc:  # noqa: BLE001
        raise E2EFailure(f"Failed to convert OID to dotted string: {value!r}") from exc


def _safe_pretty(value: object) -> str:
    pretty = getattr(value, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(value)


def _purge_test_enum_artifacts() -> None:
    print("[purge] Removing TEST-ENUM compiled/schema/state artifacts")

    if COMPILED_TEST_ENUM.exists():
        COMPILED_TEST_ENUM.unlink()
        print(f"  removed: {COMPILED_TEST_ENUM}")

    if COMPILED_TEST_ENUM_PYCACHE.exists():
        for pyc in COMPILED_TEST_ENUM_PYCACHE.glob("TEST-ENUM-MIB*.pyc"):
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


async def _snmp_get(host: str, port: int, community: str, *oids: str) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
        ),
    )


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
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *var_binds,
        ),
    )


async def _snmp_getnext(host: str, port: int, community: str, oid: str) -> tuple[str, object]:
    result = cast(
        "tuple[Any, Any, Any, tuple[Any, ...]]",
        await next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        ),
    )

    err_ind, err_stat, err_idx, var_binds = result
    if err_ind:
        raise E2EFailure(f"GETNEXT transport/protocol error: {err_ind}")
    if err_stat:
        raise E2EFailure(f"GETNEXT SNMP error: {_safe_pretty(err_stat)} at {err_idx}")
    if not var_binds:
        raise E2EFailure("GETNEXT returned no var-binds")

    vb = var_binds[0]
    return _oid_to_dotted(vb[0]), vb[1]


async def _snmp_walk_table(
    host: str, port: int, community: str, table_oid: str
) -> list[tuple[str, object]]:
    """Walk all OIDs under table_oid and return (oid_str, value) pairs."""
    results: list[tuple[str, object]] = []
    current_oid = table_oid
    prefix = table_oid + "."
    while True:
        result = cast(
            "tuple[Any, Any, Any, tuple[Any, ...]]",
            await next_cmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                await UdpTransportTarget.create((host, port)),
                ContextData(),
                ObjectType(ObjectIdentity(current_oid)),
            ),
        )
        err_ind, err_stat, _, var_binds = result
        if err_ind or err_stat or not var_binds:
            break
        vb = var_binds[0]
        next_oid = _oid_to_dotted(vb[0])
        if not next_oid.startswith(prefix):
            break
        results.append((next_oid, vb[1]))
        current_oid = next_oid
    return results


def _run_snmptable(host: str, port: int, community: str, table_oid: str) -> str | None:
    """Run net-snmp snmptable and return stdout, or None if snmptable is unavailable."""
    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "snmptable",
                "-v2c",
                f"-c{community}",
                "-On",
                "-Cb",
                f"{host}:{port}",
                table_oid,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"  [warn] snmptable exited {result.returncode}: {result.stderr.strip()}")
            return None
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [warn] snmptable not available: {exc}")
        return None


async def _wait_for_agent(host: str, port: int, timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        err_ind, err_stat, _, _ = await _snmp_get(host, port, "public", SYS_NAME_OID)
        if not err_ind and not err_stat:
            return
        await asyncio.sleep(0.5)
    raise E2EFailure(f"Agent did not become ready within {timeout_seconds:.1f}s")


def _assert_process_owns_udp_port(proc: subprocess.Popen[str], port: int) -> None:
    pids = _find_udp_port_pids(port)
    if proc.pid is None:
        raise E2EFailure("Started agent process has no PID")
    if proc.pid not in pids:
        raise E2EFailure(
            f"Started process PID {proc.pid} does not own UDP:{port}; "
            f"current owner(s): {pids}"
        )


def _start_agent_process() -> subprocess.Popen[str]:
    cmd = [sys.executable, "run_agent_with_rest.py"]
    return subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _stop_agent_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _drain_agent_output(proc: subprocess.Popen[str], max_lines: int = 120) -> str:
    if proc.stdout is None:
        return ""

    lines: list[str] = []
    for _ in range(max_lines):
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())
    return "\n".join(lines)


async def _validate_baseline(host: str, port: int) -> None:
    print("[check] Baseline OID shape checks")

    status_next_oid, status_next_value = await _snmp_getnext(host, port, "public", TEST_ROW_STATUS_OID)
    print(f"  testRowStatus next: {status_next_oid} = {_safe_pretty(status_next_value)}")

    endpoint_next_oid, endpoint_next_value = await _snmp_getnext(host, port, "public", ENDPOINT_NAME_OID)
    print(f"  endPointName next: {endpoint_next_oid} = {_safe_pretty(endpoint_next_value)}")

    if ".49.57.50.46.49.54.56.46.49.46.49" in endpoint_next_oid:
        raise E2EFailure(
            "IpAddress index appears ASCII-encoded in endpoint table OID suffix"
        )


async def _validate_single_index_rowstatus(host: str, port: int) -> None:
    print("[check] Single-index createAndGo/destroy")
    idx = 6421

    colour_oid = _row_oid(TEST_ROW_COLOUR_OID, idx)
    priority_oid = _row_oid(TEST_ROW_PRIORITY_OID, idx)
    status_oid = _row_oid(TEST_ROW_STATUS_OID, idx)

    # --- createAndGo ---
    err_ind, err_stat, err_idx, _ = await _snmp_set(
        host,
        port,
        "private",
        [
            ObjectType(ObjectIdentity(colour_oid), Integer(2)),
            ObjectType(ObjectIdentity(priority_oid), Integer(20)),
            ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO)),
        ],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Single-index createAndGo failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    # --- GET all columns and validate exact values ---
    err_ind, err_stat, err_idx, get_vbs = await _snmp_get(
        host,
        port,
        "public",
        colour_oid,
        priority_oid,
        status_oid,
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Single-index GET after create failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    colour_value = int(get_vbs[0][1])
    priority_value = int(get_vbs[1][1])
    status_value = int(get_vbs[2][1])

    if colour_value != 2:
        raise E2EFailure(f"Single-index colour mismatch: expected 2 got {colour_value}")
    if priority_value != 20:
        raise E2EFailure(f"Single-index priority mismatch: expected 20 got {priority_value}")
    if status_value != ACTIVE:
        raise E2EFailure(f"Single-index RowStatus not active(1); got {status_value}")

    print(f"  GET columns: colour={colour_value}, priority={priority_value}, rowStatus={status_value}")

    # --- snmptable: display full table (informational) ---
    table_output = _run_snmptable(host, port, "public", TEST_ENUM_TABLE_OID)
    if table_output is not None:
        print(f"  snmptable output:\n{table_output.rstrip()}")
        if str(idx) not in table_output:
            raise E2EFailure(f"Row index {idx} not found in snmptable output")

    # --- Walk table: verify all column OIDs exist for this row ---
    walk = await _snmp_walk_table(host, port, "public", TEST_ENUM_TABLE_OID)
    row_oids = [oid for oid, _ in walk if oid.endswith(f".{idx}")]
    if len(row_oids) < 3:
        raise E2EFailure(
            f"Expected ≥3 column OIDs for index {idx}, found {len(row_oids)}: {row_oids}"
        )
    print(f"  walk: {len(row_oids)} column OIDs present for index {idx}: {row_oids}")

    # --- destroy ---
    err_ind, err_stat, err_idx, _ = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_oid), Integer(DESTROY))],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Single-index destroy failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    # --- Post-destroy walk: verify no ghost entries ---
    post_walk = await _snmp_walk_table(host, port, "public", TEST_ENUM_TABLE_OID)
    ghost_oids = [oid for oid, _ in post_walk if oid.endswith(f".{idx}")]
    if ghost_oids:
        raise E2EFailure(f"Ghost OID(s) remain after single-index destroy: {ghost_oids}")
    print(f"  post-destroy walk: no ghost entries for index {idx}")


async def _validate_multi_index_rowstatus(host: str, port: int) -> None:
    print("[check] Multi-index (IpAddress + slot) createAndGo/destroy")

    ip_parts = (198, 51, 100, 10)
    slot = 77
    index_suffix = ".".join(str(x) for x in ip_parts) + f".{slot}"

    colour_oid = _row_oid(ADDR_STATUS_COLOUR_OID, *ip_parts, slot)
    priority_oid = _row_oid(ADDR_STATUS_PRIORITY_OID, *ip_parts, slot)
    status_oid = _row_oid(ADDR_STATUS_ROWSTATUS_OID, *ip_parts, slot)

    # --- createAndGo ---
    err_ind, err_stat, err_idx, _ = await _snmp_set(
        host,
        port,
        "private",
        [
            ObjectType(ObjectIdentity(colour_oid), Integer(3)),
            ObjectType(ObjectIdentity(priority_oid), Integer(30)),
            ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO)),
        ],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Multi-index createAndGo failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    # --- GET all columns and validate exact values ---
    err_ind, err_stat, err_idx, get_vbs = await _snmp_get(
        host,
        port,
        "public",
        colour_oid,
        priority_oid,
        status_oid,
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Multi-index GET after create failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    colour_value = int(get_vbs[0][1])
    priority_value = int(get_vbs[1][1])
    status_value = int(get_vbs[2][1])

    if colour_value != 3:
        raise E2EFailure(f"Multi-index colour mismatch: expected 3 got {colour_value}")
    if priority_value != 30:
        raise E2EFailure(f"Multi-index priority mismatch: expected 30 got {priority_value}")
    if status_value != ACTIVE:
        raise E2EFailure(f"Multi-index RowStatus not active(1); got {status_value}")

    print(f"  GET columns: colour={colour_value}, priority={priority_value}, rowStatus={status_value}")

    # --- snmptable: display full table (informational) ---
    table_output = _run_snmptable(host, port, "public", ADDR_STATUS_TABLE_OID)
    if table_output is not None:
        print(f"  snmptable output:\n{table_output.rstrip()}")

    # --- Walk table: verify all column OIDs exist for this row ---
    walk = await _snmp_walk_table(host, port, "public", ADDR_STATUS_TABLE_OID)
    row_oids = [oid for oid, _ in walk if oid.endswith(index_suffix)]
    if len(row_oids) < 3:
        raise E2EFailure(
            f"Expected ≥3 column OIDs for {index_suffix}, found {len(row_oids)}: {row_oids}"
        )
    print(f"  walk: {len(row_oids)} column OIDs present for {index_suffix}: {row_oids}")

    # --- GETNEXT OID shape check (numeric IpAddress index expansion) ---
    prev_oid = _row_oid(ADDR_STATUS_ROWSTATUS_OID, *ip_parts, slot - 1)
    next_oid, next_value = await _snmp_getnext(host, port, "public", prev_oid)
    print(f"  multi-index status next: {next_oid} = {_safe_pretty(next_value)}")

    if not next_oid.startswith(_row_oid(ADDR_STATUS_ROWSTATUS_OID, *ip_parts)):
        raise E2EFailure(
            "Multi-index RowStatus OID prefix mismatch; expected numeric IpAddress index expansion"
        )

    if ".49.57.56.46.53.49.46.49.48.48.46.49.48" in next_oid:
        raise E2EFailure("Multi-index RowStatus OID looks ASCII-encoded")

    # --- destroy ---
    err_ind, err_stat, err_idx, _ = await _snmp_set(
        host,
        port,
        "private",
        [ObjectType(ObjectIdentity(status_oid), Integer(DESTROY))],
    )
    if err_ind or err_stat:
        raise E2EFailure(
            f"Multi-index destroy failed: {err_ind or _safe_pretty(err_stat)} at {err_idx}"
        )

    # --- Post-destroy walk: verify no ghost entries ---
    post_walk = await _snmp_walk_table(host, port, "public", ADDR_STATUS_TABLE_OID)
    ghost_oids = [oid for oid, _ in post_walk if oid.endswith(index_suffix)]
    if ghost_oids:
        raise E2EFailure(f"Ghost OID(s) remain after multi-index destroy: {ghost_oids}")
    print(f"  post-destroy walk: no ghost entries for {index_suffix}")


async def run_flow(
    host: str,
    port: int,
    keep_logs: bool,
    force_kill_port_owner: bool,
) -> int:
    _ensure_port_ready(port, force_kill_port_owner)
    _purge_test_enum_artifacts()

    print("[start] Launching agent")
    proc = _start_agent_process()

    try:
        await _wait_for_agent(host, port)
        _assert_process_owns_udp_port(proc, port)
        print("[start] Agent is ready")

        await _validate_baseline(host, port)
        await _validate_single_index_rowstatus(host, port)
        await _validate_multi_index_rowstatus(host, port)

        print("[pass] Full purge-and-run validation succeeded")
        return 0

    except E2EFailure as exc:
        print(f"[fail] {exc}")
        if keep_logs:
            print("[logs] Agent output (tail):")
            print(_drain_agent_output(proc))
        return 1

    finally:
        print("[stop] Stopping agent")
        _stop_agent_process(proc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full purge + RowStatus end-to-end validation")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP agent UDP port")
    parser.add_argument(
        "--keep-logs",
        action="store_true",
        help="Print captured agent output on failure",
    )
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
            keep_logs=args.keep_logs,
            force_kill_port_owner=args.force_kill_port_owner,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
