class RmsRuntimeError(Exception):
    """
    Custom error for run-time errors
    """


class UnknownConfigError(Exception):
    """
    Custom error class for unknown config objects
    """


class RmsProjectNotFoundError(OSError):
    """Raised when attempting to open an RMS project that does not exist."""


class RmsConfigError(ValueError):
    """Raised when the configuration file is errorneous."""


class RmsConfigNotFoundError(FileNotFoundError):
    """Raised when attempting to open a site configuration that does not exist."""


class RmsExecutableError(OSError):
    """Raised when the RMS executable cannot be executed, either because it's
    not found or because of invalid user access to it."""


class RmsWrapperError(FileNotFoundError):
    """Raised when the RMS wrapper cannot be found."""


class RmsVersionError(ValueError):
    """Raised when the given rms version does not exist."""
