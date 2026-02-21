"""CLI wrapper for sending SNMP traps using TrapSender.

This CLI sends MIB-defined NOTIFICATION-TYPEs using the NotificationType API.
For sending arbitrary traps, use the REST API /send-trap endpoint instead.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from pysnmp.proto import rfc1902

from app.trap_sender import TrapSender, VarBindSpec


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Send a MIB-defined SNMP notification (trap or inform)",
        epilog="Example: %(prog)s --mib SNMPv2-MIB --notification coldStart --host localhost --port 162",
    )
    parser.add_argument(
        "--mib", required=True, help="MIB name, e.g. SNMPv2-MIB or IF-MIB"
    )
    parser.add_argument(
        "--notification",
        required=True,
        help="Notification name, e.g. coldStart or linkDown",
    )
    parser.add_argument(
        "--host", default="localhost", help="Destination host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=162, help="Destination port (default: 162)"
    )
    parser.add_argument(
        "--community", default="public", help="SNMP community string (default: public)"
    )
    parser.add_argument(
        "--trap-type",
        choices=["trap", "inform"],
        default="inform",
        help="Notification type: trap (unconfirmed) or inform (confirmed)",
    )

    # Optional varbinds
    parser.add_argument(
        "--varbind",
        action="append",
        nargs=3,
        metavar=("MIB", "SYMBOL", "VALUE"),
        help="Add extra varbind: --varbind IF-MIB ifIndex 1 (can be repeated)",
    )
    parser.add_argument(
        "--varbind-index",
        action="append",
        nargs=4,
        metavar=("MIB", "SYMBOL", "VALUE", "INDEX"),
        help="Add indexed varbind: --varbind-index IF-MIB ifOperStatus 1 2 (can be repeated)",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # Build extra varbinds list
    extra_varbinds: list[VarBindSpec] = []

    if args.varbind:
        for mib, symbol, value in args.varbind:
            # Try to parse value as int, otherwise use string
            try:
                parsed_value = rfc1902.Integer32(int(value))
            except ValueError:
                parsed_value = rfc1902.OctetString(value)

            extra_varbinds.append((mib, symbol, parsed_value))

    if args.varbind_index:
        for mib, symbol, value, index in args.varbind_index:
            # Try to parse value as int, otherwise use string
            try:
                parsed_value = rfc1902.Integer32(int(value))
            except ValueError:
                parsed_value = rfc1902.OctetString(value)

            # Try to parse index as int, otherwise use string
            parsed_index: int | str
            try:
                parsed_index = int(index)
            except ValueError:
                parsed_index = index

            extra_varbinds.append((mib, symbol, parsed_value, parsed_index))

    sender = TrapSender(
        dest=(args.host, args.port),
        community=args.community,
    )

    try:
        sender.send_mib_notification(
            mib=args.mib,
            notification=args.notification,
            trap_type=args.trap_type,
            extra_varbinds=extra_varbinds if extra_varbinds else None,
        )
        print(
            f"✓ Sent {args.trap_type} {args.mib}::{args.notification} to {args.host}:{args.port}"
        )
        return 0
    except Exception as e:
        print(f"Error sending notification: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
