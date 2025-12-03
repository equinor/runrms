"""Tests for the api worker."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import zmq

from runrms.api import RemoteException, RmsApiProxy
from runrms.api.worker import Request, Response


def mock_response(success: bool = True, value: Any = None, **kwargs: Any) -> bytes:
    """Helper to serialize a response."""
    response = Response(success=success, value=value, **kwargs)
    return response.serialize()


def test_root_proxy_creates_socket(
    mock_context: MagicMock, mock_socket: MagicMock, zmq_address: str
) -> None:
    """Root proxy sets up a ZMQ connection."""
    with patch("runrms.api.proxy.zmq.Context", return_value=mock_context):
        RmsApiProxy(zmq_address)

    mock_context.socket.assert_called_once_with(zmq.REQ)
    mock_socket.connect.assert_called_once_with(zmq_address)
    mock_socket.setsockopt.assert_any_call(zmq.RCVTIMEO, 30000)
    mock_socket.setsockopt.assert_any_call(zmq.SNDTIMEO, 5000)


def test_child_proxy_reuses_socket(
    proxy_with_mocks: RmsApiProxy, mock_context: MagicMock
) -> None:
    """Child proxies don't create a new connection."""
    child = proxy_with_mocks._create_child_proxy(["child"])

    assert mock_context.socket.call_count == 1
    assert child._is_root is False


def test_custom_timeouts(mock_context: MagicMock, zmq_address: str) -> None:
    """Can set custom timeout values."""
    with patch("runrms.api.proxy.zmq.Context", return_value=mock_context):
        RmsApiProxy(zmq_address, rcv_timeout_ms=10000, snd_timeout_ms=2000)

    socket = mock_context.socket.return_value
    socket.setsockopt.assert_any_call(zmq.RCVTIMEO, 10000)
    socket.setsockopt.assert_any_call(zmq.SNDTIMEO, 2000)


def test_getattr_returns_child_proxy(proxy_with_mocks: RmsApiProxy) -> None:
    """Accessing attribute returns new proxy with extended path."""
    child = proxy_with_mocks.some_attr

    assert isinstance(child, RmsApiProxy)
    assert child._path == ["some_attr"]


def test_nested_getattr_extends_path(proxy_with_mocks: RmsApiProxy) -> None:
    """Chained attribute access extends path."""
    nested = proxy_with_mocks.level1.level2.level3

    assert nested._path == ["level1", "level2", "level3"]


def test_private_attr_raises(proxy_with_mocks: RmsApiProxy) -> None:
    """Acessing private attributes raises AttributeError.

    This is disallowed to keep it simpler until the need arises."""
    with pytest.raises(AttributeError, match="no attribute '_private'"):
        _ = proxy_with_mocks._private


def test_str_repr_on_root_proxy_gives_instance(proxy_with_mocks: RmsApiProxy) -> None:
    """Str and repr print the root RmsApiProxy instance with its address."""
    assert str(proxy_with_mocks).startswith("<RmsApiProxy connected to ipc://")
    assert repr(proxy_with_mocks).startswith("<RmsApiProxy connected to ipc://")


def test_version_special_case(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """___version__ is fetched if asked for."""
    mock_socket.recv.return_value = mock_response(value="1.2.3")

    version = proxy_with_mocks.__version__

    assert version == "1.2.3"
    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.path == ["__version__"]


def test_call_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Calling a method sends a proper request."""
    mock_socket.recv.return_value = mock_response(value=42)

    result = proxy_with_mocks.some_method(1, 2, key="value")

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["some_method"]
    assert request.args == (1, 2)
    assert request.kwargs == {"key": "value"}
    assert result == 42


def test_getitem_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using subscript get operation sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value="a")

    result = ref[0]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__getitem__"]
    assert request.args == (0,)
    assert request.kwargs == {}
    assert result == "a"


def test_setitem_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using subscript set operation sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=None)

    ref[0] = "b"

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__setitem__"]
    assert request.args == (0, "b")
    assert request.kwargs == {}


def test_delitem_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using subscript del operation sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=None)

    del ref[0]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__delitem__"]
    assert request.args == (0,)
    assert request.kwargs == {}


def test_contains_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using subscript del operation sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = "a" in ref

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__contains__"]
    assert request.args == ("a",)
    assert request.kwargs == {}
    assert result is True


@pytest.mark.parametrize(
    "fn, path, resp",
    [
        (str, "__str__", "['a', 'b', 'c']"),
        (repr, "__repr__", "MockUnpickleable(['a', 'b', 'c'])"),
        (len, "__len__", 3),
        (bool, "__bool__", True),
        (hash, "__hash__", 3),
        (int, "__int__", 0),
        (float, "__float__", 0.0),
    ],
)
def test_callable_dunders_send_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
    fn: Callable[[Any], Any],
    path: str,
    resp: Any,
) -> None:
    """Using a dunder method sends a proper request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=resp)

    fn(ref)

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", path]
    assert request.args == ()
    assert request.kwargs == {}


