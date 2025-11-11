"""Tests for the api worker."""

from runrms.api.worker import ApiWorker, ProxyRef, Request, Response

from .conftest import MockNested, MockUnpickleable


def test_ping(mock_worker: ApiWorker) -> None:
    """Worker generates pong to ping."""
    request = Request(msg_type="ping", path=[])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == "pong"


def test_shutdown(mock_worker: ApiWorker) -> None:
    """Shutdown sets running flag to false."""
    assert mock_worker.running

    request = Request(msg_type="shutdown", path=[])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == "shutting down"
    assert not mock_worker.running


def test_getattr_simple_value(mock_worker: ApiWorker) -> None:
    """Worker can retrieve simple pickleable attr."""
    request = Request(msg_type="getattr", path=["value"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == 42


def test_getattr_nested_obj(mock_worker: ApiWorker) -> None:
    """Worker can retrieve nested obj."""
    request = Request(msg_type="getattr", path=["nested"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert isinstance(response.value, MockNested)
    assert response.value.multiply(2, 3) == 6


def test_getattr_nested_obj_unpickleable(mock_worker: ApiWorker) -> None:
    """Worker can retrieve nested obj."""
    request = Request(msg_type="getattr", path=["nested_unpickleable"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert isinstance(response.value, ProxyRef)

    obj_id = response.value.obj_id
    assert obj_id in mock_worker.object_store
    assert isinstance(mock_worker.object_store[obj_id], MockUnpickleable)


def test_getattr_nonexistent(mock_worker: ApiWorker) -> None:
    """Worker can retrieve nested obj."""
    request = Request(msg_type="getattr", path=["nonexistent"])
    response = mock_worker.execute_request(request)

    assert not response.success
    assert response.error_type == "AttributeError"
    assert response.error
    assert "nonexistent" in response.error


def test_call_method_with_args(mock_worker: ApiWorker) -> None:
    """Call with method with positional args."""
    request = Request(msg_type="call", path=["add"], args=(10, 20))
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == 30


def test_call_method_with_kwargs(mock_worker: ApiWorker) -> None:
    """Call with method with kwargs."""
    request = Request(msg_type="call", path=["add"], kwargs={"a": 5, "b": 15})
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == 20


def test_call_returns_pickleable(mock_worker: ApiWorker) -> None:
    """Pickleable objects are returned directly."""
    request = Request(msg_type="call", path=["get_list"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert isinstance(response.value, list)
    assert response.value == [1, 2, 3]


def test_call_returns_unpickleable_reference(mock_worker: ApiWorker) -> None:
    """Unpickleable objects are returned by ref."""
    request = Request(msg_type="call", path=["get_object"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert isinstance(response.value, ProxyRef)


def test_call_with_empty_path(mock_worker: ApiWorker) -> None:
    """Calling an empty path returns an error."""
    request = Request(msg_type="call", path=[])
    response = mock_worker.execute_request(request)

    assert not response.success
    assert response.error_type == "ValueError"
    assert response.error
    assert "empty access path" in response.error


def test_call_method_raises_exception(mock_worker: ApiWorker) -> None:
    """Calling an method that raises returns the exception."""
    request = Request(msg_type="call", path=["raise_error"])
    response = mock_worker.execute_request(request)

    assert not response.success
    assert response.error_type == "ValueError"
    assert response.error
    assert "Intentional error" in response.error
    assert response.traceback is not None


def test_setattr_simple_value(mock_worker: ApiWorker) -> None:
    """Worker can set a simple attr."""
    request = Request(msg_type="setattr", path=["value"], value=43)
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value is None

    request = Request(msg_type="getattr", path=["value"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == 43


def test_setattr_nested_obj(mock_worker: ApiWorker) -> None:
    """Worker can set and retrieve nested obj."""
    request = Request(msg_type="setattr", path=["nested", "val"], value=["foo", "bar"])
    response = mock_worker.execute_request(request)

    assert response.success

    request = Request(msg_type="getattr", path=["nested", "val"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == ["foo", "bar"]


def test_setattr_nested_unpickleable_obj(mock_worker: ApiWorker) -> None:
    """Worker can set and retrieve from a nested unpickleable obj."""
    request = Request(
        msg_type="setattr",
        path=["nested_unpickleable", "val"],
        value={"foo": ["bar", "baz"]},
    )
    response = mock_worker.execute_request(request)

    assert response.success

    request = Request(msg_type="getattr", path=["nested_unpickleable", "val"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert response.value == {"foo": ["bar", "baz"]}


def test_reference_retrieval(mock_worker: ApiWorker) -> None:
    """References can be retrieved and used."""
    request1 = Request(msg_type="getattr", path=["nested_unpickleable"])
    response1 = mock_worker.execute_request(request1)
    obj_id = response1.value.obj_id

    request2 = Request(msg_type="call", path=["$ref", obj_id, "sub"], args=(3, 4))
    response2 = mock_worker.execute_request(request2)

    assert response2.success
    assert response2.value == -1


def test_reference_invalid_id(mock_worker: ApiWorker) -> None:
    """Invalid ref ids return an error."""
    request = Request(msg_type="call", path=["$ref", "999", "method"])
    response = mock_worker.execute_request(request)

    assert not response.success
    assert response.error_type == "KeyError"
    assert response.error
    assert "not found in store" in response.error


def test_reference_missing_id(mock_worker: ApiWorker) -> None:
    """Ref without id returns an error."""
    request = Request(msg_type="call", path=["$ref"])
    response = mock_worker.execute_request(request)

    assert not response.success
    assert response.error_type == "ValueError"
    assert response.error
    assert "requires an object id" in response.error


def test_reference_chained_access(mock_worker: ApiWorker) -> None:
    """References can use references."""
    request1 = Request(msg_type="call", path=["get_object"])
    response1 = mock_worker.execute_request(request1)
    obj_id = response1.value.obj_id

    request2 = Request(msg_type="call", path=["$ref", obj_id, "get_value"])
    response2 = mock_worker.execute_request(request2)

    assert response2.success
    assert response2.value == 99


def test_obj_store_increments_id(mock_worker: ApiWorker) -> None:
    """Obj ids increment for each stored object."""
    request1 = Request(msg_type="getattr", path=["nested_unpickleable"])
    response1 = mock_worker.execute_request(request1)
    obj_id1 = response1.value.obj_id

    request2 = Request(msg_type="call", path=["get_object"])
    response2 = mock_worker.execute_request(request2)
    obj_id2 = response2.value.obj_id

    assert obj_id1 != obj_id2
    assert int(obj_id2) == int(obj_id1) + 1


def test_iterator_returns_reference(mock_worker: ApiWorker) -> None:
    """Iterator obs return as ref (unpickleable)."""
    request = Request(msg_type="call", path=["__iter__"])
    response = mock_worker.execute_request(request)

    assert response.success
    assert isinstance(response.value, ProxyRef)


def test_request_serialization_roundtrip() -> None:
    """Serializing and deserializing a request both validate and are equal."""
    request = Request(
        msg_type="call",
        path=["method", "nested"],
        args=(1, 2, 3),
        kwargs={"key": "value"},
    )

    serialized = request.serialize()
    deserialized = Request.deserialize(serialized)

    assert deserialized.msg_type == request.msg_type
    assert deserialized.path == request.path
    assert deserialized.args == request.args
    assert deserialized.kwargs == request.kwargs


def test_response_serialization_roundtrip() -> None:
    """Serializing and deserializing a response both validate and are equal."""
    response = Response(
        success=False,
        error="Test error",
        error_type="TestError",
        traceback="Test traceback",
    )

    serialized = response.serialize()
    deserialized = Response.deserialize(serialized)

    assert deserialized.success == response.success
    assert deserialized.error == response.error
    assert deserialized.error_type == response.error_type
    assert deserialized.traceback == response.traceback


def test_response_with_proxy_reference_serialization() -> None:
    """Response containing a ProxyRef dict can be serialized."""
    response = Response(success=True, value={"obj_id": "42"})

    serialized = response.serialize()
    deserialized = Response.deserialize(serialized)

    assert deserialized.success
    assert deserialized.value == {"obj_id": "42"}
