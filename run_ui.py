"""Root launcher for the SNMP GUI application."""

from __future__ import annotations

import sys

from ui.snmp_gui import main


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