def test_eq_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using == operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = ref == ["a", "b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__eq__"]
    assert request.args == (["a", "b", "c"],)
    assert request.kwargs == {}
    assert result is True


def test_ne_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using != operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = ref != ["b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__ne__"]
    assert request.args == (["b", "c"],)
    assert request.kwargs == {}
    assert result is True


def test_lt_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using < operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=False)

    result = ref < ["b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__lt__"]
    assert request.args == (["b", "c"],)
    assert request.kwargs == {}
    assert result is False


def test_le_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using <= operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = ref <= ["a", "b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__le__"]
    assert request.args == (["a", "b", "c"],)
    assert request.kwargs == {}
    assert result is True


def test_gt_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using > operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = ref > ["b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__gt__"]
    assert request.args == (["b", "c"],)
    assert request.kwargs == {}
    assert result is True


def test_ge_sends_correct_request(
    proxy_with_mocks: RmsApiProxy,
    mock_socket: MagicMock,
) -> None:
    """Using >= operator sends the correct request."""
    ref = proxy_with_mocks.nested_unpickleable
    mock_socket.recv.return_value = mock_response(value=True)

    result = ref >= ["a", "b", "c"]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "call"
    assert request.path == ["nested_unpickleable", "__ge__"]
    assert request.args == (["a", "b", "c"],)
    assert request.kwargs == {}
    assert result is True


def test_call_on_root_raises(proxy_with_mocks: RmsApiProxy) -> None:
    """Calling root proxy raisees a TypeError.

    This is like 'rmsapi()'."""
    with pytest.raises(TypeError, match="Root proxy is not callable"):
        proxy_with_mocks()


