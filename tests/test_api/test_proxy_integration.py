"""Integration tests for RmsApiProxy with a real worker."""

import time
from subprocess import Popen

import pytest

from runrms.api import RemoteException, RmsApiProxy


def test_simple_attr_access(worker: Popen[bytes], zmq_address: str) -> None:
    """Can access simple attributes."""
    proxy = RmsApiProxy(zmq_address)
    value = proxy.value.get()

    assert value == 42


def test_method_call_with_args(worker: Popen[bytes], zmq_address: str) -> None:
    """Can call methods with args."""
    proxy = RmsApiProxy(zmq_address)
    result = proxy.add(10, 20)

    assert result == 30


def teset_nested_attr_access(worker: Popen[bytes], zmq_address: str) -> None:
    """Can access nested attributes and call methods."""
    proxy = RmsApiProxy(zmq_address)
    result = proxy.nested.multiply(5, 7)

    assert result == 35


def test_unpickleable_object_returns_proxy(
    worker: Popen[bytes], zmq_address: str
) -> None:
    """Unpickleable objects return as proxies."""
    proxy = RmsApiProxy(zmq_address)
    obj = proxy.get_object()

    assert isinstance(obj, RmsApiProxy)
    assert obj.get_value() == 99


def test_set_and_get_attr(worker: Popen[bytes], zmq_address: str) -> None:
    """Can set and retrieve attributes."""
    proxy = RmsApiProxy(zmq_address)

    proxy.value = 100
    assert proxy.value.get() == 100


def test_nested_unpickleable_access(worker: Popen[bytes], zmq_address: str) -> None:
    """Can work with nested unpcikleable objects."""
    proxy = RmsApiProxy(zmq_address)
    result = proxy.nested_unpickleable.sub(10, 3)

    assert result == 7


def test_iteration_protocol(worker: Popen[bytes], zmq_address: str) -> None:
    """Can iterate over proxy objects."""
    proxy = RmsApiProxy(zmq_address)

    iterator = iter(proxy)
    values = [next(iterator) for _ in range(3)]

    assert values == [1, 2, 3]
    with pytest.raises(StopIteration):
        next(iterator)


def test_remote_exception_propagates(worker: Popen[bytes], zmq_address: str) -> None:
    """Remote exceptions propagate correctly."""
    proxy = RmsApiProxy(zmq_address)

    with pytest.raises(RemoteException, match="Intentional error") as e:
        proxy.raise_error()

    assert e.value.remote_type == "ValueError"
    assert e.value.remote_traceback is not None


def test_operations_on_unpickleable_reference(
    worker: Popen[bytes], zmq_address: str
) -> None:
    """Test that dunder operations on an reference are forwarded to the worker."""
    proxy = RmsApiProxy(zmq_address)
    ref = proxy.nested_unpickleable
    assert isinstance(ref, RmsApiProxy)

    assert ref[0] == "a"  # __getitem__
    assert len(ref) == 3  # __len__
    assert "z" not in ref  # __contains__
    assert str(ref) == "['a', 'b', 'c']"
    assert repr(ref) == "MockUnpickleable(['a', 'b', 'c'])"

    ref[0] = "z"  # __setitem__
    assert ref[0] == "z"  # __getitem__
    assert "z" in ref  # __contains__

    assert str(ref) == "['z', 'b', 'c']"  # __str__
    assert repr(ref) == "MockUnpickleable(['z', 'b', 'c'])"  # __repr__

    del ref[0]  # __delitem__
    assert ref[0] == "b"  # __getitem__
    assert len(ref) == 2  # __len__
    assert "z" not in ref  # __contains__

    assert str(ref) == "['b', 'c']"  # __str__
    assert repr(ref) == "MockUnpickleable(['b', 'c'])"  # __repr__

    assert bool(ref) is True  # __bool__ (has items)

    with pytest.raises(RemoteException, match="Remote TypeError: int()"):
        int(ref)  # __int__

    with pytest.raises(RemoteException, match="Remote TypeError: float()"):
        float(ref)  # __float__

    assert ref == ["b", "c"]  # __eq__
    assert ref != ["z", "b", "c"]  # __ne__
    assert ref > ["a", "b"]  # __gt__  (lexicographic ordering for list str comparisons)
    assert ref >= ["b", "c"]  # __ge__
    assert ref < ["d", "e"]  # __lt__
    assert ref <= ["c", "d"]  # __le__

    can_hash = {ref: 1}  # __hash__
    assert can_hash[ref] == 1


def test_ping_worker(worker: Popen[bytes], zmq_address: str) -> None:
    """Can ping worker."""
    proxy = RmsApiProxy(zmq_address)

    assert proxy._ping() is True


def test_shutdown_worker(worker: Popen[bytes], zmq_address: str) -> None:
    """Can shutdown worker."""
    proxy = RmsApiProxy(zmq_address)

    proxy._shutdown()
    proxy._cleanup()

    time.sleep(0.1)  # Let it stop, hopefully
    assert worker.poll() == 0
