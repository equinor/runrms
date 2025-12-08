"""Tests for the ApiExecutor."""

import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from runrms.api import RmsApiProxy
from runrms.config import ApiConfig
from runrms.executor import ApiExecutor


@pytest.fixture
def mock_config() -> ApiConfig:
    """Create a mock API RMS config."""
    config = ApiConfig(version="14.2.2")
    config.site_config.batch_lm_license_file = None
    return config


@pytest.fixture
def mock_exec_env() -> dict[str, str]:
    """Mock exec environment."""
    return {
        "TCL_LIBRARY": "/opt/rms/lib/tcl8.6",
        "PATH": "/usr/bin",
    }


def test_generate_zmq_address(mock_config: ApiConfig) -> None:
    """Generated ZMQ address is unique and follows expected format."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)
        address = executor.zmq_address

        assert address.startswith("ipc://")
        assert "rmsapi_" in address
        assert address.endswith(".sock")


def test_custom_zmq_address_is_used(mock_config: ApiConfig) -> None:
    """Custom zmq address is used when provided."""
    custom_address = "ipc:///tmp/custom.sock"
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config, zmq_address=custom_address)

    assert executor.zmq_address == custom_address


def test_setup_rms_environment(mock_config: ApiConfig) -> None:
    """Correct environment is established for RMS."""
    # Ensures the env isn't added at initialization
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

    orig_exec_env = deepcopy(executor._exec_env)
    executor._setup_rms_environment()
    new_exec_env = deepcopy(executor._exec_env)

    assert orig_exec_env != new_exec_env
    assert set(orig_exec_env.items()) ^ set(new_exec_env.items()) == {
        ("LD_LIBRARY_PATH", "/opt/rms/14.2.2/lib64:/opt/rms/14.2.2/lib"),
        ("PATH", "/opt/rms/14.2.2/bin"),
        ("ROXAR_RMS_ROOT", "/opt/rms/14.2.2"),
    }


def test_setup_rms_environment_with_license(mock_config: ApiConfig) -> None:
    """Correct environment with license file is established for RMS."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        mock_config.site_config.batch_lm_license_file = "foo.lic"
        executor_with_license = ApiExecutor(mock_config)

    assert "LM_LICENSE_FILE" not in executor_with_license._exec_env
    executor_with_license._setup_rms_environment()
    assert executor_with_license._exec_env["LM_LICENSE_FILE"] == "foo.lic"


def test_exec_mode_is_api(mock_config: ApiConfig) -> None:
    """Executor reports correct execution mode."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

    assert executor.exec_mode.value == "api"


def test_is_running_false_when_no_worker(mock_config: ApiConfig) -> None:
    """is_running is False when no worker process exists."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

    assert executor.is_running is False


def test_is_running_false_when_worker_terminated(mock_config: ApiConfig) -> None:
    """is_running is False when worker has terminated."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)
        executor._worker_process = MagicMock(spec=subprocess.Popen)
        executor._worker_process.poll.return_value = 0

    assert executor.is_running is False


def test_is_running_true_when_worker_active(mock_config: ApiConfig) -> None:
    """is_running is True when worker is active."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)
        executor._worker_process = MagicMock(spec=subprocess.Popen)
        executor._worker_process.poll.return_value = None

    assert executor.is_running is True


def test_build_command(mock_config: ApiConfig, mock_exec_env: dict[str, str]) -> None:
    """Command is built correctly from config and env."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)
        executor._exec_env = mock_exec_env

        cmd = executor._build_command()

        assert cmd[0] == "env"
        assert f"TCL_LIBRARY={mock_exec_env['TCL_LIBRARY']}" in cmd
        assert f"PATH={mock_exec_env['PATH']}" in cmd
        assert cmd[-3] == mock_config.wrapper
        assert cmd[-2] == mock_config.executable
        assert cmd[-1] == executor.zmq_address


def test_wait_for_starter_startsup_raises_if_no_worker(mock_config: ApiConfig) -> None:
    """Exception raised if no worker to wait for."""
    executor = ApiExecutor(mock_config)
    with pytest.raises(
        RuntimeError, match="No worker process set, cannot wait for one"
    ):
        executor._wait_for_worker_startup()


def test_start_worker_does_nothing_if_worker_not_none(mock_config: ApiConfig) -> None:
    """Start worker is a no-op if the worker process is not none."""
    executor = ApiExecutor(mock_config)
    with patch("runrms.executor.api_executor.subprocess.Popen") as mock_popen:
        executor._worker_process = MagicMock()
        executor._start_worker()
        mock_popen.assert_not_called()


def test_start_worker_starts_worker_process(mock_config: ApiConfig) -> None:
    """Start worker creates a worker process and starts it up."""
    executor = ApiExecutor(mock_config)
    with patch("runrms.executor.api_executor.subprocess.Popen") as mock_popen:
        mock_worker_process = MagicMock()
        mock_worker_process.poll.return_value = None
        mock_popen.return_value = mock_worker_process

        executor._start_worker()

        mock_popen.assert_called_once_with(
            executor._build_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        # Should be called 15+ times
        mock_worker_process.poll.assert_called()
        mock_worker_process.communicate.assert_not_called()


def test_start_worker_fails_to_start_worker_process(mock_config: ApiConfig) -> None:
    """Some things are called when a worker process fails to start."""
    executor = ApiExecutor(mock_config)
    with (
        patch("runrms.executor.api_executor.subprocess.Popen") as mock_popen,
        pytest.raises(RuntimeError, match="stdout: foo\nstderr: bar"),
    ):
        mock_worker_process = MagicMock()
        mock_worker_process.poll.return_value = [None, None, 1]
        mock_worker_process.communicate.return_value = (b"foo", b"bar")
        mock_popen.return_value = mock_worker_process

        executor._start_worker()

        mock_popen.assert_called_once_with(
            executor._build_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        # Should be called twice (for each None), then fail
        mock_worker_process.poll.assert_called()
        mock_worker_process.communicate.assert_called()


def test_run_starts_worker_once(mock_config: ApiConfig) -> None:
    """run() starts the worker process only once."""
    with (
        patch.object(ApiExecutor, "_setup_rms_environment"),
        patch.object(ApiExecutor, "_start_worker") as mock_start,
        patch.object(ApiExecutor, "_create_proxy") as mock_create_proxy,
    ):
        mock_proxy = MagicMock(spec=RmsApiProxy)
        mock_create_proxy.return_value = mock_proxy

        executor = ApiExecutor(mock_config)
        executor._worker_process = MagicMock(spec=subprocess.Popen)

        proxy1 = executor.run()
        executor._worker_process.poll.return_value = None
        proxy2 = executor.run()

        assert mock_start.call_count == 1
        assert proxy1 is proxy2


def test_run_creates_proxy_once(mock_config: ApiConfig) -> None:
    """run() starts the worker process only once."""
    with (
        patch.object(ApiExecutor, "_setup_rms_environment"),
        patch.object(ApiExecutor, "_start_worker"),
        patch.object(ApiExecutor, "_create_proxy") as mock_create_proxy,
    ):
        mock_proxy = MagicMock(spec=RmsApiProxy)
        mock_create_proxy.return_value = mock_proxy

        executor = ApiExecutor(mock_config)
        executor._worker_process = MagicMock(spec=subprocess.Popen)
        executor._worker_process.poll.return_value = None

        executor.run()
        executor.run()

    assert mock_create_proxy.call_count == 1


def test_shutdown_sends_shutdown_to_proxy(mock_config: ApiConfig) -> None:
    """shutdown() sends shutdown request to proxy."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

        mock_proxy = MagicMock(spec=RmsApiProxy)
        executor._proxy_instance = mock_proxy

        executor.shutdown()

        mock_proxy._shutdown.assert_called_once()
        mock_proxy._cleanup.assert_called_once()


