import glob
import os
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent

from runrms.config import ForwardModelConfig
from runrms.exceptions import RmsRuntimeError

from ._rms_executor import RmsExecutionMode, RmsExecutor


@contextmanager
def pushd(path: str | Path) -> Generator[None, None, None]:
    """pushd functionality"""
    cwd_ = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd_)


class ForwardModelExecutor(RmsExecutor[ForwardModelConfig]):
    """
    Class for executing runrms as forward model job
    """

    def __init__(self, config: ForwardModelConfig) -> None:
        super().__init__(config)
        if (license_file := self.config.site_config.batch_lm_license_file) is not None:
            self.update_exec_env("LM_LICENSE_FILE", license_file)

    def _exec_rms(self) -> int:
        """Execute RMS with given environment"""
        args = self.pre_rms_args()
        args += [
            str(self.config.executable),
            "-project",
            str(self.config.project.path),
            "-seed",
            str(self.config.seed),
            "-readonly",
            "-nomesa",
            "-export_path",
            str(self.config.export_path),
            "-import_path",
            str(self.config.import_path),
            "-batch",
            str(self.config.workflow),
        ]

        if self.config.version:
            args += ["-v", str(self.config.version)]

        if self.config.threads:
            args += ["-threads", str(self.config.threads)]

        comp_process = subprocess.run(args=args, check=False)
        return comp_process.returncode

    def print_failure(self, exit_status: int) -> None:
        run_path = self.config.run_path.resolve()
        # Reverse sort so workflow.log is (probably) first and
        # YYYYMMDD-HHMMSS-XXXXX-RMS.log files are (probably) last
        log_files = sorted(glob.glob(f"{run_path}/*.log"), reverse=True)

        if exit_status == 137:
            # When the OOM-killer strikes, the RMS process (or maybe one of its
            # subprocesses) will get a SIGKILL (9) signal, which is often reported
            # as 128+9=137.
            fail_msg = dedent(
                f"""
        The RMS run failed with exit status: {exit_status}.

        This often means that the compute node ran out of memory and RMS or one of its
        subprocesses was terminated.
                """
            )

        elif not log_files:
            fail_msg = dedent(
                f"""
        The RMS run failed with exit status: {exit_status} and no log files were
        found in:

        * {run_path}

        This may mean that the compute node ran out of memory and RMS or one of its
        subprocesses was terminated, or that some other error has occurred.
                """
            )

        else:
            fail_msg = dedent(
                f"""
        The RMS run failed with exit status: {exit_status}. Typically this means a
        job in an RMS workflow has failed.
                """
            )

        if log_files:
            fail_msg += dedent(
                """
        For more details try checking these log files:

        * RMS.stderr.NN and RMS.stdout.NN
        * rms/model/workflow.log
        * Other named log files in rms/model, e.g. workflow_sim2seis.log
        * rms/model/YYYYMMDD-HHMMSS-XXXXX-RMS.log corresponding to your run

        The following log files were found in this realization's run path:

                """
            )
            fail_msg += "\n".join([f"* {f}" for f in log_files])

        print(fail_msg, file=sys.stderr)

    @property
    def exec_mode(self) -> RmsExecutionMode:
        """Executing in batch mode."""
        return RmsExecutionMode.batch

    def run(self) -> int:
        """Main executor entry point."""
        if not os.path.exists(self.config.run_path):
            os.makedirs(self.config.run_path)

        if (
            self.config._version_given != self.config.version
            and not self.config.allow_no_env
        ):
            raise RmsRuntimeError(
                "RMS environment not specified for version: "
                f"{self.config._version_given}"
            )

        with pushd(self.config.run_path):
            now = time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(time.time()))
            with open("RMS_SEED_USED", "a+", encoding="utf-8") as filehandle:
                filehandle.write(f"{now} ... {self.config.seed}\n")

            if not os.path.exists(self.config.export_path):
                os.makedirs(self.config.export_path)

            if not os.path.exists(self.config.import_path):
                os.makedirs(self.config.import_path)

            exit_status = self._exec_rms()

        if exit_status != 0:
            self.print_failure(exit_status)
            return exit_status

        if self.config.target_file is None:
            return exit_status

        if not os.path.isfile(self.config.target_file):
            raise RmsRuntimeError(
                "The RMS run did not produce the expected file: "
                f"{self.config.target_file}"
            )

        if self.config.target_file_mtime is None:
            return exit_status

        if os.path.getmtime(self.config.target_file) == self.config.target_file_mtime:
            raise RmsRuntimeError(
                f"The target file: {self.config.target_file} is unmodified - "
                "interpreted as failure"
            )
        return exit_status
