import logging
import pytest
from pytest_mock import MockerFixture
from typing import cast

from pysnmp.proto import rfc1902

from app.cli_trap_sender import main as cli_main
from app.trap_sender import TrapSender

@pytest.fixture
def trap_sender() -> TrapSender:
    return TrapSender(dest=('localhost', 162), community='public')

def test_init(trap_sender: TrapSender) -> None:
    assert trap_sender.snmpEngine is not None
    assert trap_sender.dest == ('localhost', 162)
    assert trap_sender.community == 'public'
    assert isinstance(trap_sender.logger, logging.Logger)
    assert trap_sender.start_time > 0

def test_init_with_custom_params() -> None:
    custom_sender = TrapSender(dest=('192.168.1.1', 1162), community='private')
    assert custom_sender.dest == ('192.168.1.1', 1162)
    assert custom_sender.community == 'private'

def test_send_trap_invalid_type(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_send = mocker.patch('app.trap_sender.send_notification')
    mock_error = mocker.patch.object(trap_sender.logger, 'error')

    from typing import Literal
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.OctetString('test'), trap_type=cast(Literal['trap', 'inform'], 'invalid'))
    mock_error.assert_called_once()
    assert 'Invalid trap_type' in mock_error.call_args[0][0]
    mock_send.assert_not_called()

def test_send_trap_success_trap(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_send = mocker.patch('app.trap_sender.send_notification', new_callable=mocker.AsyncMock)
    mock_run = mocker.patch('app.trap_sender.asyncio.run')
    from typing import Awaitable, Any
    def _run(coro: Awaitable[Any]) -> Any:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    mock_send.return_value = (None, 0, 0, [])
    mock_run.side_effect = _run
    mock_info = mocker.patch.object(trap_sender.logger, 'info')
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.OctetString('test'), trap_type='trap')
    mock_run.assert_called_once()
    mock_info.assert_called_once()
    assert 'Trap sent' in mock_info.call_args[0][0]

def test_send_trap_success_inform(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_send = mocker.patch('app.trap_sender.send_notification', new_callable=mocker.AsyncMock)
    mock_run = mocker.patch('app.trap_sender.asyncio.run')
    from typing import Awaitable, Any
    def _run(coro: Awaitable[Any]) -> Any:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    mock_send.return_value = (None, 0, 0, [])
    mock_run.side_effect = _run
    mock_info = mocker.patch.object(trap_sender.logger, 'info')
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.Integer32(42), trap_type='inform')
    mock_run.assert_called_once()
    mock_info.assert_called_once()
    assert 'Trap sent' in mock_info.call_args[0][0]

def test_send_trap_with_error_indication(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_send = mocker.patch('app.trap_sender.send_notification', new_callable=mocker.AsyncMock)
    mock_run = mocker.patch('app.trap_sender.asyncio.run')
    from typing import Awaitable, Any
    def _run(coro: Awaitable[Any]) -> Any:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    mock_send.return_value = ('Network timeout', 0, 0, [])
    mock_run.side_effect = _run
    mock_error = mocker.patch.object(trap_sender.logger, 'error')
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.OctetString('test'), trap_type='trap')
    mock_error.assert_called_once()
    assert 'Trap send error' in mock_error.call_args[0][0]

def test_send_trap_exception_during_send(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_run = mocker.patch('app.trap_sender.asyncio.run')
    from typing import Coroutine, Any
    def _raise(coro: Coroutine[Any, Any, Any]) -> None:
        coro.close()
        raise RuntimeError('Connection failed')
    mock_run.side_effect = _raise
    mock_exception = mocker.patch.object(trap_sender.logger, 'exception')
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.OctetString('test'), trap_type='inform')
    mock_exception.assert_called_once()
    assert 'Exception while sending SNMP trap' in mock_exception.call_args[0][0]

def test_send_trap_executes_async_send(trap_sender: TrapSender, mocker: MockerFixture) -> None:
    mock_send = mocker.patch('app.trap_sender.send_notification', new_callable=mocker.AsyncMock)
    mock_udp = mocker.patch('app.trap_sender.UdpTransportTarget.create', new_callable=mocker.AsyncMock)
    mock_send.return_value = (None, 0, 0, [])
    mock_udp.return_value = mocker.MagicMock()
    mock_info = mocker.patch.object(trap_sender.logger, 'info')
    trap_sender.send_trap((1, 3, 6, 1, 4, 1, 99999, 1, 0), rfc1902.OctetString('test'), trap_type='trap')
    mock_send.assert_called_once()
    mock_udp.assert_called_once()
    mock_info.assert_called_once()


def test_cli_invalid_oid(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main(["--oid", "bad.oid", "--value", "test"])
    output = capsys.readouterr()
    assert exit_code == 1
    assert "OID must be dot-separated integers" in output.err


def test_cli_sends_trap(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    mock_sender = mocker.MagicMock()
    mocker.patch("app.cli_trap_sender.TrapSender", return_value=mock_sender)

    exit_code = cli_main([
        "--oid", "1.3.6.1.4.1.99999.1.0",
        "--value", "test",
        "--value-type", "string",
        "--trap-type", "trap",
    ])
    _output = capsys.readouterr()
    assert exit_code == 0
    mock_sender.send_trap.assert_called_once()