def test_call_returns_proxy_for_reference(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Call returnings an object reference creates a proxy."""
    mock_socket.recv.return_value = mock_response(value={"obj_id": "123"})

    result = proxy_with_mocks.get_object()

    assert isinstance(result, RmsApiProxy)
    assert result._path == ["$ref", "123"]


def test_nested_call(proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock) -> None:
    """Can call methods on nested attributes."""
    mock_socket.recv.return_value = mock_response(value=100)

    proxy_with_mocks.nested.obj.method(5)

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.path == ["nested", "obj", "method"]
    assert request.args == (5,)


def test_setattr_sends_request(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Setting an attribute sends a setattr request."""
    mock_socket.recv.return_value = mock_response()

    proxy_with_mocks.some_attr = 42

    request = Request.deserialize(mock_socket.sent_data)
    assert request.msg_type == "setattr"
    assert request.path == ["some_attr"]
    assert request.value == 42


def test_setattr_nested(proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock) -> None:
    """Can set nested attributes."""
    mock_socket.recv.return_value = mock_response()

    proxy_with_mocks.nested.value = [1, 2, 3]

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.path == ["nested", "value"]
    assert request.value == [1, 2, 3]


def test_setattr_private_uses_obj_setattr(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Settings a private attributes uses object.__setattr__."""
    proxy_with_mocks._internal_value = 99

    assert proxy_with_mocks._internal_value == 99


def test_iter_returns_proxy(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Calling __iter__ returns an iterator proxy."""
    mock_socket.recv.return_value = mock_response(value={"obj_id": "iter_1"})

    iterator = iter(proxy_with_mocks)

    assert isinstance(iterator, RmsApiProxy)
    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.path == ["__iter__"]


def test_next_calls_worker(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Calling __iter__ returns an iterator proxy."""
    mock_socket.recv.return_value = mock_response(value=42)

    result = next(proxy_with_mocks.some_iterator)

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.path == ["some_iterator", "__next__"]
    assert result == 42


def test_next_raises_stop_iteration(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """StopIteration is raised when iterator exhausted."""
    mock_socket.recv.return_value = mock_response(
        success=False,
        error_type="StopIteration",
    )

    with pytest.raises(StopIteration):
        next(proxy_with_mocks.some_iterator)


def test_remote_exception_raised(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Remote errors raise RemoteException."""
    mock_socket.recv.return_value = mock_response(
        success=False, error="Big fail", error_type="ValueError", traceback="GOTO 10"
    )

    with pytest.raises(RemoteException, match="Big fail") as e:
        proxy_with_mocks.failing_methods()

    assert e.value.remote_type == "ValueError"
    assert e.value.remote_traceback == "GOTO 10"


def test_zmq_timeout_raises(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """ZMQ timeout raisers TimeoutError."""
    mock_socket.recv.side_effect = [zmq.Again(), zmq.Again()]  # type: ignore[no-untyped-call]

    with pytest.raises(TimeoutError, match="Request timed out"):
        proxy_with_mocks.slow_method()


def test_zmq_error_raises(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """ZMQ timeout raisers ConnectionError."""
    mock_socket.recv.side_effect = zmq.ZMQError(msg="Connection lost")

    with pytest.raises(ConnectionError, match="ZMQ error: Connection lost"):
        proxy_with_mocks.slow_method()


def test_ping_success(proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock) -> None:
    """Ping returns False on error."""
    mock_socket.recv.side_effect = zmq.Again

    assert proxy_with_mocks._ping() is False


def test_ping_only_on_root(proxy_with_mocks: RmsApiProxy) -> None:
    """Ping can only ne called on a root proxy."""
    child = proxy_with_mocks.child

    with pytest.raises(RuntimeError, match="only be called on root"):
        child._ping()


def test_shutdown_sends_request(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Shutdown sends shutdown request."""
    mock_socket.recv.return_value = mock_response(value="shutting down")

    proxy_with_mocks._shutdown()

    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "shutdown"


def test_shutdown_on_child_proxy_raises(proxy_with_mocks: RmsApiProxy) -> None:
    """Accessing attribute returns new proxy with extended path."""
    child = proxy_with_mocks.some_attr
    with pytest.raises(RuntimeError, match="Shutdown can only be called on root"):
        child._shutdown()


def test_cleanup_closes_socket(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """Cleanup closes socket on root proxy."""
    proxy_with_mocks._cleanup()

    mock_socket.close.assert_called_once()


def test_cleanup_noop_on_child(proxy_with_mocks: RmsApiProxy) -> None:
    """Cleanup does nothing on child proxy."""
    child = proxy_with_mocks.child
    child._cleanup()  # doesn't raise


def test_get_fetches_value(
    proxy_with_mocks: RmsApiProxy, mock_socket: MagicMock
) -> None:
    """get() fetches the actual value from the worker."""
    mock_socket.recv.return_value = mock_response(value=42)

    value = proxy_with_mocks.some_attr.get()

    assert value == 42
    sent_data = mock_socket.send.call_args[0][0]
    request = Request.deserialize(sent_data)
    assert request.msg_type == "getattr"
    assert request.path == ["some_attr"]


def test_get_on_root_raises(proxy_with_mocks: RmsApiProxy) -> None:
    """get() on root proxy raises."""
    with pytest.raises(RuntimeError, match="Cannot get value of root proxy"):
        proxy_with_mocks.get()


def test_no_get_on_dict_key_raises(proxy_with_mocks: RmsApiProxy) -> None:
    """Helpful serialization error is raised when using an RmsApiProxy as an arg."""
    some = {}

    with pytest.raises(TypeError, match="Unable to serialize request to rmsapi"):
        some[proxy_with_mocks.some_attr] = "foo"
