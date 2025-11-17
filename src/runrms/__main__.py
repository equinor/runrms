import argparse
import subprocess
import sys

from .config import ForwardModelConfig, InteractiveConfig
from .exceptions import UnknownConfigError
from .executor import ForwardModelExecutor, InteractiveExecutor

try:
    from .version import __version__
except ImportError:
    __version__ = "0.0.0"


DESCRIPTION = """
This utility runs or opens an RMS project from the command line. In practice it
is a wrapper around the 'rms' command, itself a wrapper that invokes the RMS
application. Note that not all options valid for 'rms' are mapped into this
utility.

This utility can:
- find the RMS version in RMS project files and launch the correct version
- set environment variables, including a PYTHONPATH, for a site configuration
  that extends the vendor distributed Python packages.
- set the path (via environment variables) to site installed RMS plugins.

Example usage:

    $ runrms drogon.rms14.2.2            # If new project: warn and run the RMS default
    $ runrms drogon.rms14.2.2            # Automatically detect version from .master
    $ runrms drogon.rms14.1.3 -v 14.2.2  # Force version 14.2.2, upgrading the project
"""


def _add_fm_arguments(prs: argparse.ArgumentParser) -> None:
    """Command line options specific to the ERT forward model only."""
    fm_prs = prs.add_argument_group(
        title="ERT forward model options",
        description=(
            "These arguments are relevant for the ERT forward model only. "
            "Specifying '--iens' will cause RMS to be run as an RMS forward model. "
            "Typically you should not be providing these options manually."
        ),
    )
    fm_prs.add_argument(
        "--iens",
        dest="iens",
        type=int,
        help="The ERT realization number",
        default=None,
    )
    fm_prs.add_argument(
        "--run-path",
        default="rms/model",
        help="The directory which will be used as current working directory "
        "when ERT is running rms",
    )
    fm_prs.add_argument(
        "--target-file",
        default=None,
        help="Name of file which should be created/updated by rms",
    )
    fm_prs.add_argument(
        "--import-path",
        default="./",
        help="The prefix of all relative paths when rms is importing",
    )
    fm_prs.add_argument(
        "--export-path",
        default="./",
        help="The prefix of all relative paths when rms is exporting",
    )
    fm_prs.add_argument(
        "--allow-no-env",
        action="store_true",
        help="Allow RMS to run without a site configured environment",
    )


def _add_dev_arguments(prs: argparse.ArgumentParser) -> None:
    """Command line options specific to the ERT forward model only."""
    dev_prs = prs.add_argument_group(
        title="Development/testing options",
        description=(
            "These arguments are for development and testing. "
            "Typically you do not need to use these options."
        ),
    )
    dev_prs.add_argument(
        "--test-env",
        "--testpylib",
        dest="testpylib",
        action="store_true",
        help="This option is deprecated. Use '--setup' or 'rmsenv' instead.",
    )
    dev_prs.add_argument(
        "--setup",
        dest="setup",
        type=str,
        help=(
            "Path to the runrms.yml site configuration. "
            "Defaults to the site configuration actually used."
        ),
    )


def get_parser() -> argparse.ArgumentParser:
    """Make a parser for command line arguments and for documentation."""
    prs = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    prs.add_argument("project", type=str, nargs="?", help="RMS project name")
    prs.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="If you want to run this script in verbose mode",
    )
    prs.add_argument(
        "--project",
        "-p",
        dest="theproject",
        help="Project argument, for backward compaibility (prefer use without this!)",
    )
    prs.add_argument(
        "--dryrun",
        dest="dryrun",
        action="store_true",
        help="Run this script without actually launching RMS",
    )
    prs.add_argument(
        "--version",
        "-v",
        dest="version",
        type=str,
        nargs="?",
        help="The RMS version to run, e.g. 14.2.2.",
    )
    prs.add_argument(
        "--listversions",
        "-l",
        dest="listversions",
        action="store_true",
        help="Use this option to list current RMS versions available. If this option "
        "is set then all other options are disabled.",
    )
    prs.add_argument(
        "--readonly",
        "-r",
        "-readonly",
        dest="readonly",
        action="store_true",
        help="Read only mode (disable save)",
    )
    prs.add_argument(
        "--dpiscaling",
        "-d",
        dest="sdpi",
        default=1.0,
        type=float,
        help="Specify RMS DPI display scaling as a ratio, where 1.0 is no scaling",
    )
    prs.add_argument(
        "--batch",
        "-batch",
        "-w",
        dest="workflow",
        type=str,
        help="Runs project in batch mode with the provided workflow",
    )
    prs.add_argument(
        "--seed",
        "-seed",
        type=int,
        help="The seed to run RMS with. Must be combined with --batch and a project.",
    )
    prs.add_argument(
        "--threads",
        "-threads",
        dest="threads",
        default=1,
        type=int,
        help="The number of threads RMS should use while running.",
    )
    _add_fm_arguments(prs)
    _add_dev_arguments(prs)
    return prs


def generate_config(args: argparse.Namespace) -> ForwardModelConfig | InteractiveConfig:
    """
    Generate a RmsConfig object based on the given args
    """

    if args.iens is None:
        return InteractiveConfig(args)
    return ForwardModelConfig(args)


def generate_executor(
    config: ForwardModelConfig | InteractiveConfig,
) -> InteractiveExecutor | ForwardModelExecutor:
    """
    Generate a RmsExecutor object based on the given RmsConfig
    """

    if isinstance(config, InteractiveConfig):
        return InteractiveExecutor(config)
    if isinstance(config, ForwardModelConfig):
        return ForwardModelExecutor(config)

    raise UnknownConfigError(
        f"Unable to generate executor for config of type {type(config)}"
    )


def _validate_args(parsed_args: argparse.Namespace) -> None:
    if parsed_args.seed and not (parsed_args.workflow and parsed_args.project):
        raise argparse.ArgumentError(
            None, "The --seed option must be combined with --batch and a project."
        )


def main(args: list[str] | None = None) -> int:
    """
    Launch rms
    """
    if args is None:
        args = sys.argv[1:]
    args = [x for x in args if x]
    parsed_args = get_parser().parse_args(args)

    _validate_args(parsed_args)

    config = generate_config(parsed_args)

    if parsed_args.listversions:
        subprocess.run(args=[str(config.executable), "-v"], check=False)
        return 0
    if parsed_args.testpylib:
        print(
            "The '--testpylib'/'--test-env' options are deprecated due to a change in"
            " the way that RMS Python environments are deployed. Use '--setup' or an "
            "rmsenv instead."
        )
        return 0

    executor = generate_executor(config)
    return executor.run()
