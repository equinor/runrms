"""runrms - used for running RMS in various ways."""

from ._rms_api import get_executor, get_rmsapi, shutdown, shutdown_all

__all__ = ["get_rmsapi", "get_executor", "shutdown", "shutdown_all"]
