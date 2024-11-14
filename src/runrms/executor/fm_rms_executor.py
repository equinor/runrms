from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from textwrap import dedent
from typing import TYPE_CHECKING, Generator

from ._rms_executor import RMSExecutor, RMSRuntimeError

if TYPE_CHECKING:
    from pathlib import Path

    from runrms.config.fm_rms_config import FMRMSConfig


@contextmanager
def pushd(path: str | Path) -> Generator[None, None, None]:
    """pushd functionality"""
    cwd_ = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd_)


class FMRMSExecutor(RMSExecutor):
    """
    Class for executing runrms as forward model job
    """

    config: FMRMSConfig

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

    def _add_env_from_json(self) -> None:
        # This function is to be removed/changed
        # PYTHONPATH and PATH_PREFIX that could come from this json
        # should be explicitly handled. These will arrive as
        # RMS_PYTHONPATH and RMS_PATH_PREFIX in the existing environment(?)
        self_exe, _ = os.path.splitext(os.path.basename(sys.argv[0]))
        exec_env_file = f"{self_exe}_exec_env.json"

        user_env = {}
        if os.path.isfile(exec_env_file):
            with open(exec_env_file, encoding="utf-8") as f:
                user_env = json.load(f)

        for key in set(self._exec_env.keys()) | set(user_env.keys()):
            if user_env.get(key):
                self._update_exec_env(key, str(user_env.get(key)), "json")

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

    def run(self) -> int:
        """Main executor entry point."""
        if not os.path.exists(self.config.run_path):
            os.makedirs(self.config.run_path)

        if (
            self.config._version_given != self.config.version
            and not self.config.allow_no_env
        ):
            raise RMSRuntimeError(
                "RMS environment not specified for version: "
                f"{self.config._version_given}"
            )

        self._initialize_exec_env_from_config()
        if (license_file := self.config.site_config.batch_lm_license_file) is not None:
            self._update_exec_env("LM_LICENSE_FILE", license_file, "config")
        self._add_env_from_json()

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
            raise RMSRuntimeError(
                "The RMS run did not produce the expected file: "
                f"{self.config.target_file}"
            )

        if self.config.target_file_mtime is None:
            return exit_status

        if os.path.getmtime(self.config.target_file) == self.config.target_file_mtime:
            raise RMSRuntimeError(
                f"The target file: {self.config.target_file} is unmodified - "
                "interpreted as failure"
            )
        return exit_status
