"""Integration test for trap receiver using net-snmp command-line tool."""

import shutil
import subprocess
import time
from typing import Any

import pytest

from snmp_traps.trap_receiver import TrapReceiver


requires_snmptrap = pytest.mark.skipif(
    shutil.which("snmptrap") is None,
    reason="Requires net-snmp snmptrap command-line tool to be installed",
)


@requires_snmptrap
def test_receive_trap_from_snmptrap_command() -> None:
    """Test receiving a trap sent via net-snmp snmptrap command-line tool."""
    test_port = 16666
    test_community = "public"

    received_traps = []

    def trap_callback(trap_data: dict[str, Any]) -> None:
        received_traps.append(trap_data)

    # Start receiver
    receiver = TrapReceiver(
        port=test_port,
        community=test_community,
        on_trap_callback=trap_callback,
    )
    receiver.start()

    # Give receiver time to start
    time.sleep(0.5)

    try:
        # Send trap using net-snmp snmptrap command
        # Format: snmptrap -v 2c -c <community> <host>:<port> <uptime> <trapOID> <varOID> <type> <value>
        trap_oid = "1.3.6.1.4.1.8072.999.1"  # Example trap OID
        var_oid = "1.3.6.1.4.1.8072.999.2"  # Variable OID
        cmd = [
            "snmptrap",
            "-v", "2c",
            "-c", test_community,
            f"localhost:{test_port}",
            "0",  # sysUpTime
            trap_oid,  # Trap OID
            var_oid,  # Variable OID
            "s",  # String type
            "Test trap from snmptrap command",
        ]

        # Execute snmptrap command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            pytest.skip(
                f"snmptrap command failed: {result.stderr}. "
                "This test requires net-snmp tools to be installed."
            )

        # Wait for trap to be received
        time.sleep(1.0)

        # Verify trap was received
        assert len(received_traps) > 0, "No traps received from snmptrap command"

        trap = received_traps[0]
        assert trap["trap_oid_str"] == trap_oid, f"Expected OID {trap_oid}, got {trap['trap_oid_str']}"
        assert len(trap["varbinds"]) >= 3, "Expected at least 3 varbinds (uptime, trapOID, message)"

        # Verify trap is in receiver's storage
        stored_traps = receiver.get_received_traps()
        assert len(stored_traps) > 0, "Trap not found in receiver storage"

    finally:
        receiver.stop()


@requires_snmptrap
def test_receive_multiple_traps_from_snmptrap() -> None:
    """Test receiving multiple traps from snmptrap command."""
    test_port = 16667
    test_community = "public"

    received_traps = []

    def trap_callback(trap_data: dict[str, Any]) -> None:
        received_traps.append(trap_data)

    receiver = TrapReceiver(
        port=test_port,
        community=test_community,
        on_trap_callback=trap_callback,
    )
    receiver.start()
    time.sleep(0.5)

    try:
        # Send multiple traps
        trap_oids = [
            "1.3.6.1.4.1.8072.999.1",
            "1.3.6.1.4.1.8072.999.2",
            "1.3.6.1.4.1.8072.999.3",
        ]

        for i, trap_oid in enumerate(trap_oids):
            var_oid = f"1.3.6.1.4.1.8072.999.{100 + i}"
            cmd = [
                "snmptrap",
                "-v", "2c",
                "-c", test_community,
                f"localhost:{test_port}",
                "0",
                trap_oid,
                var_oid,
                "s",
                f"Test trap {i+1}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                pytest.skip("snmptrap command failed - net-snmp tools may not be installed")

            time.sleep(0.2)  # Small delay between traps

        # Wait for all traps to be received
        time.sleep(0.5)

        # Verify all traps were received
        assert len(received_traps) >= 3, f"Expected at least 3 traps, got {len(received_traps)}"

        # Verify trap OIDs
        received_oids = [t["trap_oid_str"] for t in received_traps]
        for trap_oid in trap_oids:
            assert trap_oid in received_oids, f"OID {trap_oid} not found in received traps"

    finally:
        receiver.stop()
