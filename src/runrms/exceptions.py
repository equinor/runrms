class RMSRuntimeError(Exception):
    """
    Custom error for run-time errors
    """


class UnknownConfigError(Exception):
    """
    Custom error class for unknown config objects
    """


class RMSProjectNotFoundError(OSError):
    """Raised when attempting to open an RMS project that does not exist."""


class RMSConfigError(ValueError):
    """Raised when the configuration file is errorneous."""


class RMSConfigNotFoundError(FileNotFoundError):
    """Raised when attempting to open a site configuration that does not exist."""


class RMSExecutableError(OSError):
    """Raised when the RMS executable cannot be executed, either because it's
    not found or because of invalid user access to it."""


class RMSWrapperError(FileNotFoundError):
    """Raised when the RMS wrapper cannot be found."""


class RMSVersionError(ValueError):
    """Raised when the given rms version does not exist."""
