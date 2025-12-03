from __future__ import annotations

from typing import Any

import zmq

from runrms._logging import null_logger

from .worker import Request, Response

logger = null_logger(__name__)


class RemoteException(Exception):
    """Exception raised when remote call fails."""

    def __init__(
        self,
        message: str,
        remote_type: str | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        """Exception with serialized data."""
        super().__init__(message)
        self.remote_type = remote_type
        self.remote_traceback = remote_traceback

    def __str__(self) -> str:
        parts = [f"Remote {self.remote_type}: {super().__str__()}"]
        if self.remote_traceback:
            parts.append("\nRemote traceback:")
            parts.append(self.remote_traceback)
        return "\n".join(parts)


class RmsApiProxy:
    """Proxy object that forwards all operations to worker process.

    This is the class that is returned to users. When they do

    >>> rmsapi = get_rmsapi("14.2.2")  # Returns an RmsApiProxy

    and run operations on rmsapi, it forwards almost all of them to the worker. So:

    >>> project = rmsapi.Project.open()  # Returns an RmsApiProxy

    will return a child-`RmsApiProxy` with the same zmq socket and context passed to it.
    The root proxy sends a 'getattr' to the worker. In every child proxy, the internal
    path is kept as the current "state" of what the proxy is representing. In this case,
    it would be proxy reference.

    Then, the `open()` method is a `__call__` on the child proxy. It forwards this to
    the worker, which returns a reference to the project stored in the worker. This
    creates another child RmsApiProxy with the same connection info.
    """

    def __init__(
        self,
        zmq_address: str,
        path: list[str] | None = None,
        *,
        _shared_context: zmq.Context[zmq.Socket[bytes]] | None = None,
        _shared_socket: zmq.Socket[bytes] | None = None,
        rcv_timeout_ms: int = 30000,
        snd_timeout_ms: int = 5000,
    ) -> None:
        """Initialize proxy.

        Args:
            zmq_address: ZMQ address to connect to
            path: Current attribute path (for nested access)
            _shared_context: Shared ZMQ context for child proxies
            _shared_socket: Shared ZMQ socket for child proxies
            rcv_timeout_ms: Receive timeout in milliseconds
            snd_timeout_msg: Send timeout in milliseconds
        """
        self._zmq_address = zmq_address
        self._path = path or []
        self.__context: zmq.Context[zmq.Socket[bytes]] | None = _shared_context
        self.__socket: zmq.Socket[bytes] | None = _shared_socket
        self._is_root = _shared_context is None and _shared_socket is None
        self._rcv_timeout_ms = rcv_timeout_ms
        self._snd_timeout_ms = snd_timeout_ms

        if self._is_root:
            self._setup_zmq()

    @property
    def _context(self) -> zmq.Context[zmq.Socket[bytes]]:
        if not self.__context:
            raise RuntimeError(
                "ZMQ context not initialized. This should not happen - "
                "please report this as a bug."
            )
        return self.__context

    @property
    def _socket(self) -> zmq.Socket[bytes]:
        if not self.__socket:
            raise RuntimeError(
                "ZMQ socket not initialized. This should not happen - "
                "please report this as a bug."
            )
        return self.__socket

    def _setup_zmq(self) -> None:
        """Setup ZMQ socket connection."""
        if self.__context is not None:
            logger.warning("ZMQ context already exists, skipping setup")
            return

        logger.debug("Creating ZMQ context")
        self.__context = zmq.Context()

        logger.debug("Creating REQ socket")
        self.__socket = self._context.socket(zmq.REQ)

        logger.debug(f"Connecting to {self._zmq_address}")
        self.__socket.connect(self._zmq_address)

        logger.debug(
            "Configuring timeouts: "
            f"recv={self._rcv_timeout_ms}ms, snd={self._snd_timeout_ms}ms"
        )
        self.__socket.setsockopt(zmq.RCVTIMEO, self._rcv_timeout_ms)
        self.__socket.setsockopt(zmq.SNDTIMEO, self._snd_timeout_ms)

        logger.info("Proxy initialized and connected")

    def _send_request(self, request: Request) -> Response:
        """Send request and receive response."""
        try:
            request_data = request.serialize()
            logger.debug(
                f"Sending {request.msg_type} for path "
                f"{'.'.join(request.path) if request.path else '<root>'} "
                f"({len(request_data)} bytes)"
            )

            self._socket.send(request_data)
            response_data = self._socket.recv()

            logger.debug(f"Received response ({len(response_data)} bytes)")
            response = Response.deserialize(response_data)

            if not response.success:
                if response.error_type == "StopIteration":
                    raise StopIteration

                logger.error(f"Remote error: {response.error_type} - {response.error}")
                raise RemoteException(
                    response.error or "Unknown error",
                    response.error_type,
                    response.traceback,
                )
            return response
        except TypeError as e:
            raise TypeError(
                "Unable to serialize request to rmsapi. This can happen for "
                "several reasons:\n"
                "1. You're using an attribute like 'some.attr' directly. You must "
                "instead use 'some.attr.get()' to use the actual value.\n"
                "2. You're passing an object where some attribute is being used "
                "in a way similar to 1. You must call '.get()' on it first.\n"
                f"Details: Request: {request}, Error: {e}"
            ) from e
        except zmq.Again as e:
            logger.error(f"Request timed out after {self._rcv_timeout_ms}ms")
            raise TimeoutError(f"Request timed out: {e}") from e
        except zmq.ZMQError as e:
            logger.error(f"ZMQ error: {e}")
            raise ConnectionError(f"ZMQ error: {e}") from e

    def _handle_response_value(self, response: Response) -> Any:
        """Handle the response, return a proxy if needed."""
        if isinstance(response.value, dict) and "obj_id" in response.value:
            new_path = ["$ref", response.value["obj_id"]]
            return self._create_child_proxy(new_path)
        return response.value

    def _create_child_proxy(self, new_path: list[str]) -> RmsApiProxy:
        """Create a child proxy with an extended path."""
        return RmsApiProxy(
            self._zmq_address,
            path=new_path,
            _shared_context=self._context,
            _shared_socket=self._socket,
            rcv_timeout_ms=self._rcv_timeout_ms,
            snd_timeout_ms=self._snd_timeout_ms,
        )

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to worker."""
        if name == "__version__":
            request = Request(msg_type="getattr", path=["__version__"])
            response = self._send_request(request)
            return response.value

        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        # For simple attrs, need to check if it's callable
        # Return a new proxy with extended path to chain it
        new_path = [*self._path, name]
        return self._create_child_proxy(new_path)

    def get(self) -> Any:
        """Fetch and return the actual value."""
        if not self._path:
            raise RuntimeError("Cannot get value of root proxy.")

        request = Request(msg_type="getattr", path=self._path)
        response = self._send_request(request)
        return self._handle_response_value(response)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Forward method call to worker."""
        if not self._path:
            raise TypeError("Root proxy is not callable")

        request = Request(msg_type="call", path=self._path, args=args, kwargs=kwargs)
        response = self._send_request(request)
        return self._handle_response_value(response)

    def __iter__(self) -> Any:
        """Forward iteration to worker."""
        request = Request(msg_type="call", path=[*self._path, "__iter__"])
        response = self._send_request(request)
        return self._handle_response_value(response)

    def __next__(self) -> Any:
        """Forward next() to worker."""
        request = Request(msg_type="call", path=[*self._path, "__next__"])
        response = self._send_request(request)
        return self._handle_response_value(response)

    def __setattr__(self, name: str, value: Any) -> None:
        """Forward attribute setting to worker."""
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        path = [*self._path, name]
        request = Request(msg_type="setattr", path=path, value=value)
        self._send_request(request)

    def __getitem__(self, key: Any) -> Any:
        """Forward subscript access to worker (e.g. obj[key])."""
        request = Request(
            msg_type="call", path=[*self._path, "__getitem__"], args=(key,)
        )
        response = self._send_request(request)
        return self._handle_response_value(response)

    def __setitem__(self, key: Any, value: Any) -> Any:
        """Forward subscript assignment to worker (e.g. obj[key] = value)."""
        request = Request(
            msg_type="call", path=[*self._path, "__setitem__"], args=(key, value)
        )
        self._send_request(request)

    def __delitem__(self, key: Any) -> Any:
        """Forward subscript deletion to worker (e.g. del obj[key])."""
        request = Request(
            msg_type="call", path=[*self._path, "__delitem__"], args=(key,)
        )
        self._send_request(request)

    def __contains__(self, item: Any) -> Any:
        """Forward 'in' operator to worker (e.g. item in obj)."""
        request = Request(
            msg_type="call", path=[*self._path, "__contains__"], args=(item,)
        )
        response = self._send_request(request)
        return response.value

    def __str__(self) -> str:
        """Forward string conversion to worker."""
        if not self._path:
            return f"<RmsApiProxy connected to {self._zmq_address}>"

        request = Request(msg_type="call", path=[*self._path, "__str__"])
        response = self._send_request(request)
        return response.value

    def __repr__(self) -> str:
        """Forward repr conversion to worker."""
        if not self._path:
            return f"<RmsApiProxy connected to {self._zmq_address}>"

        request = Request(msg_type="call", path=[*self._path, "__repr__"])
        response = self._send_request(request)
        return response.value

    def __len__(self) -> int:
        """Forward len() to worker."""
        request = Request(msg_type="call", path=[*self._path, "__len__"])
        response = self._send_request(request)
        return response.value

    def __bool__(self) -> int:
        """Forward bool() to worker."""
        request = Request(msg_type="call", path=[*self._path, "__bool__"])
        response = self._send_request(request)
        return response.value

    def __int__(self) -> int:
        """Forward int() to worker."""
        request = Request(msg_type="call", path=[*self._path, "__int__"])
        response = self._send_request(request)
        return response.value

    def __float__(self) -> int:
        """Forward float() to worker."""
        request = Request(msg_type="call", path=[*self._path, "__float__"])
        response = self._send_request(request)
        return response.value

    def __eq__(self, other: Any) -> bool:
        """Forward equality comparison to worker (e.g. obj == other)."""
        request = Request(msg_type="call", path=[*self._path, "__eq__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __ne__(self, other: Any) -> bool:
        """Forward inequality comparison to worker (e.g. obj != other)."""
        request = Request(msg_type="call", path=[*self._path, "__ne__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __lt__(self, other: Any) -> bool:
        """Forward less than comparison to worker (e.g. obj < other)."""
        request = Request(msg_type="call", path=[*self._path, "__lt__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __le__(self, other: Any) -> bool:
        """Forward less than or equal to comparison to worker (e.g. obj <= other)."""
        request = Request(msg_type="call", path=[*self._path, "__le__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __gt__(self, other: Any) -> bool:
        """Forward greater than comparison to worker (e.g. obj >= other)."""
        request = Request(msg_type="call", path=[*self._path, "__gt__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __ge__(self, other: Any) -> bool:
        """Forward greater than or equal to comparison to worker (e.g. obj > other)."""
        request = Request(msg_type="call", path=[*self._path, "__ge__"], args=(other,))
        response = self._send_request(request)
        return response.value

    def __hash__(self) -> int:
        """Forward hash request to worker.

        This is required to place items as keys in dictionaries, sets, etc."""
        request = Request(msg_type="call", path=[*self._path, "__hash__"])
        response = self._send_request(request)
        return response.value

    def __del__(self) -> None:
        """Clean-up if GC'd.

        This is not sent to the worker."""
        self._cleanup()

    def _ping(self) -> bool:
        """Check if worker is responsive."""
        if not self._is_root:
            raise RuntimeError("Ping can only be called on root proxy")

        try:
            logger.debug("Sending ping to worker")
            request = Request(msg_type="ping", path=[])

            response = self._send_request(request)
            success = response.value == "pong"

            logger.debug(f"Ping {'successful' if success else 'failed'}")
            return success
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
            return False

    def _shutdown(self) -> None:
        """Request worker to shutdown."""
        if not self._is_root:
            raise RuntimeError("Shutdown can only be called on root proxy")

        logger.info("Sending shutdown to worker")
        request = Request(msg_type="shutdown", path=[])
        self._send_request(request)
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up ZMQ resources."""
        if not self._is_root:
            return

        if self.__socket:
            self.__socket.close()
            self.__socket = None
        if self.__context:
            self.__context.term()
            self.__context = None
