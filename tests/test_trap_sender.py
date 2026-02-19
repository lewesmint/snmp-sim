"""Tests for TrapSender using NotificationType API."""
import logging
import pytest
from pytest_mock import MockerFixture

from pysnmp.proto import rfc1902
from pysnmp.hlapi.v3arch.asyncio import ObjectIdentity, ObjectType, SnmpEngine

from app.cli_trap_sender import main as cli_main
from app.trap_sender import TrapSender


@pytest.fixture
def trap_sender() -> TrapSender:
    return TrapSender(dest=('localhost', 162), community='public')


def test_init(trap_sender: TrapSender) -> None:
    """Test TrapSender initialization."""
    assert trap_sender.snmp_engine is not None
    assert trap_sender.dest == ('localhost', 162)
    assert trap_sender.community == 'public'
    assert isinstance(trap_sender.logger, logging.Logger)


def test_init_with_custom_params() -> None:
    """Test TrapSender with custom parameters."""
    custom_sender = TrapSender(dest=('192.168.1.1', 1162), community='private')
    assert custom_sender.dest == ('192.168.1.1', 1162)
    assert custom_sender.community == 'private'


def test_coerce_varbind_object_type(trap_sender: TrapSender) -> None:
    """Test _coerce_varbind with an ObjectType instance."""
    obj_type = ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0), rfc1902.OctetString('test'))
    result = trap_sender._coerce_varbind(obj_type)
    assert result is obj_type


def test_coerce_varbind_scalar_tuple(trap_sender: TrapSender) -> None:
    """Test _coerce_varbind with scalar tuple (mib, symbol, value)."""
    result = trap_sender._coerce_varbind(('SNMPv2-MIB', 'sysDescr', rfc1902.OctetString('test')))
    assert isinstance(result, ObjectType)


def test_coerce_varbind_indexed_tuple(trap_sender: TrapSender) -> None:
    """Test _coerce_varbind with indexed tuple (mib, symbol, value, index)."""
    result = trap_sender._coerce_varbind(('IF-MIB', 'ifOperStatus', rfc1902.Integer32(1), 2))
    assert isinstance(result, ObjectType)


def test_coerce_varbind_invalid_type(trap_sender: TrapSender) -> None:
    """Test _coerce_varbind with invalid type."""
    with pytest.raises(TypeError, match="extra_varbinds entries must be ObjectType or tuple"):
        trap_sender._coerce_varbind("invalid")  # pyright: ignore[reportArgumentType]


def test_send_mib_notification_sync(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    """Test synchronous send_mib_notification."""
    mock_async = mocker.patch.object(trap_sender, 'send_mib_notification_async', new_callable=mocker.AsyncMock)
    mock_async.return_value = None

    # Mock asyncio.run to execute the coroutine
    import asyncio
    from typing import Any, Coroutine

    def mock_run(coro: Coroutine[Any, Any, Any]) -> Any:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    mocker.patch('asyncio.run', side_effect=mock_run)
    mocker.patch('asyncio.get_running_loop', side_effect=RuntimeError("No running loop"))

    trap_sender.send_mib_notification(
        mib='SNMPv2-MIB',
        notification='coldStart',
        trap_type='trap'
    )

    mock_async.assert_called_once_with(
        mib='SNMPv2-MIB',
        notification='coldStart',
        trap_type='trap',
        extra_varbinds=None
    )


def test_send_mib_notification_reuses_provided_engine(mocker: MockerFixture) -> None:
    """Test provided snmp_engine is passed through to send_notification."""
    external_engine = SnmpEngine()
    sender = TrapSender(
        dest=('localhost', 162),
        community='public',
        snmp_engine=external_engine,
    )

    mocker.patch('app.trap_sender.UdpTransportTarget.create', new_callable=mocker.AsyncMock, return_value=object())
    mock_send = mocker.patch(
        'app.trap_sender.send_notification',
        new_callable=mocker.AsyncMock,
        return_value=(None, 0, 0, []),
    )

    sender.send_mib_notification(
        mib='SNMPv2-MIB',
        notification='coldStart',
        trap_type='trap',
    )

    assert mock_send.await_count == 1
    assert mock_send.await_args is not None
    call_args = mock_send.await_args.args
    assert call_args[0] is external_engine


def test_send_mib_notification_reuses_internal_engine(mocker: MockerFixture) -> None:
    """Test internal sender mode uses same engine across sends."""
    sender = TrapSender(dest=('localhost', 162), community='public')

    mocker.patch('app.trap_sender.UdpTransportTarget.create', new_callable=mocker.AsyncMock, return_value=object())
    mock_send = mocker.patch(
        'app.trap_sender.send_notification',
        new_callable=mocker.AsyncMock,
        return_value=(None, 0, 0, []),
    )

    sender.send_mib_notification(
        mib='SNMPv2-MIB',
        notification='coldStart',
        trap_type='trap',
    )
    sender.send_mib_notification(
        mib='SNMPv2-MIB',
        notification='coldStart',
        trap_type='trap',
    )

    assert mock_send.await_count == 2
    first_engine = mock_send.await_args_list[0].args[0]
    second_engine = mock_send.await_args_list[1].args[0]
    assert first_engine is sender.snmp_engine
    assert second_engine is sender.snmp_engine


def test_cli_missing_required_args(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI with missing required arguments."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--mib", "SNMPv2-MIB"])
    output = capsys.readouterr()
    assert exc_info.value.code == 2  # argparse exits with 2 for missing required args
    assert "required" in output.err.lower()


def test_cli_sends_notification(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI sends notification using new NotificationType API."""
    mock_sender = mocker.MagicMock()
    mocker.patch("app.cli_trap_sender.TrapSender", return_value=mock_sender)

    exit_code = cli_main([
        "--mib", "SNMPv2-MIB",
        "--notification", "coldStart",
        "--host", "localhost",
        "--port", "162",
        "--trap-type", "trap",
    ])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "Sent trap SNMPv2-MIB::coldStart" in output.out
    mock_sender.send_mib_notification.assert_called_once_with(
        mib="SNMPv2-MIB",
        notification="coldStart",
        trap_type="trap",
        extra_varbinds=None,
    )


def test_cli_sends_notification_with_varbinds(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI sends notification with extra varbinds."""
    mock_sender = mocker.MagicMock()
    mocker.patch("app.cli_trap_sender.TrapSender", return_value=mock_sender)

    exit_code = cli_main([
        "--mib", "IF-MIB",
        "--notification", "linkDown",
        "--varbind-index", "IF-MIB", "ifIndex", "1", "2",
        "--varbind-index", "IF-MIB", "ifOperStatus", "2", "2",
        "--trap-type", "inform",
    ])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "Sent inform IF-MIB::linkDown" in output.out

    # Verify send_mib_notification was called
    mock_sender.send_mib_notification.assert_called_once()
    call_args = mock_sender.send_mib_notification.call_args
    assert call_args.kwargs["mib"] == "IF-MIB"
    assert call_args.kwargs["notification"] == "linkDown"
    assert call_args.kwargs["trap_type"] == "inform"
    assert call_args.kwargs["extra_varbinds"] is not None
    assert len(call_args.kwargs["extra_varbinds"]) == 2
