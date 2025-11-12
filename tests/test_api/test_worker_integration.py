"""Tests for the api worker."""

import pickle
import time
from pathlib import Path
from subprocess import Popen
from uuid import uuid4

import pytest
import zmq

from runrms.api.worker import Request, Response

from .conftest import MockNested


@pytest.fixture
def zmq_address(tmp_path: Path) -> str:
    """Provide a unique address for tests."""
    uuid = uuid4().hex[:8]
    socket_path = tmp_path / f"{uuid}.sock"
    return f"ipc://{socket_path}"


def send_request(socket: zmq.Socket[bytes], request: Request) -> Response:
    """Helper to send request and receive response."""
    try:
        socket.send(request.serialize())
        response_data = socket.recv()
        return Response.deserialize(response_data)
    except zmq.Again as e:
        raise TimeoutError("No response received") from e
    except Exception as e:
        raise RuntimeError(f"Communcation error: {e}") from e


def test_ping(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Worker responds to ping."""
    request = Request(msg_type="ping", path=[])
    response = send_request(client, request)

    assert response.success
    assert response.value == "pong"


def test_getattr_simple(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Can get a simple attribute."""
    request = Request(msg_type="getattr", path=["value"])
    response = send_request(client, request)

    assert response.success
    assert response.value == 42


def test_getattr_nested(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Can get a nested attribtue."""
    request = Request(msg_type="getattr", path=["nested"])
    response = send_request(client, request)

    assert response.success
    # MockNested can be pickled so the object is returned
    assert isinstance(response.value, MockNested)


def test_setattr_simple_value(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Worker can set a simple attr."""
    request = Request(msg_type="setattr", path=["value"], value=43)
    response = send_request(client, request)

    assert response.success
    assert response.value is None

    request = Request(msg_type="getattr", path=["value"])
    response = send_request(client, request)

    assert response.success
    assert response.value == 43


def test_setattr_nested_obj(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Worker can set and retrieve nested obj."""
    request = Request(msg_type="setattr", path=["nested", "val"], value=["foo", "bar"])
    response = send_request(client, request)

    assert response.success

    request = Request(msg_type="getattr", path=["nested", "val"])
    response = send_request(client, request)

    assert response.success
    assert response.value == ["foo", "bar"]


def test_setattr_nested_unpickleable_obj(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Worker can set and retrieve from a nested unpickleable obj."""
    request = Request(
        msg_type="setattr",
        path=["nested_unpickleable", "val"],
        value={"foo": ["bar", "baz"]},
    )
    response = send_request(client, request)

    assert response.success

    request = Request(msg_type="getattr", path=["nested_unpickleable", "val"])
    response = send_request(client, request)

    assert response.success
    assert response.value == {"foo": ["bar", "baz"]}


def test_call_method(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Can call method with args."""
    request = Request(msg_type="call", path=["add"], args=(10, 20), kwargs={})
    response = send_request(client, request)

    assert response.success
    assert response.value == 30


def test_call_nested_unpickleable_method(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Can call a method on nested obj using a ref."""
    request1 = Request(msg_type="getattr", path=["nested_unpickleable"])
    response1 = send_request(client, request1)
    obj_id = response1.value["obj_id"]

    # Call on nested object
    request2 = Request(
        msg_type="call", path=["$ref", obj_id, "sub"], args=(4, 5), kwargs={}
    )
    response2 = send_request(client, request2)

    assert response2.success
    assert response2.value == -1


def test_unpickleable_returns_reference(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Unpickleable objs return a proxy ref."""
    request = Request(msg_type="call", path=["get_object"], args=(), kwargs={})
    response = send_request(client, request)

    assert response.success
    assert isinstance(response.value, dict)
    assert "obj_id" in response.value


def test_reference_method_call(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Call methods on ref'd objects."""
    # Unpickleable
    request1 = Request(msg_type="call", path=["get_object"])
    response1 = send_request(client, request1)
    obj_id = response1.value["obj_id"]

    request2 = Request(msg_type="call", path=["$ref", obj_id, "get_value"])
    response2 = send_request(client, request2)

    assert response2.success
    assert response2.value == 99


def test_invalid_reference(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Test invalid ref return an error."""
    request = Request(msg_type="call", path=["$ref", "nonexistent", "method"])
    response = send_request(client, request)

    assert not response.success
    assert response.error_type == "KeyError"
    assert response.error is not None
    assert "not found in store" in response.error


def test_reference_without_id(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Ref without id returns error."""
    request = Request(msg_type="getattr", path=["$ref"])
    response = send_request(client, request)

    assert not response.success
    assert response.error_type == "ValueError"
    assert response.error is not None
    assert "requires an object id" in response.error


def test_nonexistent_attribute(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Test accessing nonexitent attribute returns an error."""
    request = Request(msg_type="getattr", path=["nonexistent"])
    response = send_request(client, request)

    assert not response.success
    assert response.error_type == "AttributeError"
    assert response.traceback is not None


def test_call_without_path(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Calling without a path returns an error."""
    request = Request(msg_type="call", path=[])
    response = send_request(client, request)

    assert not response.success
    assert response.error_type == "ValueError"
    assert response.error is not None
    assert "empty access path" in response.error


def test_method_exception_propagates(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Exceptions from methods are returned back."""
    request = Request(msg_type="call", path=["add"], args=(object(), object()))
    response = send_request(client, request)
    print(response)

    assert not response.success
    assert response.error_type == "TypeError"
    assert response.traceback is not None


def test_unknown_message_type(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Unknown message types returns errors."""
    invalid_req = pickle.dumps(
        {"msg_type": "invalid", "path": [], "args": None, "kwargs": None, "value": None}
    )
    client.send(invalid_req)
    response_data = client.recv()
    response = Response.deserialize(response_data)

    assert not response.success
    assert response.error is not None
    assert "3 validation errors" in response.error


def test_iterator_returns_reference(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Calling __iter__ retrusn an iterator reference."""
    request = Request(msg_type="call", path=["__iter__"])
    response = send_request(client, request)

    assert response.success
    assert isinstance(response.value, dict)
    assert "obj_id" in response.value  # is a proxy ref


def test_pickleable_list_returns_directory(
    worker: Popen[bytes], client: zmq.Socket[bytes]
) -> None:
    """Pickleable list is returned directly."""
    request = Request(msg_type="call", path=["get_list"])
    response = send_request(client, request)

    assert response.success
    assert response.value == [1, 2, 3]
    assert not isinstance(response.value, dict)


def test_shutdown_stops_worker(worker: Popen[bytes], client: zmq.Socket[bytes]) -> None:
    """Shutdown successful stops the worker."""
    request = Request(msg_type="shutdown", path=[])
    response = send_request(client, request)

    assert response.success
    assert response.value == "shutting down"

    time.sleep(0.1)  # Let it stop, hopefully
    assert worker.poll() == 0
