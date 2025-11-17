import datetime
import getpass
import logging
import platform
import shutil
import subprocess
import time

from runrms._utils import BColors, xalert, xwarn
from runrms.config import InteractiveConfig
from runrms.version import __version__

from ._rms_executor import RmsExecutionMode, RmsExecutor

logger = logging.getLogger(__name__)


class InteractiveExecutor(RmsExecutor[InteractiveConfig]):
    """
    Class for executing runrms in interactive mode
    """

    def _handle_locked_project(self) -> None:
        """Do action if project is locked."""
        xwarn(
            "NB! Opening a locked RMS project (you have 5 seconds to press "
            "Ctrl-C to abort)"
        )
        for sec in range(5, 0, -1):
            time.sleep(1)
            print(f"... {sec}")

    def _exec_rms(self) -> int:
        """Launch RMS with correct pythonpath, pluginspath etc."""
        self.update_exec_env("QT_SCALE_FACTOR", str(self.config._dpi_scaling))
        pre_args = self.pre_rms_args()

        args = [
            str(self.config.executable),
            "-v",
            str(self.config.version),
        ]
        if self.config.readonly:
            args.append("-readonly")

        if self.config.workflow:
            args += ["-batch", str(self.config.workflow)]

        if self.config.project:
            args += ["-project", str(self.config.project.path)]

        self.command = " ".join(args)
        print(BColors.BOLD, f"\nRunning: {self.command}\n", BColors.ENDC)
        print("=" * shutil.get_terminal_size((132, 20)).columns)

        if self.config.project and self.config.project.locked:
            self._handle_locked_project()

        if self.config.debug is False:
            print(BColors.OKGREEN)

        if self.config.dryrun:
            xwarn("<<<< DRYRUN, do not start RMS >>>>")
            print(BColors.ENDC)
            return 0

        logger.debug(f"Execution environment: \n{self._exec_env}")
        rms_process = subprocess.run(pre_args + args, check=True)
        print(BColors.ENDC)
        return rms_process.returncode

    @property
    def exec_mode(self) -> RmsExecutionMode:
        """Executing in interacting mode."""
        return RmsExecutionMode.interactive

    def run(self) -> int:
        """Main executor function"""
        self.showinfo()
        status = self._exec_rms()

        logger.debug("Status from subprocess: %s", status)

        print(
            BColors.BOLD,
            "\nRunning <runrms>. Type <runrms -h> for help\n",
            BColors.ENDC,
        )
        if not self.config.dryrun:
            self.runlogger()
        return status

    def runlogger(self) -> None:
        """Add a line to 'interactive_usage_log' defined in the site configuration.

        This log is structured as a csv with the following columns:

            date, time, user, host, full_rms_exe, commandline_options
        """
        if (
            not self.config.site_config.interactive_usage_log
            or not (usage_log := self.config.site_config.interactive_usage_log).exists()
        ):
            return

        now = datetime.datetime.now()
        nowtime = now.strftime("%Y-%m-%d,%H:%M:%S")
        user = getpass.getuser()
        host = platform.node()

        lline = "{},{},{},{},{},{}\n".format(
            nowtime, user, host, "client", self.config.executable, self.command
        )

        with open(usage_log, "a") as logg:
            logg.write(lline)

        logger.debug("Logging usage to %s:", str(usage_log))
        logger.debug(lline)

    def showinfo(self) -> None:
        """Show info on RMS project."""
        fmt = "{0:30s}: {1}"
        fmt_two = "{0:30s}: {1} {2}"
        print("=" * shutil.get_terminal_size((132, 20)).columns)
        print(f"Script runrms version {__version__}")
        print("=" * shutil.get_terminal_size((132, 20)).columns)
        print(fmt.format("Setup for runrms", self.config.site_config_file))
        print(fmt.format("Current default version", self.config.site_config.default))
        print(fmt.format("RMS version requested", self.config.version_given))
        print(fmt.format("RMS version using", self.config.version))

        if self.config.project:
            print(fmt.format("RMS project version", self.config.project.master.version))
            print(fmt.format("Project name", self.config.project.name))
            print(fmt.format("Last saved by", self.config.project.master.user))
            print(
                fmt_two.format(
                    "Last saved date & time",
                    self.config.project.master.date,
                    self.config.project.master.time,
                )
            )
            print(fmt.format("Locking info", self.config.project.lockfile))
            print(fmt.format("RMS fileversion", self.config.project.master.fileversion))
            print(fmt.format("RMS variant", self.config.project.master.variant))

        order = "first"
        print(fmt.format(f"PYTHONPATH added as {order}", self.config.env.PYTHONPATH))
        print(fmt.format("RMS plugins path", self.config.env.RMS_PLUGINS_LIBRARY))
        print(fmt.format("TCL/TK path", self.config.env.TCL_LIBRARY))
        print(fmt.format("APS_TOOLBOX path", self.config.env.APS_TOOLBOX_PATH or ""))
        print(fmt.format("RMS DPI scaling", self.config._dpi_scaling))
        print(fmt.format("RMS executable", self.config.executable))
        print("=" * shutil.get_terminal_size((132, 20)).columns)
        print("=" * shutil.get_terminal_size((132, 20)).columns)

        expected_extension = f"rms{self.config.version}"
        if self.config.project and not self.config.project.name.endswith(
            expected_extension
        ):
            proj_name = self.config.project.name
            given_extension = proj_name.split(".", 1)[-1]

            if "rms" in proj_name:
                proj_ext_version = proj_name.split("rms")[-1]
                given_extension = f"rms{proj_ext_version}"

            xalert(
                "NOTE: Project name extension inconsistent with RMS version. "
                f"Expected <{expected_extension}>, got <{given_extension}>",
            )
