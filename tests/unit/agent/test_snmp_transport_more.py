from app.snmp_transport import SNMPTransport


def test_init_start_stop() -> None:
    """Construct, start and stop the transport without errors."""
    t = SNMPTransport()
    assert t is not None
    # methods are no-ops but should not raise
    t.start()
    t.stop()


def test_start_stop_idempotent() -> None:
    """Calling start/stop multiple times should be safe/no-op."""
    t = SNMPTransport()
    t.start()
    t.start()
    t.stop()
    t.stop()
