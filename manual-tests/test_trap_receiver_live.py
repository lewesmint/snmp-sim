#!/usr/bin/env python3
"""Manual test to verify Trap Receiver works end-to-end."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from snmp_traps.trap_receiver import TrapReceiver
from snmp_traps.trap_sender import TrapSender


def main() -> None:
    """Run manual trap receiver test."""
    print("\n" + "=" * 70)
    print("TRAP RECEIVER LIVE TEST")
    print("=" * 70)

    # Configuration
    test_port = 16662
    test_community = "public"

    print(f"\n✓ Starting Trap Receiver on port {test_port}...")
    receiver = TrapReceiver(
        host="127.0.0.1",
        port=test_port,
        community=test_community,
    )

    # Start receiver
    receiver.start()
    time.sleep(0.5)

    if not receiver.is_running():
        print("✗ Failed to start receiver!")
        return

    print("✓ Trap Receiver is running")

    try:
        print(f"\n✓ Sending test trap via TrapSender to localhost:{test_port}...")
        sender = TrapSender(
            dest=("localhost", test_port),
            community=test_community,
        )

        # Send a coldStart trap
        sender.send_mib_notification(
            mib="SNMPv2-MIB",
            notification="coldStart",
            trap_type="trap",
        )

        print("✓ Trap sent, waiting for reception...")
        time.sleep(1.0)

        # Get received traps
        traps = receiver.get_received_traps()
        trap_count = len(traps)

        print(f"\n{'=' * 70}")
        print(f"RESULT: {trap_count} trap(s) received")
        print(f"{'=' * 70}")

        if trap_count > 0:
            trap = traps[0]
            print(f"\n✓ Trap Details:")
            print(f"  Timestamp:  {trap.get('timestamp')}")
            print(f"  Trap OID:   {trap.get('trap_oid_str')}")
            print(f"  Is Test:    {trap.get('is_test_trap')}")
            varbinds = trap.get('varbinds', [])
            print(f"  Varbinds:   {len(varbinds) if isinstance(varbinds, (list, tuple)) else 0} received")

            if trap.get("varbinds"):
                print(f"\n  Varbind Details:")
                varbinds = trap.get("varbinds", [])
                if isinstance(varbinds, (list, tuple)):
                    for vb in varbinds[:5]:  # Show first 5
                        print(f"    - {vb.get('oid_str')}: {vb.get('value')}")

            print("\n✓ TRAP RECEIVER IS WORKING!")
        else:
            print("\n✗ No traps were received - Trap Receiver may not be working")

    finally:
        print("\n✓ Stopping receiver...")
        receiver.stop()
        print("✓ Test complete")


if __name__ == "__main__":
    main()
