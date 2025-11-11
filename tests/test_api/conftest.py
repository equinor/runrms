"""Fixtures and mocks for the api proxy."""

import subprocess
import sys
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from subprocess import Popen
from typing import Any
from uuid import uuid4

import pytest
import zmq

from runrms.api.worker import ApiWorker


class MockNested:
    """Nested mocked object."""

    def multiply(self, x: int, y: int) -> int:
        return x * y


class MockUnpickleable:
    """Object that cannot be pickled."""

    def __reduce__(self) -> Any:
        raise TypeError("Cannot pickle MockUnpickleable")

    def get_value(self) -> int:
        return 99

    def sub(self, a: int, b: int) -> int:
        return a - b


class MockApi:
    """Mock api for testing."""

    def __init__(self) -> None:
        self.value = 42
        self.nested = MockNested()
        self.nested_unpickleable = MockUnpickleable()
        self.items = [1, 2, 3]

    def add(self, a: int, b: int) -> int:
        return a + b

    def get_object(self) -> MockUnpickleable:
        return MockUnpickleable()

    def get_list(self) -> list[int]:
        return [1, 2, 3]

    def raise_error(self) -> None:
        raise ValueError("Intentional error")

    def __iter__(self) -> Iterator[int]:
        return iter(self.items)


@pytest.fixture
def zmq_address(tmp_path: Path) -> str:
    """Provide a unique address for tests."""
    uuid = uuid4().hex[:8]
    socket_path = tmp_path / f"{uuid}.sock"
    return f"ipc://{socket_path}"


@pytest.fixture
def mock_worker() -> ApiWorker:
    """Returns a non-running worker instance."""
    api_worker = ApiWorker("ipc:///tmp/unused.sock")
    api_worker.api_object = MockApi()
    return api_worker


@pytest.fixture
def worker(zmq_address: str, tmp_path: Path) -> Generator[Popen[bytes], None, None]:
    """Creates and start a worker in a background thread."""
    test_script = tmp_path / "test_worker_runner.py"
    test_script.write_text(f"""
import sys
sys.path.insert(0, {repr(str(Path(__file__).parent.parent.parent))})

from {__name__} import MockApi
from runrms.api.worker import ApiWorker

if __name__ == "__main__":
    worker = ApiWorker("{zmq_address}")
    worker.run(MockApi())
""")

    process = subprocess.Popen(
        [sys.executable, str(test_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.25)

    if process.poll() is not None:
        stdout, stderr = process.communicate()
        pytest.fail(f"Worker process failed to start:\n{stderr.decode()}")

    yield process

    try:
        process.terminate()
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture
def client(zmq_address: str) -> Generator[zmq.Socket[bytes], None, None]:
    """Create a client socket."""
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(zmq_address)
    socket.setsockopt(zmq.RCVTIMEO, 5000)
    socket.setsockopt(zmq.SNDTIMEO, 5000)

    yield socket

    socket.close()
    context.term()
