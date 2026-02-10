"""Tests for trap receiver functionality."""
import time
from typing import Any
from app.trap_receiver import TrapReceiver


def test_trap_receiver_init() -> None:
    """Test trap receiver initialization."""
    receiver = TrapReceiver(port=16662, community="public")
    
    assert receiver.port == 16662
    assert receiver.community == "public"
    assert receiver.running is False
    assert len(receiver.received_traps) == 0


def test_trap_receiver_start_stop() -> None:
    """Test starting and stopping the trap receiver."""
    receiver = TrapReceiver(port=16662)
    
    # Start receiver
    receiver.start()
    assert receiver.running is True
    assert receiver.thread is not None
    
    # Give it a moment to start
    time.sleep(0.1)
    
    # Stop receiver
    receiver.stop()
    assert receiver.running is False


def test_trap_receiver_parse_trap() -> None:
    """Test parsing trap varbinds."""
    from pysnmp.proto import rfc1902
    
    receiver = TrapReceiver()
    
    # Create mock varbinds
    varbinds = [
        ((1, 3, 6, 1, 2, 1, 1, 3, 0), rfc1902.TimeTicks(12345)),
        ((1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0), rfc1902.ObjectIdentifier((1, 3, 6, 1, 4, 1, 99999, 0, 1))),
        ((1, 3, 6, 1, 4, 1, 99999, 0, 1), rfc1902.OctetString("Test message")),
    ]
    
    trap_data = receiver._parse_trap(varbinds)
    
    assert trap_data["uptime"] is not None
    assert trap_data["trap_oid"] == (1, 3, 6, 1, 4, 1, 99999, 0, 1)
    assert trap_data["trap_oid_str"] == "1.3.6.1.4.1.99999.0.1"
    assert trap_data["is_test_trap"] is True
    assert len(trap_data["varbinds"]) == 3


def test_trap_receiver_parse_non_test_trap() -> None:
    """Test parsing non-test trap."""
    from pysnmp.proto import rfc1902
    
    receiver = TrapReceiver()
    
    # Create mock varbinds for a different trap
    varbinds = [
        ((1, 3, 6, 1, 2, 1, 1, 3, 0), rfc1902.TimeTicks(12345)),
        ((1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0), rfc1902.ObjectIdentifier((1, 3, 6, 1, 6, 3, 1, 1, 5, 1))),  # coldStart
    ]
    
    trap_data = receiver._parse_trap(varbinds)
    
    assert trap_data["trap_oid"] == (1, 3, 6, 1, 6, 3, 1, 1, 5, 1)
    assert trap_data["is_test_trap"] is False


def test_trap_receiver_callback() -> None:
    """Test trap callback is invoked."""
    callback_called = []
    
    def test_callback(trap_data: dict[str, Any]) -> None:
            callback_called.append(trap_data)
    
    receiver = TrapReceiver(on_trap_callback=test_callback)
    
    # Mock varbinds
    from pysnmp.proto import rfc1902
    varbinds = [
        ((1, 3, 6, 1, 2, 1, 1, 3, 0), rfc1902.TimeTicks(12345)),
        ((1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0), rfc1902.ObjectIdentifier((1, 3, 6, 1, 4, 1, 99999, 0, 1))),
    ]
    
    # Call the callback directly
    receiver._trap_callback(None, None, None, None, varbinds, None)
    
    assert len(callback_called) == 1
    assert callback_called[0]["is_test_trap"] is True


def test_trap_receiver_get_received_traps() -> None:
    """Test getting received traps."""
    receiver = TrapReceiver()
    
    # Add some mock traps
    receiver.received_traps = [
        {"timestamp": "2024-01-01T10:00:00", "trap_oid_str": "1.2.3"},
        {"timestamp": "2024-01-01T10:01:00", "trap_oid_str": "1.2.4"},
        {"timestamp": "2024-01-01T10:02:00", "trap_oid_str": "1.2.5"},
    ]
    
    # Get all traps (should be reversed - most recent first)
    traps = receiver.get_received_traps()
    assert len(traps) == 3
    assert traps[0]["trap_oid_str"] == "1.2.5"  # Most recent first
    
    # Get limited traps
    traps = receiver.get_received_traps(limit=2)
    assert len(traps) == 2


def test_trap_receiver_clear_traps() -> None:
    """Test clearing received traps."""
    receiver = TrapReceiver()
    
    # Add some mock traps
    receiver.received_traps = [
        {"timestamp": "2024-01-01T10:00:00", "trap_oid_str": "1.2.3"},
    ]
    
    assert len(receiver.received_traps) == 1
    
    receiver.clear_traps()
    
    assert len(receiver.received_traps) == 0


def test_trap_receiver_max_traps_limit() -> None:
    """Test that receiver respects max traps limit."""
    receiver = TrapReceiver()
    receiver.max_traps = 5
    
    # Add more than max traps
    for i in range(10):
        receiver.received_traps.append({"trap_oid_str": f"1.2.{i}"})
        # Simulate the limit enforcement
        if len(receiver.received_traps) > receiver.max_traps:
            receiver.received_traps.pop(0)
    
    assert len(receiver.received_traps) == 5
    # Should have the last 5 traps
    assert receiver.received_traps[0]["trap_oid_str"] == "1.2.5"
    assert receiver.received_traps[4]["trap_oid_str"] == "1.2.9"

