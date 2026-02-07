"""CLI wrapper for sending SNMP traps using TrapSender."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, Tuple

from pyasn1.type.univ import Integer, OctetString
from pysnmp.smi import builder

from app.trap_sender import TrapSender


def _parse_oid(oid_str: str) -> Tuple[int, ...]:
    parts = [p for p in oid_str.strip().split(".") if p]
    return tuple(int(p) for p in parts)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send an SNMP trap or inform")
    parser.add_argument("--oid", required=True, help="OID, e.g. 1.3.6.1.4.1.99999.1.0")
    parser.add_argument("--value", required=True, help="Value to send")
    parser.add_argument(
        "--value-type",
        choices=["string", "int"],
        default="string",
        help="Value type (string|int)",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=162)
    parser.add_argument("--community", default="public")
    parser.add_argument("--trap-type", choices=["trap", "inform"], default="inform")
    parser.add_argument("--mib-name", default="__MY_MIB")

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        oid = _parse_oid(args.oid)
    except ValueError:
        print("Error: OID must be dot-separated integers", file=sys.stderr)
        return 1

    value = (
        Integer(int(args.value))
        if args.value_type == "int"
        else OctetString(args.value)
    )

    mib_builder = builder.MibBuilder()
    mib_builder.load_modules("SNMPv2-SMI")

    sender = TrapSender(
        mib_builder,
        dest=(args.host, args.port),
        community=args.community,
        mib_name=args.mib_name,
    )

    sender.send_trap(oid, value, trap_type=args.trap_type)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
