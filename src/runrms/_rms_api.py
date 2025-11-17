"""Main api entry point."""

import atexit
from typing import Any

from ._logging import null_logger
from .api import RmsApiProxy
from .config import ApiConfig
from .executor import ApiExecutor

logger = null_logger(__name__)

_executors: list[ApiExecutor] = []
_last_executor: ApiExecutor | None = None


def get_executor(
    version: str,
    project: str | None = None,
    config_path: str | None = None,
    zmq_address: str | None = None,
    **executor_kwargs: Any,
) -> ApiExecutor:
    """Get an RMS API executor.

    This returns the executor itself to have full control over its lifespan.
    """
    global _last_executor  # noqa: PLW0603 global bad

    logger.info(f"Creating RMS API executor for version {version}")

    config = ApiConfig(
        project=project,
        config_path=config_path,
        version=version,
    )
    executor = ApiExecutor(config, zmq_address=zmq_address, **executor_kwargs)

    _executors.append(executor)
    _last_executor = executor

    logger.debug("Created executor, starting worker")
    return executor


def get_rmsapi(
    version: str,
    project: str | None = None,
    config_path: str | None = None,
    zmq_address: str | None = None,
    **executor_kwargs: Any,
) -> RmsApiProxy:
    """Get an RMS API proxy for the specified version.

    This is the main entry point for accessing the RMS API. It creates an executor,
    starts the worker process, and returns a proxy object that can be used to interact
    with the RMS API.

    The executor is tracked internally and will be automatically cleaned up on exit. For
    manual cleanup, use `shutdown()` to close the most recent executor, or
    `shutdown_all()` to close all executors.

    Args:
        version: RMS Version to use (e.g. "14.2.2" or "15.1.0.0")
        project: Optional path to RMS project file
        config_path: Optional path to custom configuration file
        zmq:address: Optional ZMQ address (auto-generated if not provided)
        **executor_kwargs: Additional arguments passed to ApiExecutor (e.g.
            startup_timeout, ping_retries)

    Returns:
        RmsApiProxy instance for interacting with RMS API.

    Raises:
        ValueError: If version is not specified
        RuntimeError: If worker process fails to start or respond

    Example:
        >>> rmsapi = get_rmsapi("14.2.2")
        >>> print(rmsapi.__version__)
        >>> rmsapi.project.close()
        >>> shutdown()
    """
    executor = get_executor(
        version=version,
        project=project,
        config_path=config_path,
        zmq_address=zmq_address,
        **executor_kwargs,
    )
    logger.debug("Starting executor and returning proxy")
    return executor.run()


def shutdown() -> None:
    """Shutdown the most recently created executor."""
    global _last_executor  # noqa: PLW0603 global bad

    if _last_executor is not None:
        logger.info("Shutting down most recent executor")
        try:
            _last_executor.shutdown()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            _last_executor = None
    else:
        logger.debug("No executor to shutdown")


def shutdown_all() -> None:
    """Shutdown all tracked executors.

    This is called automatically on exit."""
    global _last_executor  # noqa: PLW0603 global bad

    # Get all executors that haven't been GC'd
    executors = list(_executors)

    if not executors:
        logger.debug("No executors to shutdown")
        return

    logger.info(f"Shutting down {len(executors)} executor(s)")

    for executor in executors:
        try:
            executor.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")

    _executors.clear()
    _last_executor = None

    logger.info("All executors shutdown complete")


atexit.register(shutdown_all)
