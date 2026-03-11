"""runrms - used for running RMS in various ways."""

from runrms.exceptions import (
    RmsConfigError,
    RmsConfigNotFoundError,
    RmsExecutableError,
    RmsProjectNotFoundError,
    RmsRuntimeError,
    RmsVersionError,
    RmsWrapperError,
    UnknownConfigError,
)

from ._rms_api import get_executor, get_rmsapi, shutdown, shutdown_all

__all__ = [
    "get_rmsapi",
    "get_executor",
    "shutdown",
    "shutdown_all",
    "RmsRuntimeError",
    "UnknownConfigError",
    "RmsProjectNotFoundError",
    "RmsConfigError",
    "RmsConfigNotFoundError",
    "RmsExecutableError",
    "RmsWrapperError",
    "RmsVersionError",
]
