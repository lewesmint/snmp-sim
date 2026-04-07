#!/usr/bin/env python3
"""Manual CREATE-AND-GO test for TEST-ENUM-MIB against local snmp-sim.

This script validates an SNMP manager workflow for RowStatus:
1) SET row columns + RowStatus=createAndGo(4) on a new index
2) GET RowStatus and row columns to confirm creation/activation
3) SET RowStatus=destroy(6)

Default target is localhost:11161 (snmp-sim default).
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
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

TEST_ROW_COLOUR_OID = "1.3.6.1.4.1.99998.1.2.1.2"
TEST_ROW_PRIORITY_OID = "1.3.6.1.4.1.99998.1.2.1.3"
TEST_ROW_STATUS_OID = "1.3.6.1.4.1.99998.1.2.1.4"

CREATE_AND_GO = 4
DESTROY = 6
ACTIVE = 1


async def _snmp_set(
    host: str,
    port: int,
    community: str,
    var_binds: Iterable[ObjectType],
) -> tuple[Any, Any, Any, tuple[ObjectType, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[ObjectType, ...]]",
        await set_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *list(var_binds),
        ),
    )


async def _snmp_get(
    host: str,
    port: int,
    community: str,
    var_binds: Iterable[ObjectType],
) -> tuple[Any, Any, Any, tuple[ObjectType, ...]]:
    return cast(
        "tuple[Any, Any, Any, tuple[ObjectType, ...]]",
        await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            await UdpTransportTarget.create((host, port)),
            ContextData(),
            *list(var_binds),
        ),
    )


def _row_oid(base_oid: str, index: int) -> str:
    return f"{base_oid}.{index}"


def _pretty(value: object) -> str:
    pretty = getattr(value, "prettyPrint", None)
    return str(pretty()) if callable(pretty) else str(value)


def _print_result(prefix: str, var_binds: tuple[ObjectType, ...]) -> None:
    for vb in var_binds:
        print(f"{prefix} {_pretty(vb[0])} = {_pretty(vb[1])}")


async def run_test(host: str, port: int, read_community: str, write_community: str, index: int) -> int:
    colour_oid = _row_oid(TEST_ROW_COLOUR_OID, index)
    priority_oid = _row_oid(TEST_ROW_PRIORITY_OID, index)
    status_oid = _row_oid(TEST_ROW_STATUS_OID, index)

    print("=== CREATE-AND-GO TEST ===")
    print(f"Target: {host}:{port}")
    print(f"Index: {index}")

    # Manager attempts one-shot create: writable columns + RowStatus=createAndGo(4)
    err_ind, err_stat, err_idx, set_vbs = await _snmp_set(
        host,
        port,
        write_community,
        [
            ObjectType(ObjectIdentity(colour_oid), Integer(2)),
            ObjectType(ObjectIdentity(priority_oid), Integer(20)),
            ObjectType(ObjectIdentity(status_oid), Integer(CREATE_AND_GO)),
        ],
    )

    if err_ind:
        print(f"FAIL: SET transport/protocol error: {err_ind}")
        return 1
    if err_stat:
        print(f"FAIL: SET SNMP error: {_pretty(err_stat)} at index {err_idx}")
        return 1

    _print_result("SET OK:", set_vbs)

    # Verify row exists and status is active(1)
    err_ind, err_stat, err_idx, get_vbs = await _snmp_get(
        host,
        port,
        read_community,
        [
            ObjectType(ObjectIdentity(colour_oid)),
            ObjectType(ObjectIdentity(priority_oid)),
            ObjectType(ObjectIdentity(status_oid)),
        ],
    )

    if err_ind:
        print(f"FAIL: GET transport/protocol error: {err_ind}")
        return 1
    if err_stat:
        print(f"FAIL: GET SNMP error: {_pretty(err_stat)} at index {err_idx}")
        return 1

    _print_result("GET OK:", get_vbs)

    status_value = int(get_vbs[2][1])
    if status_value != ACTIVE:
        print(
            "FAIL: RowStatus is not active(1) after createAndGo "
            f"(actual={status_value})."
        )
        return 1

    # Clean up created row
    err_ind, err_stat, err_idx, destroy_vbs = await _snmp_set(
        host,
        port,
        write_community,
        [ObjectType(ObjectIdentity(status_oid), Integer(DESTROY))],
    )

    if err_ind:
        print(f"FAIL: DESTROY transport/protocol error: {err_ind}")
        return 1
    if err_stat:
        print(f"FAIL: DESTROY SNMP error: {_pretty(err_stat)} at index {err_idx}")
        return 1

    _print_result("DESTROY OK:", destroy_vbs)
    print("PASS: createAndGo flow completed successfully.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CREATE-AND-GO test against snmp-sim")
    parser.add_argument("--host", default="127.0.0.1", help="SNMP agent host")
    parser.add_argument("--port", type=int, default=11161, help="SNMP agent UDP port")
    parser.add_argument("--read-community", default="public", help="Read community")
    parser.add_argument("--write-community", default="private", help="Write community")
    parser.add_argument("--index", type=int, default=4242, help="Row index to create")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(
        run_test(
            host=args.host,
            port=args.port,
            read_community=args.read_community,
            write_community=args.write_community,
            index=args.index,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
