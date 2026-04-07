#!/usr/bin/env python3
"""
Cross-platform CLI for manual SNMP testing (works on Windows, macOS, Linux).

Usage:
    python snmp_cli_test.py get <host> <oid>
    python snmp_cli_test.py set <host> <oid> <value_type> <value>
    python snmp_cli_test.py walk <host> <oid>
    python snmp_cli_test.py test-workflow [host] [--base-oid <oid>] [--index-ip <ip>] [--index-port <port>]

Examples:
    # Test the standard FOOBAR MIB (OID 1.3.6.1.4.1.8998.321654)
    python snmp_cli_test.py test-workflow

    # Test with custom OIDs (for your extracted MIB)
    python snmp_cli_test.py test-workflow localhost:11161 \\
        --base-oid 1.3.6.1.4.1.YOUR.OID.1.1.1 \\
        --index-ip 127.0.0.1 \\
        --index-port 2000

    # Individual operations
    python snmp_cli_test.py get localhost:11161 1.3.6.1.2.1.1.5.0
    python snmp_cli_test.py set localhost:11161 1.3.6.1.4.1.8998.321654.1.1.1.4.127.0.0.1.2000 i 4
    python snmp_cli_test.py walk localhost:11161 1.3.6.1.4.1.8998.321654
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    Counter32,
    Integer,
    ObjectIdentity,
    ObjectType,
    OctetString,
    SnmpEngine,
    UdpTransportTarget,
    bulk_walk_cmd,
    get_cmd,
    set_cmd,
)


DEFAULT_HOST_PORT = "localhost:11161"
DEFAULT_BASE_OID = "1.3.6.1.4.1.8998.321654.1.1.1"
DEFAULT_READ_COMMUNITY = "public"
DEFAULT_WRITE_COMMUNITY = "private"


def format_snmp_error_status(err_stat: object) -> str:
    """Format an SNMP error status in a pyright-safe way."""
    pretty_print = getattr(err_stat, "prettyPrint", None)
    if callable(pretty_print):
        result = pretty_print()
        return str(result)
    return str(err_stat)


def parse_host_port(host_str: str) -> tuple[str, int]:
    """Parse 'host:port' or 'host' (defaults to 11161)."""
    if ":" in host_str:
        host, port_str = host_str.rsplit(":", 1)
        return host, int(port_str)
    return host_str, 11161


def parse_value(value_type_char: str, value_str: str) -> Any:
    """Parse SNMP value types: i=Integer, o=OctetString, c=Counter32, etc."""
    type_map = {
        "i": Integer,
        "o": OctetString,
        "c": Counter32,
        "s": OctetString,  # String
        "a": OctetString,  # IpAddress (as string)
        "d": OctetString,  # Opaque (as string)
    }
    value_cls = type_map.get(value_type_char, OctetString)
    try:
        if value_cls is Integer or value_cls is Counter32:
            return value_cls(int(value_str))
        return value_cls(value_str.encode() if isinstance(value_str, str) else value_str)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Failed to parse {value_type_char} value '{value_str}': {e}") from e


async def snmp_get(host: str, port: int, oid: str, community: str = "public") -> None:
    """GET a single OID."""
    engine = SnmpEngine()
    iterator = await get_cmd(
        engine,
        CommunityData(community),
        await UdpTransportTarget.create((host, port), timeout=5, retries=2),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    
    err_ind, err_stat, err_idx, var_binds = iterator
    
    if err_ind:
        print(f"ERROR: {err_ind}", file=sys.stderr)
        sys.exit(1)
    if err_stat:
        print(
            f"SNMP Error: {format_snmp_error_status(err_stat)} at index {err_idx}",
            file=sys.stderr,
        )
        sys.exit(1)
    
    for name, val in var_binds:
        print(f"{name} = {val}")


async def snmp_set(
    host: str,
    port: int,
    oid: str,
    value_type: str,
    value: str,
    community: str = DEFAULT_WRITE_COMMUNITY,
    strict: bool = True,
) -> bool:
    """SET a single OID."""
    engine = SnmpEngine()
    value_obj = parse_value(value_type, value)
    
    iterator = await set_cmd(
        engine,
        CommunityData(community, mpModel=1),  # SNMPv2c
        await UdpTransportTarget.create((host, port), timeout=5, retries=2),
        ContextData(),
        ObjectType(ObjectIdentity(oid), value_obj),
    )
    
    err_ind, err_stat, err_idx, var_binds = iterator
    
    if err_ind:
        print(f"ERROR: {err_ind}", file=sys.stderr)
        if strict:
            sys.exit(1)
        return False
    if err_stat:
        print(
            f"SNMP Error: {format_snmp_error_status(err_stat)} at index {err_idx}",
            file=sys.stderr,
        )
        if strict:
            sys.exit(1)
        return False
    
    for name, val in var_binds:
        print(f"{name} = {val}")
    return True


async def snmp_walk(host: str, port: int, oid: str, community: str = "public") -> None:
    """Walk an OID subtree."""
    engine = SnmpEngine()
    iterator = bulk_walk_cmd(
        engine,
        CommunityData(community),
        await UdpTransportTarget.create((host, port), timeout=5, retries=2),
        ContextData(),
        0,
        10,
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    )
    
    async for err_ind, err_stat, err_idx, var_binds in iterator:
        if err_ind:
            print(f"ERROR: {err_ind}", file=sys.stderr)
            break
        if err_stat:
            print(
                f"SNMP Error: {format_snmp_error_status(err_stat)} at index {err_idx}",
                file=sys.stderr,
            )
            break
        
        for name, val in var_binds:
            print(f"{name} = {val}")


async def test_workflow(
    host: str,
    port: int,
    base_oid: str = DEFAULT_BASE_OID,
    index_ip: str = "127.0.0.1",
    index_port: int = 2000,
    read_community: str = DEFAULT_READ_COMMUNITY,
    write_community: str = DEFAULT_WRITE_COMMUNITY,
) -> None:
    """Run the createAndGo/destroy workflow test."""
    # Build OIDs
    col_ip = base_oid + ".1"
    col_send_port = base_oid + ".2"
    col_trap_port = base_oid + ".3"
    col_rowstatus = base_oid + ".4"
    
    # Build index from IP and port
    ip_parts = [str(int(x)) for x in index_ip.split(".")]
    idx_suffix = ".".join(ip_parts) + "." + str(index_port)
    
    row_oid_prefix = base_oid + "." + idx_suffix
    rowstatus_oid = col_rowstatus + "." + idx_suffix
    trap_port_oid = col_trap_port + "." + idx_suffix
    
    print(f"[config] Base OID: {base_oid}")
    print(f"[config] Index IP: {index_ip}, Port: {index_port}")
    print(f"[config] Read community: {read_community}")
    print(f"[config] Write community: {write_community}")
    print(f"[config] Row OID suffix: {idx_suffix}")
    print(f"[config] RowStatus OID: {rowstatus_oid}")
    print()
    
    try:
        # Make repeated runs idempotent by trying to delete any pre-existing row.
        print("[prep] Attempting pre-clean destroy for target row (safe to ignore if missing)")
        print(f"  Command: snmpset -v2c -c {write_community} {host}:{port} {rowstatus_oid} i 6")
        _ = await snmp_set(
            host,
            port,
            rowstatus_oid,
            "i",
            "6",
            write_community,
            strict=False,
        )
        print()

        # Test 1: createAndGo (value=4)
        print("[test] SET createAndGo (value=4)")
        print(f"  Command: snmpset -v2c -c {write_community} {host}:{port} {rowstatus_oid} i 4")
        await snmp_set(host, port, rowstatus_oid, "i", "4", write_community)
        print()
        
        # Test 2: GET after create
        print("[test] GET managerRowStatus after create")
        print(f"  Command: snmpget -v2c -c {read_community} {host}:{port} {rowstatus_oid}")
        await snmp_get(host, port, rowstatus_oid, read_community)
        print()
        
        print("[test] GET managerTrapPort (should be DEFVAL=162)")
        print(f"  Command: snmpget -v2c -c {read_community} {host}:{port} {trap_port_oid}")
        await snmp_get(host, port, trap_port_oid, read_community)
        print()
        
        # Test 3: Walk the row
        print("[test] WALK full row")
        print(f"  Command: snmpwalk -v2c -c {read_community} {host}:{port} {row_oid_prefix}")
        await snmp_walk(host, port, row_oid_prefix, read_community)
        print()
        
        # Test 4: destroy (value=6)
        print("[test] SET destroy (value=6)")
        print(f"  Command: snmpset -v2c -c {write_community} {host}:{port} {rowstatus_oid} i 6")
        await snmp_set(host, port, rowstatus_oid, "i", "6", write_community)
        print()
        
        # Test 5: GET after destroy (expect error)
        print("[test] GET after destroy (expect error/noSuchInstance)")
        print(f"  Command: snmpget -v2c -c {read_community} {host}:{port} {rowstatus_oid}")
        await snmp_get(host, port, rowstatus_oid, read_community)
        
        print("\n[pass] Workflow test completed successfully")
        
    except Exception as e:
        print(f"\n[fail] Workflow test failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-platform CLI SNMP client for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # GET command
    get_parser = subparsers.add_parser("get", help="GET an OID")
    get_parser.add_argument("host_port", help="host:port or host (default port 11161)")
    get_parser.add_argument("oid", help="OID to get")
    get_parser.add_argument(
        "--community",
        default=DEFAULT_READ_COMMUNITY,
        help=f"Read community (default: {DEFAULT_READ_COMMUNITY})",
    )
    
    # SET command
    set_parser = subparsers.add_parser("set", help="SET an OID")
    set_parser.add_argument("host_port", help="host:port or host (default port 11161)")
    set_parser.add_argument("oid", help="OID to set")
    set_parser.add_argument("type", help="Value type: i=Integer, o=OctetString, s=String")
    set_parser.add_argument("value", help="Value to set")
    set_parser.add_argument(
        "--community",
        default=DEFAULT_WRITE_COMMUNITY,
        help=f"Write community (default: {DEFAULT_WRITE_COMMUNITY})",
    )
    
    # WALK command
    walk_parser = subparsers.add_parser("walk", help="WALK an OID subtree")
    walk_parser.add_argument("host_port", help="host:port or host (default port 11161)")
    walk_parser.add_argument("oid", help="OID to walk")
    walk_parser.add_argument(
        "--community",
        default=DEFAULT_READ_COMMUNITY,
        help=f"Read community (default: {DEFAULT_READ_COMMUNITY})",
    )
    
    # Test workflow command
    test_parser = subparsers.add_parser("test-workflow", help="Run createAndGo/destroy workflow")
    test_parser.add_argument(
        "host_port",
        nargs="?",
        default=DEFAULT_HOST_PORT,
        help=f"host:port or host (default: {DEFAULT_HOST_PORT})",
    )
    test_parser.add_argument(
        "--base-oid",
        default=DEFAULT_BASE_OID,
        help=f"Base OID for the table row (default: {DEFAULT_BASE_OID})",
    )
    test_parser.add_argument(
        "--index-ip",
        default="127.0.0.1",
        help="IP address for table index (default: 127.0.0.1)",
    )
    test_parser.add_argument(
        "--index-port",
        type=int,
        default=2000,
        help="Port number for table index (default: 2000)",
    )
    test_parser.add_argument(
        "--read-community",
        default=DEFAULT_READ_COMMUNITY,
        help=f"Read community (default: {DEFAULT_READ_COMMUNITY})",
    )
    test_parser.add_argument(
        "--write-community",
        default=DEFAULT_WRITE_COMMUNITY,
        help=f"Write community (default: {DEFAULT_WRITE_COMMUNITY})",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    host, port = parse_host_port(args.host_port)
    
    if args.command == "get":
        asyncio.run(snmp_get(host, port, args.oid, args.community))
    elif args.command == "set":
        asyncio.run(snmp_set(host, port, args.oid, args.type, args.value, args.community))
    elif args.command == "walk":
        asyncio.run(snmp_walk(host, port, args.oid, args.community))
    elif args.command == "test-workflow":
        asyncio.run(
            test_workflow(
                host,
                port,
                args.base_oid,
                args.index_ip,
                args.index_port,
                args.read_community,
                args.write_community,
            )
        )


if __name__ == "__main__":
    main()
