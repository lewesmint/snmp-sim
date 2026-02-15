"""Unit tests for async_wrapper.py synchronous SNMP wrapper."""

import asyncio
import sys
import unittest
from typing import cast
from unittest.mock import MagicMock, Mock, patch

# Mock PySNMP imports before importing async_wrapper
sys.modules["pysnmp"] = MagicMock()
sys.modules["pysnmp.hlapi"] = MagicMock()
sys.modules["pysnmp.hlapi.asyncio"] = MagicMock()

from async_wrapper import (  # noqa: E402
    SnmpSyncError,
    SyncSnmpClient,
    _LoopThread,
    _raise_on_error,
    get_sync,
    make_oid,
    run_sync,
    set_sync,
    shutdown_sync_wrapper,
)


class TestRaiseOnError(unittest.TestCase):
    """Test error handling in _raise_on_error."""

    def test_no_error(self) -> None:
        """Should not raise when no errors."""
        _raise_on_error(None, None, None)
        _raise_on_error(None, 0, 0)

    def test_error_indication(self) -> None:
        """Should raise SnmpSyncError on error_indication."""
        with self.assertRaises(SnmpSyncError) as cm:
            _raise_on_error("Connection timeout", None, None)
        self.assertIn("Connection timeout", str(cm.exception))

    def test_error_status_with_pretty_print(self) -> None:
        """Should raise SnmpSyncError on error_status with pretty-printed message."""
        mock_status = MagicMock()
        mock_status.prettyPrint.return_value = "noAccess"

        with self.assertRaises(SnmpSyncError) as cm:
            _raise_on_error(None, mock_status, 0)
        self.assertIn("noAccess", str(cm.exception))
        self.assertIn("index 0", str(cm.exception))

    def test_error_status_with_error_index(self) -> None:
        """Should include error index in error message."""
        mock_status = MagicMock()
        mock_status.prettyPrint.return_value = "notWritable"

        with self.assertRaises(SnmpSyncError) as cm:
            _raise_on_error(None, mock_status, 2)
        self.assertIn("notWritable", str(cm.exception))
        self.assertIn("index 2", str(cm.exception))


class TestRunSync(unittest.TestCase):
    """Test the run_sync function for both sync and async context."""

    def test_run_sync_no_loop(self) -> None:
        """Should use asyncio.run when no event loop is running."""

        async def dummy_coro() -> int:
            return 42

        result = run_sync(dummy_coro())
        self.assertEqual(result, 42)

    def test_run_sync_with_running_loop(self) -> None:
        """Should use background loop thread when a loop is already running."""

        async def inner_coro() -> str:
            return "result_from_async"

        async def test_coro() -> str:
            # run_sync should detect the running loop and use background thread
            return cast(str, run_sync(inner_coro()))

        result = asyncio.run(test_coro())
        self.assertEqual(result, "result_from_async")


class TestGetSet(unittest.TestCase):
    """Test get_sync and set_sync functions."""

    @patch("async_wrapper.run_sync")
    def test_get_sync_success(self, mock_run: Mock) -> None:
        """Should return varBinds on successful GET."""
        mock_var_binds = (MagicMock(),)
        mock_run.return_value = (None, None, None, mock_var_binds)

        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        result = get_sync(mock_engine, mock_auth, address, (MagicMock(),))
        self.assertEqual(result, mock_var_binds)

    @patch("async_wrapper.run_sync")
    def test_get_sync_error(self, mock_run: Mock) -> None:
        """Should raise SnmpSyncError on GET error."""
        mock_run.return_value = ("timeout", None, None, None)

        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        with self.assertRaises(SnmpSyncError):
            get_sync(mock_engine, mock_auth, address, (MagicMock(),))

    @patch("async_wrapper.run_sync")
    def test_set_sync_success(self, mock_run: Mock) -> None:
        """Should return varBinds on successful SET."""
        mock_var_binds = (MagicMock(),)
        mock_run.return_value = (None, None, None, mock_var_binds)

        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        result = set_sync(mock_engine, mock_auth, address, (MagicMock(),))
        self.assertEqual(result, mock_var_binds)

    @patch("async_wrapper.run_sync")
    def test_set_sync_error(self, mock_run: Mock) -> None:
        """Should raise SnmpSyncError on SET error."""
        mock_status = MagicMock()
        mock_status.prettyPrint.return_value = "notWritable"
        mock_run.return_value = (None, mock_status, 0, None)

        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        with self.assertRaises(SnmpSyncError):
            set_sync(mock_engine, mock_auth, address, (MagicMock(),))


