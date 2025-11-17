"""Worker process that hosts the actual API and responds to zmq requests.

This file is executed as a script by the API Executor. All dependencies it needs should
therefore be in this file. Do not remove the response/request objects, and do not import
other things in this package into this file.

Both zmq and Pydantic are required to be installed in the RMS environment.
"""

import pickle
import signal
import sys
import traceback
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any, Final, Literal, Self

import zmq
from pydantic import BaseModel


class ProxyRef(BaseModel):
    """Reference to a non-pickleable object stored on the worker side."""

    obj_id: str


class Request(BaseModel):
    """Request sent from proxy to worker."""

    msg_type: Literal["getattr", "call", "setattr", "shutdown", "ping"]
    """The message types that are understood in the protocol.

    Cannot be an enum due to 'runrms' being serialized into the message, which is
    unavailable on the RMS side."""

    path: list[str]
    """The access path into an object.

    If the proxy is on 'rmsapi' and 'rmsapi.zones' is accessed, the path is 'zones'.
    However, if the proxy is an object reference (e.g. 'project'), the path will be an
    int. This int is an object id and can then be accessed from stored objects.
    """

    args: tuple[Any, ...] = ()
    """Args given to a called method."""

    kwargs: dict[str, Any] = {}
    """Kwargs given to a called method."""

    value: Any = None
    """Provided for a 'setattr' message. This value is ignored otherwise."""

    def serialize(self) -> bytes:
        """Pickles the model with serializable Python objects."""
        data = self.model_dump(mode="python")
        return pickle.dumps(data)

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Unpickle request from bytes."""
        data_dict = pickle.loads(data)
        return cls.model_validate(data_dict)


class Response(BaseModel):
    """Response sent from worker to proxy."""

    success: bool
    value: Any = None
    """The value returned from a getattr or call."""
    error: str | None = None
    error_type: str | None = None
    traceback: str | None = None

    def serialize(self) -> bytes:
        """Pickles the model with serializable Python objects."""
        data = self.model_dump(mode="python")
        return pickle.dumps(data)

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Unpickle request from bytes."""
        data_dict = pickle.loads(data)
        return cls.model_validate(data_dict)


