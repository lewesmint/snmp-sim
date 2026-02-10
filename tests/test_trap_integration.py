"""Integration tests for trap sender and receiver."""
import time
from typing import Any
from app.trap_sender import TrapSender
from app.trap_receiver import TrapReceiver
from pysnmp.proto import rfc1902


def test_send_and_receive_test_trap() -> None:
    """Test sending and receiving a test trap."""
    # Use a unique port to avoid conflicts
    test_port = 16663

    # Track received traps
    received_traps = []

    def trap_callback(trap_data: dict[str, Any]) -> None:
        received_traps.append(trap_data)

    # Start receiver
    receiver = TrapReceiver(
        port=test_port,
        community="public",
        on_trap_callback=trap_callback
    )
    receiver.start()

    # Give receiver time to start
    time.sleep(0.5)

    try:
        # Send test trap
        sender = TrapSender(
            dest=("localhost", test_port),
            community="public"
        )

        test_trap_oid = (1, 3, 6, 1, 4, 1, 99999, 0, 1)
        sender.send_trap(
            test_trap_oid,
            rfc1902.OctetString("Test message"),
            trap_type="trap"
        )

        # Wait for trap to be received
        time.sleep(1.0)

        # Verify trap was received
        assert len(received_traps) > 0, "No traps received"

        trap = received_traps[0]
        assert trap["is_test_trap"] is True
        assert trap["trap_oid"] == test_trap_oid
        assert trap["trap_oid_str"] == "1.3.6.1.4.1.99999.0.1"

        # Verify trap is in receiver's storage
        stored_traps = receiver.get_received_traps()
        assert len(stored_traps) > 0
        assert stored_traps[0]["is_test_trap"] is True

    finally:
        # Clean up
        receiver.stop()


def test_send_and_receive_regular_trap() -> None:
    """Test sending and receiving a regular (non-test) trap."""
    test_port = 16664

    received_traps = []

    def trap_callback(trap_data: dict[str, Any]) -> None:
        received_traps.append(trap_data)

    receiver = TrapReceiver(
        port=test_port,
        on_trap_callback=trap_callback
    )
    receiver.start()

    time.sleep(0.5)

    try:
        sender = TrapSender(dest=("localhost", test_port))

        # Send a coldStart trap
        coldstart_oid = (1, 3, 6, 1, 6, 3, 1, 1, 5, 1)
        sender.send_trap(
            coldstart_oid,
            rfc1902.OctetString("System starting"),
            trap_type="trap"
        )

        time.sleep(1.0)

        assert len(received_traps) > 0
        trap = received_traps[0]
        assert trap["is_test_trap"] is False
        assert trap["trap_oid"] == coldstart_oid

    finally:
        receiver.stop()


def test_receiver_clear_traps() -> None:
    """Test clearing received traps."""
    receiver = TrapReceiver(port=16665)
    
    # Add some mock traps
    receiver.received_traps = [
        {"timestamp": "2024-01-01T10:00:00", "trap_oid_str": "1.2.3"},
        {"timestamp": "2024-01-01T10:01:00", "trap_oid_str": "1.2.4"},
    ]
    
    assert len(receiver.received_traps) == 2
    
    receiver.clear_traps()
    
    assert len(receiver.received_traps) == 0
    assert len(receiver.get_received_traps()) == 0


def test_receiver_status() -> None:
    """Test receiver status checking."""
    receiver = TrapReceiver(port=16666)
    
    assert receiver.is_running() is False
    
    receiver.start()
    time.sleep(0.1)
    
    assert receiver.is_running() is True
    
    receiver.stop()
    
    assert receiver.is_running() is False