def test_shutdown_cleans_up_on_proxy_error(mock_config: ApiConfig) -> None:
    """shutdown() cleans up proxy if shutdown request fails."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

        mock_proxy = MagicMock(spec=RmsApiProxy)
        mock_proxy._shutdown.side_effect = Exception("Connection failed")
        executor._proxy_instance = mock_proxy

        executor.shutdown()  # Shouldn't raise

        mock_proxy._cleanup.assert_called_once()


def test_shutdown_terminates_worker(mock_config: ApiConfig) -> None:
    """shutdown() terminates the worker process."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.wait.return_value = 0
        executor._worker_process = mock_process

        executor.shutdown()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()


def test_shutdown_kills_worker_on_timeout(mock_config: ApiConfig) -> None:
    """shutdown() kills worker if termination times out."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config)

        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="", timeout=2),
            0,
        ]
        executor._worker_process = mock_process

        executor.shutdown()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


def def_shutdown_cleans_up_socket_file(mock_config: ApiConfig, tmp_path: Path) -> None:
    """shutdown() removes the socket file."""
    socket_path = tmp_path / "test.sock"
    socket_path.touch()

    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config, zmq_address=f"ipc://{socket_path}")

        executor.shutdown()

        assert not socket_path.exists()


def test_shutdown_handles_missing_socket_file(mock_config: ApiConfig) -> None:
    """shutdown() handles missing socket file gracefully."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config, zmq_address="ipc:///tmp/nonexistent.sock")

        executor.shutdown()  # should not raise


def test_zmq_address_raises_after_shutdown(mock_config: ApiConfig) -> None:
    """Accessing zmq_address after shutdown raises error."""
    with patch.object(ApiExecutor, "_setup_rms_environment"):
        executor = ApiExecutor(mock_config, zmq_address="ipc:///tmp/nonexistent.sock")
        executor.shutdown()

        with pytest.raises(RuntimeError, match="ZMQ address not available"):
            _ = executor.zmq_address


def test_create_proxy_retries_ping(mock_config: ApiConfig) -> None:
    """_create_proxy retries ping on failure."""
    with (
        patch.object(ApiExecutor, "_setup_rms_environment"),
        patch("runrms.executor.api_executor.RmsApiProxy") as mock_proxy_class,
    ):
        mock_proxy = MagicMock(spec=RmsApiProxy)
        # Fail twice
        mock_proxy._ping.side_effect = [False, False, True]
        mock_proxy_class.return_value = mock_proxy

        executor = ApiExecutor(mock_config, ping_retries=3, ping_delay=0.01)

        proxy = executor._create_proxy()

        assert proxy is mock_proxy
        assert mock_proxy._ping.call_count == 3


def test_create_proxy_shuts_down_on_timeout(mock_config: ApiConfig) -> None:
    """_create_proxy shuts down executor if ping fails."""
    with (
        patch.object(ApiExecutor, "_setup_rms_environment"),
        patch("runrms.executor.api_executor.RmsApiProxy") as mock_proxy_class,
        patch.object(ApiExecutor, "shutdown") as mock_shutdown,
    ):
        mock_proxy = MagicMock(spec=RmsApiProxy)
        mock_proxy._ping.return_value = False
        mock_proxy_class.return_value = mock_proxy

        executor = ApiExecutor(mock_config, ping_retries=2, ping_delay=0.01)

        with pytest.raises(
            RuntimeError, match="failed to respond after 2 ping attempts"
        ):
            executor._create_proxy()

        mock_shutdown.assert_called_once()