class ApiWorker:
    """Worker process that executes API calls via ZMQ."""

    script_path: Final[Path] = Path(__file__).parent / "worker.py"

    def __init__(self, zmq_address: str) -> None:
        """Creates the RMS API worker.

        Args:
            zmq_address: The address ZMQ will communicate over. Expected to have a
                'tcp://' or 'ipc://' prefix already.

        This class communicates with the proxy and holds a reference to 'rmsapi',
        executing functions via RPC call from the proxy.

        Python objects that can be pickled are returned back to the proxy. However, many
        RMS objects are Boost C++ objects. By default boost does not make objects
        pickleable, which means they cannot be sent back to the proxy.

        The solution to this is to keep an in-memory cache of these objects. They are
        given a numerical reference number and stored in 'object_store'. A reference is
        returned back to the proxy, and if or when the client executes something on it,
        the object id reference is sent with the request and the worker will do it here.

        A running counter for the objects is kept here as 'next_id'. This is
        stored and communicated as a string and is converted from 'next_id'.
        """
        self.zmq_address = zmq_address
        self._context: zmq.Context[zmq.Socket[bytes]] | None = None
        self._socket: zmq.Socket[bytes] | None = None
        self._api_object: ModuleType | None = None
        self.running = True

        self.object_store: dict[str, Any] = {}
        # Incremented to track object ids stored in the store
        self.next_id = 0

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals."""
        self.running = False

    def setup_zmq(self) -> None:
        """Setup ZMQ context and socket."""
        self._context = zmq.Context()
        self._socket = self.context.socket(zmq.REP)
        self._socket.bind(self.zmq_address)
        self._socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 sec timeout

    @property
    def context(self) -> zmq.Context[zmq.Socket[bytes]]:
        if self._context is None:
            raise RuntimeError("ZMQ context not established.")
        return self._context

    @property
    def socket(self) -> zmq.Socket[bytes]:
        if self._socket is None:
            raise RuntimeError("ZMQ socket not established.")
        return self._socket

    def _resolve_object(self, request: Request) -> tuple[Any, list[str]]:
        """Resolve object from request path.

        Start at the 'root' of 'rmsapi', which is 'rmsapi' itself.
        In the following logic we will drill down to the actual object we need to
        work on, which may be something new, specified by a 'path', or it may
        actually be a reference to an existing object we've stored in the object
        store, and which was sent with the request (a ProxyRef dict).
        """
        obj: Any = self.api_object
        path_to_traverse = request.path

        # This is a reference to an object we've seen and stored before.
        if request.path and request.path[0] == "$ref":
            # A reference was sent, but not its id!
            if len(request.path) < 2:
                raise ValueError("$ref requires an object id")

            obj_id = request.path[1]
            if obj_id not in self.object_store:
                raise KeyError(f"Object id {obj_id} not found in store")

            obj = self.object_store[obj_id]
            # We have the reference object. But are we accessing things on it?
            # We still have to traverse the path to see, and it depends on the RPC
            # call, too.
            path_to_traverse = request.path[2:]

        return obj, path_to_traverse

    def execute_request(self, request: Request) -> Response:
        """Execute a request and return response."""
        try:
            if request.msg_type == "ping":
                return Response(success=True, value="pong")

            if request.msg_type == "shutdown":
                self.running = False
                return Response(success=True, value="shutting down")

            obj, path = self._resolve_object(request)

            if request.msg_type == "getattr":
                result = self._execute_getattr(obj, path)
            elif request.msg_type == "call":
                result = self._execute_call(obj, path, request.args, request.kwargs)
            elif request.msg_type == "setattr":
                self._execute_setattr(obj, path, request.value)
                result = None
            else:
                # Should be unreachable, as Pydantic validation will have failed at
                # Request object instantiation.
                raise ValueError(f"Unknown message type: {request.msg_type}")

            return self._make_response(result)

        except StopIteration:
            return Response(
                success=False,
                error="StopIteration",
                error_type="StopIteration",
                traceback=None,
            )
        except Exception as e:
            return Response(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )

    def _execute_getattr(self, obj: Any, path: list[str]) -> Any:
        """Execute getattr traversal."""
        for attr in path:
            obj = getattr(obj, attr)
        return obj

    def _execute_call(
        self, obj: Any, path: list[str], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        """Execute method call."""
        if not path:
            raise ValueError("Cannot call method on empty access path")

        # Get to the actual method
        for attr in path[:-1]:
            obj = getattr(obj, attr)

        method = getattr(obj, path[-1])
        return method(*args, **kwargs)

    def _execute_setattr(self, obj: Any, path: list[str], value: Any) -> None:
        """Execute setattr."""
        if not path:
            raise ValueError("Cannot 'setattr' on empty path")

        for attr in path[:-1]:
            obj = getattr(obj, attr)

        setattr(obj, path[-1], value)

    def _make_response(self, result: Any) -> Response:
        """Create response, storing non-pickleable objects and returning a ProxyRef.

        This handles a few issues around pickling:

        - If pickling fails on the result, it is returned as a ProxyRef.
        - Pickled can succeed, but contain a reference to '_rmsapi' or 'rmsapi'. Python
          will attempt to re-assemble it on the client side, but fail because those
          packages do not exist there. So check the module name and create a ProxyRef if
          so, by raising an exception that is caught.
        """
        result_type = type(result)
        module_name = result_type.__module__

        try:
            pickle.dumps(result)

            if module_name and module_name.startswith(("rmsapi", "_rmsapi")):
                raise TypeError("Cannot unpickle on client side")

            response = Response(success=True, value=result)
            response.serialize()  # Ensure it can be serialized
            return response
        except (
            AttributeError,
            ModuleNotFoundError,
            RuntimeError,
            TypeError,
            pickle.PicklingError,
        ):
            obj_id = str(self.next_id)
            self.object_store[obj_id] = result

            self.next_id += 1

            return Response(success=True, value=ProxyRef(obj_id=obj_id))

    def run(self, api_object: Any | None = None) -> None:
        """Main worker loop."""
        try:
            if not api_object:
                import rmsapi  # type: ignore[import-not-found] # noqa: PLC0415 top of file
                import rmsapi.jobs  # type: ignore[import-not-found] # noqa: PLC0415 top of file
                import rmsapi.rms  # type: ignore[import-not-found] # noqa: PLC0415 top of file

                self.api_object = rmsapi
            else:
                self.api_object = api_object
            self.setup_zmq()

            while self.running:
                try:
                    data = self.socket.recv()
                    request = Request.deserialize(data)

                    response = self.execute_request(request)
                    self.socket.send(response.serialize())

                    if request.msg_type == "shutdown":
                        break
                except zmq.Again:  # Timeout
                    continue
                except Exception as e:
                    response = Response(
                        success=False,
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc(),
                    )
                    self.socket.send(response.serialize())

        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.socket:
            self.socket.close()
            self._socket = None
        if self.context:
            self.context.term()
            self._context = None


def main() -> None:
    """Entry point for worker process."""
    if len(sys.argv) < 2:
        print("Usage: worker.py <zmq_address>", file=sys.stderr)
        sys.exit(1)

    zmq_address = sys.argv[1]
    worker = ApiWorker(zmq_address)
    worker.run()


if __name__ == "__main__":
    main()
