import argparse
import logging
import os

from ._rms_config import RmsConfig

logger = logging.getLogger(__name__)


class InteractiveConfig(RmsConfig):
    """A class which holds the necessary configuration for executing
    runrms in interactive mode.

    It is not likely that several instances of the class is required; the
    use of a class here is more for the convinience that 'self' can hold the
    different variables (attributes) across the methods.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        project = os.path.abspath(args.project) if args.project else None
        if project is None and args.theproject:
            project = os.path.abspath(args.theproject)
        super().__init__(config_path=args.setup, version=args.version, project=project)

        self._threads = args.threads
        self._readonly = args.readonly
        self._workflow = args.workflow
        self._debug = args.debug
        self._dryrun = args.dryrun
        self._dpi_scaling = args.sdpi

        for key, value in vars(args).items():
            logger.debug("Arg = %s: %s", key, value)

    @property
    def debug(self) -> bool:
        return self._debug

    @property
    def dryrun(self) -> int:
        return self._dryrun

    @property
    def threads(self) -> int:
        return self._threads

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def workflow(self) -> str | None:
        return self._workflow
