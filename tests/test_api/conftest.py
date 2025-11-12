"""Fixtures and mocks for the api proxy."""

import subprocess
import sys
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from subprocess import Popen
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import zmq

from runrms.api import RmsApiProxy
from runrms.api.worker import ApiWorker, Request


class MockNested:
    """Nested mocked object."""

    def multiply(self, x: int, y: int) -> int:
        return x * y


class MockUnpickleable:
    """Object that cannot be pickled."""

    items = ["a", "b", "c"]

    def __reduce__(self) -> Any:
        raise TypeError("Cannot pickle MockUnpickleable")

    def get_value(self) -> int:
        return 99

    def sub(self, a: int, b: int) -> int:
        return a - b

    def __iter__(self) -> Iterator[str]:
        return iter(self.items)

    def __getitem__(self, key: int) -> str:
        return self.items[key]

    def __setitem__(self, key: int, value: str) -> None:
        self.items[key] = value

    def __delitem__(self, key: int) -> None:
        del self.items[key]

    def __contains__(self, item: str) -> bool:
        return item in self.items

    def __str__(self) -> str:
        return str(self.items)

    def __repr__(self) -> str:
        return f"MockUnpickleable({self.items})"

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __int__(self) -> int:
        return int(self.items)  # type: ignore[call-overload]

    def __float__(self) -> float:
        return float(self.items)  # type: ignore[arg-type]

    def __eq__(self, other: Any) -> bool:
        return self.items == other

    def __ne__(self, other: Any) -> bool:
        return self.items != other

    def __lt__(self, other: Any) -> bool:
        return self.items < other

    def __le__(self, other: Any) -> bool:
        return self.items <= other

    def __gt__(self, other: Any) -> bool:
        return self.items > other

    def __ge__(self, other: Any) -> bool:
        return self.items >= other

    def __hash__(self) -> int:
        # Nonsense, but just for testing
        return len(self.items)


class MockApi:
    """MagicMock api for testing."""

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

    def slow_method(self) -> None:
        time.sleep(5)


@pytest.fixture
def zmq_address(tmp_path: Path) -> str:
    """Provide a unique address for tests."""
    uuid = uuid4().hex[:10]
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

    context = zmq.Context()
    health_socket = context.socket(zmq.REQ)
    health_socket.setsockopt(zmq.RCVTIMEO, 2000)
    health_socket.setsockopt(zmq.SNDTIMEO, 2000)

    try:
        health_socket.connect(zmq_address)
        ping_req = Request(msg_type="ping", path=[])
        health_socket.send(ping_req.serialize())
        health_socket.recv()
    except zmq.Again:
        process.kill()
        stdout, stderr = process.communicate()
        pytest.fail(f"Worker not responding: \n{stderr.decode()}")
    finally:
        health_socket.close()
        context.term()

    yield process

    try:
        process.terminate()
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        if process.poll() is None:
            process.kill()


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


@pytest.fixture
def mock_socket() -> MagicMock:
    """Mock a ZMQ socket."""
    socket = MagicMock(spec=zmq.Socket)
    socket.sent_data = None

    def capture_send(data: bytes) -> None:
        socket.sent_data = data

    socket.recv = MagicMock()
    socket.send.side_effect = capture_send
    return socket


@pytest.fixture
def mock_context(mock_socket: MagicMock) -> MagicMock:
    """Mock ZMQ context that returns our socket."""
    context = MagicMock(spec=zmq.Context)
    context.socket = MagicMock(return_value=mock_socket)
    return context


@pytest.fixture
def proxy_with_mocks(
    mock_context: MagicMock, mock_socket: MagicMock, zmq_address: str
) -> RmsApiProxy:
    """Create a proxy with a mocked ZMQ context."""
    with patch("runrms.api.proxy.zmq.Context", return_value=mock_context):
        return RmsApiProxy(zmq_address)
