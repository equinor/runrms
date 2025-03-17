import logging

logger = logging.getLogger(__name__)


class BColors:
    # pylint: disable=too-few-public-methods
    # local class for ANSI term color commands

    HEADER = "\033[93;42m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARN = "\033[93;43m"
    ERROR = "\033[93;41m"
    CRITICAL = "\033[1;91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def xwarn(mystring: str) -> None:
    """Print a warning with colors."""
    print(BColors.WARN, mystring, BColors.ENDC)


def xalert(mystring: str) -> None:
    """Print an alert warning in an appropriate color."""
    print(BColors.ERROR, mystring, BColors.ENDC)


def xcritical(mystring: str) -> None:
    """Print an critical error in an appropriate color."""
    print(BColors.CRITICAL, mystring, BColors.ENDC)
