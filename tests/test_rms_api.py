"""Test for main API entry point."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from runrms import _rms_api
from runrms._rms_api import ApiConfig, ApiExecutor
from runrms.api import RmsApiProxy


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset global state before and after each test."""
    _rms_api._executors.clear()
    _rms_api._last_executor = None
    yield
    _rms_api._executors.clear()
    _rms_api._last_executor = None


@pytest.fixture
def mock_executor() -> MagicMock:
    """Create a mock executor."""
    executor = MagicMock(spec=ApiExecutor)
    executor.run.return_value = MagicMock(spec=RmsApiProxy)
    executor.shutdown = MagicMock()
    return executor


def test_get_executor_creates_config(mock_executor: MagicMock) -> None:
    """get_executor creates config with provided parameters."""
    with (
        patch("runrms._rms_api.ApiConfig") as mock_config_class,
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_executor(version="14.2.2")
        mock_config_class.assert_called_once_with(
            version="14.2.2",
            project=None,
            config_path=None,
        )


def test_get_executor_creates_executor(mock_executor: MagicMock) -> None:
    """get_executor creates ApiExecutor with config and zmq_address."""
    mock_config = MagicMock(spec=ApiConfig)
    with (
        patch("runrms._rms_api.ApiConfig", return_value=mock_config),
        patch(
            "runrms._rms_api.ApiExecutor", return_value=mock_executor
        ) as mock_executor_class,
    ):
        _rms_api.get_executor(version="14.2.2", zmq_address="ipc:///tmp/test.sock")
        mock_executor_class.assert_called_once_with(
            mock_config, zmq_address="ipc:///tmp/test.sock"
        )


def test_get_executor_tracks_executor(mock_executor: MagicMock) -> None:
    """get_executor adds executor to global tracking."""
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        result = _rms_api.get_executor(version="14.2.2")

        assert result is mock_executor


def test_get_rmsapi_calls_executor_run(mock_executor: MagicMock) -> None:
    """get_rmsapi starts the executor and returns proxy."""
    mock_proxy = MagicMock(spec=RmsApiProxy)
    mock_executor.run.return_value = mock_proxy

    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        result = _rms_api.get_rmsapi(version="14.2.2")

        mock_executor.run.assert_called_once()
        assert result is mock_proxy


def test_get_rmsapi_tracks_executor(mock_executor: MagicMock) -> None:
    """get_rmsapi tracks the executor globally."""
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_rmsapi(version="14.2.2")

        assert mock_executor in _rms_api._executors
        assert _rms_api._last_executor is mock_executor


def test_shutdown_calls_executor_shutdown(mock_executor: MagicMock) -> None:
    """shutdown() calls shutdown on the last executor."""
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.shutdown()

        mock_executor.shutdown.assert_called_once()


def test_shutdown_clears_last_executor(mock_executor: MagicMock) -> None:
    """shutdown() clears the _last_executor reference."""
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.shutdown()

        assert _rms_api._last_executor is None


def test_shutdown_handles_no_executor() -> None:
    """shutdown() handles exceptions during shutdown."""
    _rms_api.shutdown()  # shouldn't raise


def test_shutdown_handles_exception(mock_executor: MagicMock) -> None:
    """shutdown() handles exceptions during shutdown."""
    mock_executor.shutdown.side_effect = Exception("Shutdown failed")
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.shutdown()

        assert _rms_api._last_executor is None


def test_shutdown_all_shuts_down_multiple_executors() -> None:
    """shutdown_all() shuts down all tracked executors."""
    mock_executor1 = MagicMock(spec=ApiExecutor)
    mock_executor2 = MagicMock(spec=ApiExecutor)

    with (
        patch("runrms._rms_api.ApiConfig"),
        patch(
            "runrms._rms_api.ApiExecutor", side_effect=[mock_executor1, mock_executor2]
        ),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.get_executor(version="15.1.0.0")

        _rms_api.shutdown_all()

        mock_executor1.shutdown.assert_called_once()
        mock_executor2.shutdown.assert_called_once()


def test_shutdown_all_clears_trackings() -> None:
    """shutdown_all() clears all global tracking."""
    mock_executor = MagicMock(spec=ApiExecutor)
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch("runrms._rms_api.ApiExecutor", return_value=mock_executor),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.shutdown_all()

        assert len(_rms_api._executors) == 0
        assert _rms_api._last_executor is None


def test_shutdown_all_handles_empty_executors() -> None:
    """shutdown_all() handles case when no executors exist."""
    _rms_api.shutdown_all()


def test_shutdown_all_continues_on_exception() -> None:
    """shutdown_all() continues shutting down even if one fails."""
    mock_executor1 = MagicMock(spec=ApiExecutor)
    mock_executor1.shutdown.side_effect = Exception("Failed")
    mock_executor2 = MagicMock(spec=ApiExecutor)
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch(
            "runrms._rms_api.ApiExecutor", side_effect=[mock_executor1, mock_executor2]
        ),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.get_executor(version="15.1.0.0")

        _rms_api.shutdown_all()  # no exception raised

        mock_executor1.shutdown.assert_called_once()
        mock_executor2.shutdown.assert_called_once()


def test_multiple_get_executor_updates_last_executor() -> None:
    """Creating multiple executors updates _last_executor."""
    mock_executor1 = MagicMock(spec=ApiExecutor)
    mock_executor1.shutdown.side_effect = Exception("Failed")
    mock_executor2 = MagicMock(spec=ApiExecutor)
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch(
            "runrms._rms_api.ApiExecutor", side_effect=[mock_executor1, mock_executor2]
        ),
    ):
        _rms_api.get_executor(version="14.2.2")
        assert _rms_api._last_executor is mock_executor1

        _rms_api.get_executor(version="15.1.0.0")
        assert _rms_api._last_executor is mock_executor2


def test_shutdown_only_affects_last_executor() -> None:
    """shutdown() only shuts down the last executor, not all."""
    mock_executor1 = MagicMock(spec=ApiExecutor)
    mock_executor1.shutdown.side_effect = Exception("Failed")
    mock_executor2 = MagicMock(spec=ApiExecutor)
    with (
        patch("runrms._rms_api.ApiConfig"),
        patch(
            "runrms._rms_api.ApiExecutor", side_effect=[mock_executor1, mock_executor2]
        ),
    ):
        _rms_api.get_executor(version="14.2.2")
        _rms_api.get_executor(version="15.1.0.0")

        _rms_api.shutdown()

        mock_executor1.shutdown.assert_not_called()
        mock_executor2.shutdown.assert_called_once()
