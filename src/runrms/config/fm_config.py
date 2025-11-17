import argparse
import logging
import os
import random
from pathlib import Path

from runrms.exceptions import RmsRuntimeError

from ._rms_config import RmsConfig
from ._rms_project import RmsProject

logger = logging.getLogger(__name__)

description = """
Forward model for running a given workflow in an existing RMS-project.

The forward model requires explicit knowledge of the version used to
produce the RMS project loaded. The Python environment is adapted to
work with Python inside RMS.

As part of the configuration there can be a file holding a list of random seeds:
``ert/input/distributions/random.seeds``. This file needs to have a specific format,
containing one number per line, with each number being unique within the file. In
addition, the first line of the file needs to have a count of the numbers in the file.
If there are 1000 unique numbers in the file, the first line will show 1000, and the
total number of lines in the file will be 1001.
"""

examples = """
Running the forward model
#########################

RMS is usually incorporated in ERT configurations using statements like

.. code-block:: bash

    DEFINE  <RMS_PROJECT>         reek.rms11.0.1
    DEFINE  <RMS_VERSION>         11.0.1
    DEFINE  <RMS_WORKFLOW_NAME>   MAIN_WORKFLOW
    FORWARD_MODEL RMS(<IENS>=<IENS>, <RMS_VERSION>=<RMS_VERSION>, <RMS_PROJECT>=<CONFIG_PATH>/../../rms/model/<RMS_NAME>)
"""  # noqa

category = "modelling.reservoir"


class ForwardModelConfig(RmsConfig):
    """A class which holds the nessecary configuration for executing
    runrms as a forward model.
    """

    project: RmsProject

    _single_seed_file = "RMS_SEED"
    _multi_seed_file = "random.seeds"
    _max_seed = 2146483648
    _seed_factor = 7907

    def __init__(self, args: argparse.Namespace) -> None:
        if not args.project:
            raise RmsRuntimeError(
                "A project must be specified to run the RMS forward model."
            )
        super().__init__(
            config_path=args.setup, version=args.version, project=args.project
        )
        self._iens = args.iens
        self._threads = args.threads
        self._workflow = args.workflow

        self._run_path = Path(args.run_path)
        self._import_path = Path(args.import_path)
        self._export_path = Path(args.export_path)
        self._allow_no_env = args.allow_no_env

        self._seed = (
            self._get_seed_from_env()
            if "RMS_SEED" in os.environ
            else self._read_seed_from_file(self._iens)
        ) % self._max_seed

        self._target_file = None
        self._target_file_mtime = None
        if args.target_file:
            self._target_file = Path(
                args.target_file
                if os.path.isabs(args.target_file)
                else os.path.join(os.getcwd(), args.target_file)
            )
            self._target_file_mtime = (
                os.path.getmtime(args.target_file)
                if os.path.isabs(args.target_file)
                else None
            )

    @property
    def allow_no_env(self) -> Path:
        return self._allow_no_env

    @property
    def run_path(self) -> Path:
        return self._run_path

    @property
    def import_path(self) -> Path:
        return self._import_path

    @property
    def export_path(self) -> Path:
        return self._export_path

    @property
    def target_file(self) -> Path | None:
        return self._target_file

    @property
    def target_file_mtime(self) -> float | None:
        return self._target_file_mtime

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def threads(self) -> int:
        return self._threads

    @property
    def workflow(self) -> str:
        return self._workflow

    def _get_seed_from_env(self) -> int:
        try:
            env_seed = os.environ.get("RMS_SEED", "")
            seed = int(env_seed)
        except ValueError as e:
            raise ValueError(
                f"The 'RMS_SEED' environment variable is set to {env_seed} which "
                "cannot be converted into an integer."
            ) from e

        for _ in range(self._iens):
            seed *= self._seed_factor
        return seed

    def _read_seed_from_file(self, iens: int) -> int:
        single_seed_file = self.run_path / self._single_seed_file
        multi_seed_file = self.run_path / self._multi_seed_file

        if single_seed_file.exists():
            # Using existing single seed file
            with open(single_seed_file) as file_handle:
                seed_list = [line.rstrip() for line in file_handle]
                self._validate_seed_source(seed_list, single_seed_file, False, iens)
                seed = int(seed_list[0])
        elif multi_seed_file.exists():
            with open(multi_seed_file) as file_handle:
                seed_list = [line.rstrip() for line in file_handle]
                self._validate_seed_source(seed_list, multi_seed_file, True, iens)
                seed = int(seed_list[self._iens + 1])
        else:
            random.seed()
            seed = random.randint(0, ForwardModelConfig._max_seed)
        return seed

    @staticmethod
    def _pre_experiment_validation(
        num_realizations: int | None = None,
    ) -> tuple[bool, ValueError | None]:
        seed_path = Path(os.getcwd(), "../input/distributions")
        single_seed_file = seed_path / ForwardModelConfig._single_seed_file
        multi_seed_file = seed_path / ForwardModelConfig._multi_seed_file
        iens_max = num_realizations - 1 if num_realizations is not None else None

        try:
            if single_seed_file.exists():
                with open(single_seed_file) as file_handle:
                    seed_list = [line.rstrip() for line in file_handle]
                    ForwardModelConfig._validate_seed_source(
                        seed_list, single_seed_file, False, iens_max
                    )
            elif multi_seed_file.exists():
                with open(multi_seed_file) as file_handle:
                    seed_list = [line.rstrip() for line in file_handle]
                    ForwardModelConfig._validate_seed_source(
                        seed_list, multi_seed_file, True, iens_max
                    )
        except ValueError as err:
            return False, err
        return True, None

    @staticmethod
    def _validate_seed_source(  # noqa: PLR0913
        lines: list[str],
        filename: Path,
        is_multi: bool,
        iens_max: int | None = None,
        validate_given_number_count: bool = False,
        validate_unique_values: bool = False,
    ) -> None:
        file_desc = "Multi seed file" if is_multi else "Single seed file"
        file_desc += f" {filename.absolute()}"
        single_format_desc = "The file must contain one number"
        multi_format_desc = (
            "The file contents must be unique numbers, one per line. "
            "The first line must have a count of the total numbers in "
            "the file, excluding the count value itself"
        )
        format_desc = multi_format_desc if is_multi else single_format_desc

        line_count = len(lines)
        if line_count == 0:
            raise ValueError(f"{file_desc} is empty. {format_desc}")
        for line in lines:
            if not line.isdigit():
                raise ValueError(
                    f"{file_desc} contains non-number values. {format_desc}"
                )
        if not is_multi:
            if line_count > 1:
                raise ValueError(
                    f"{file_desc} contains multiple seed values. {format_desc}"
                )
            return

        given_number_count = int(lines[0])
        numbers = lines[1:]
        actual_number_count = len(numbers)
        if validate_given_number_count and given_number_count != actual_number_count:
            raise ValueError(
                f"{file_desc} has an incorrect number count value in line 1, "
                f"expected {actual_number_count} but found {given_number_count}. "
                f"{format_desc}"
            )
        if actual_number_count == 0:
            raise ValueError(f"{file_desc} has no seed values. {format_desc}")
        if validate_unique_values and actual_number_count != len(set(numbers)):
            raise ValueError(
                f"{file_desc} contains non-unique seed values. {format_desc}"
            )
        if iens_max is not None and actual_number_count <= iens_max:
            raise ValueError(
                f"{file_desc} has too few seed values ({actual_number_count}) "
                f"for the needed realization number ({iens_max + 1})"
            )
