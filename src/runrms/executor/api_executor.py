"""Executor class for RMS API mode."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from subprocess import Popen
from uuid import uuid4

from runrms._logging import null_logger
from runrms.api import RmsApiProxy
from runrms.config import ApiConfig

from ._rms_executor import RmsExecutionMode, RmsExecutor

logger = null_logger(__name__)


class ApiExecutor(RmsExecutor[ApiConfig]):
    """Executor for RMS API mode."""

    def __init__(
        self,
        config: ApiConfig,
        zmq_address: str | None = None,
        startup_timeout: float = 2.0,
        ping_retries: int = 10,
        ping_delay: float = 0.5,
    ) -> None:
        """Initialize the API executor."""
        super().__init__(config)

        self._zmq_address: str | None = zmq_address or self._generate_zmq_address()
        self._worker_process: Popen[bytes] | None = None
        self._proxy_instance: RmsApiProxy | None = None

        self._startup_timeout = startup_timeout
        self._ping_retries = ping_retries
        self._ping_delay = ping_delay

        self._setup_rms_environment()

    def _generate_zmq_address(self) -> str:
        """Generate a unique IPC address."""
        temp_dir = Path(tempfile.gettempdir())
        rand = uuid4().hex[:8]
        socket_path = temp_dir / f"rmsapi_{os.getpid()}_{rand}.sock"
        address = f"ipc://{socket_path}"
        logger.debug(f"Generated ZMQ address {address}")
        return address

    def _setup_rms_environment(self) -> None:
        """Configure RMS environment variables.

        This is done differently from the other executors. It doesn't use 'PYTHONPATH',
        which is ideal! It also does some special set-up to be able to import 'rmsapi'
        from the environment its in. In this regard the ordering of environment
        variables matters.
        """
        rms_root = str(Path(self._exec_env["TCL_LIBRARY"]).parent.parent.resolve())
        logger.debug(f"RMS root directory: {rms_root}")
        self.update_exec_env("PATH", f"{rms_root}/bin")
        self.update_exec_env("ROXAR_RMS_ROOT", rms_root)
        self.update_exec_env("LD_LIBRARY_PATH", f"{rms_root}/lib")
        self.update_exec_env("LD_LIBRARY_PATH", f"{rms_root}/lib64")

        if license_file := self.config.site_config.batch_lm_license_file:
            self.update_exec_env("LM_LICENSE_FILE", license_file)
            logger.debug(f"Using license file: {license_file}")

    @property
    def zmq_address(self) -> str:
        if not self._zmq_address:
            raise RuntimeError(
                "ZMQ address not available. The executor may have been shutdown. "
                "Create a new executor instance instead of reusing a shutdown one."
            )
        return self._zmq_address

    @property
    def exec_mode(self) -> RmsExecutionMode:
        return RmsExecutionMode.api

    @property
    def is_running(self) -> bool:
        """Check if worker process is running."""
        if self._worker_process is None:
            return False
        return self._worker_process.poll() is None

    def _build_command(self) -> list[str]:
        """Build the command to start the worker process."""
        env_vars = [f"{k}={v}" for k, v in self._exec_env.items()]
        return [
            "env",
            *env_vars,
            self.config.wrapper,
            self.config.executable,
            self.zmq_address,
        ]

    def _start_worker(self) -> None:
        """Start the worker process."""
        if self._worker_process is not None:
            logger.debug("Worker already started, skipping")
            return

        cmd = self._build_command()
        logger.info(f"Starting worker process: {' '.join(cmd)}")

        self._worker_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )

        logger.debug(f"Worker process started with pid {self._worker_process.pid}")

        if not self._wait_for_worker_startup():
            stdout, stderr = self._worker_process.communicate()
            raise RuntimeError(
                "Worker process failed to start:\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )

    def _wait_for_worker_startup(self) -> bool:
        """Wait for worker process to start up.

        Returns:
            True if it did, False otherwise
        """
        if not self._worker_process:
            raise RuntimeError("No worker process set, cannot wait for one")

        start_time = time.time()
        poll_interval = 0.1

        while time.time() - start_time < self._startup_timeout:
            if self._worker_process.poll() is not None:
                logger.error("Worker process terminated during startup")
                return False
            time.sleep(poll_interval)

        logger.info("Worker startup wait completed")
        return True

    def _create_proxy(self) -> RmsApiProxy:
        """Creates and initializes the API proxy."""
        logger.debug(f"Creating proxy for address {self.zmq_address}")
        proxy = RmsApiProxy(self.zmq_address)

        logger.debug(f"Pinging worker (max {self._ping_retries} retries)")
        for attempt in range(1, self._ping_retries + 1):
            if proxy._ping():
                logger.info(f"Worker responded to ping on attempt {attempt}")
                return proxy

            logger.debug(
                f"Ping attempt {attempt}/{self._ping_retries} failed, retrying"
            )
            time.sleep(self._ping_delay)

        logger.error(f"Worker failed to respond after {self._ping_retries} attempts")
        self.shutdown()
        raise RuntimeError(
            f"Worker process failed to respond after {self._ping_retries} ping attempts"
        )

    def run(self) -> RmsApiProxy:  # type: ignore[override]
        """Start the worker and return the API proxy."""
        if not self.is_running:
            self._start_worker()

        if self._proxy_instance is None:
            self._proxy_instance = self._create_proxy()

        return self._proxy_instance

    def shutdown(self) -> None:
        """Shutdown worker process and clean up resources."""
        logger.info("Shutting down API executor")

        if self._proxy_instance is not None:
            try:
                logger.debug("Sending shutdown request to worker")
                self._proxy_instance._shutdown()
            except Exception as e:
                logger.warning(f"Failed to send shutdown to worker: {e}")
            finally:
                self._proxy_instance._cleanup()
                self._proxy_instance = None

        if self._worker_process is not None:
            self._terminate_worker()

        self._cleanup_socket()
        logger.info("Shutdown complete")

    def _terminate_worker(self) -> None:
        """Terminate the worker process gracefully, then forcefully."""
        if self._worker_process is None:
            return

        logger.debug(f"Terminating worker process (pid {self._worker_process.pid})")

        self._worker_process.terminate()
        try:
            returncode = self._worker_process.wait(timeout=2)
            logger.debug(f"Worker terminated gracefully with code {returncode}")
        except subprocess.TimeoutExpired:
            logger.warning("Worker did not terminate, killing process")
            self._worker_process.kill()
            returncode = self._worker_process.wait()
            logger.debug(f"Worker killed with code {returncode}")
        finally:
            self._worker_process = None

    def _cleanup_socket(self) -> None:
        """Clean up socket file if it exists."""
        if not self._zmq_address or not self._zmq_address.startswith("ipc://"):
            return

        socket_path = Path(self.zmq_address[6:])
        if socket_path.exists():
            try:
                socket_path.unlink()
                logger.debug(f"Removed socket file {socket_path}")
            except OSError as e:
                logger.warning(f"Failed to remove socket file {socket_path}: {e}")

        self._zmq_address = None