class TestSyncSnmpClient(unittest.TestCase):
    """Test the SyncSnmpClient convenience class."""

    @patch("async_wrapper.get_sync")
    def test_client_get(self, mock_get: Mock) -> None:
        """Should proxy get() to get_sync."""
        expected_result = (MagicMock(),)
        mock_get.return_value = expected_result
        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        client = SyncSnmpClient(engine=mock_engine, auth=mock_auth, address=address)
        mock_vb = MagicMock()

        result = client.get(mock_vb)

        mock_get.assert_called_once()
        self.assertEqual(result, expected_result)

    @patch("async_wrapper.set_sync")
    def test_client_set(self, mock_set: Mock) -> None:
        """Should proxy set() to set_sync."""
        expected_result = (MagicMock(),)
        mock_set.return_value = expected_result
        mock_engine = MagicMock()
        mock_auth = MagicMock()
        address = ("127.0.0.1", 161)

        client = SyncSnmpClient(engine=mock_engine, auth=mock_auth, address=address)
        mock_vb = MagicMock()

        result = client.set(mock_vb)

        mock_set.assert_called_once()
        self.assertEqual(result, expected_result)


class TestMakeOid(unittest.TestCase):
    """Test the make_oid helper function."""

    @patch("async_wrapper.ObjectIdentity")
    def test_make_oid(self, mock_oid_class: Mock) -> None:
        """Should create ObjectIdentity from OID string."""
        mock_oid_instance = MagicMock()
        mock_oid_class.return_value = mock_oid_instance

        result = make_oid("1.3.6.1.2.1.1.1.0")

        mock_oid_class.assert_called_once_with("1.3.6.1.2.1.1.1.0")
        self.assertEqual(result, mock_oid_instance)


class TestLoopThread(unittest.TestCase):
    """Test the _LoopThread background event loop."""

    def test_loop_thread_init(self) -> None:
        """Should initialize and start background event loop."""
        loop_thread = _LoopThread()
        self.assertIsNotNone(loop_thread.loop)
        self.assertTrue(loop_thread._thread.is_alive())

        # Cleanup
        loop_thread.stop()

    def test_loop_thread_run_coroutine(self) -> None:
        """Should execute coroutine on background loop."""

        async def test_coro() -> int:
            return 42

        loop_thread = _LoopThread()
        future = asyncio.run_coroutine_threadsafe(test_coro(), loop_thread.loop)
        result = future.result(timeout=2.0)

        self.assertEqual(result, 42)

        # Cleanup
        loop_thread.stop()

    def test_loop_thread_stop(self) -> None:
        """Should properly stop and clean up background loop."""
        loop_thread = _LoopThread()
        loop_thread.stop()

        # Thread should join within timeout
        # (we can't directly verify it stopped, but we can ensure stop() doesn't hang)
        self.assertFalse(loop_thread._thread.is_alive())


class TestShutdown(unittest.TestCase):
    """Test the shutdown_sync_wrapper function."""

    def test_shutdown_clears_global_state(self) -> None:
        """Should clear global loop thread on shutdown."""
        import async_wrapper

        # Trigger creation of global loop
        _ = async_wrapper._get_global_loop_thread()
        self.assertIsNotNone(async_wrapper._GLOBAL_LOOP_THREAD)

        # Shutdown
        shutdown_sync_wrapper()
        self.assertIsNone(async_wrapper._GLOBAL_LOOP_THREAD)


if __name__ == "__main__":
    unittest.main()
