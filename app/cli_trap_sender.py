"""CLI wrapper for sending SNMP traps using TrapSender."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from pysnmp.proto import rfc1902

from app.oid_utils import oid_str_to_tuple
from app.trap_sender import TrapSender


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

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        oid = oid_str_to_tuple(args.oid)
    except ValueError:
        print("Error: OID must be dot-separated integers", file=sys.stderr)
        return 1

    # Create value using pysnmp types
    value = (
        rfc1902.Integer32(int(args.value))
        if args.value_type == "int"
        else rfc1902.OctetString(args.value)
    )

    sender = TrapSender(
        dest=(args.host, args.port),
        community=args.community,
    )

    sender.send_trap(oid, value, trap_type=args.trap_type)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
