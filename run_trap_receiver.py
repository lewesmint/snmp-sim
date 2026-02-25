"""Root launcher for the SNMP Trap Receiver CLI with default settings."""

from __future__ import annotations

import sys

from snmp_traps.trap_receiver import main

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
