import os
import pathlib
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
import yaml
from pytest import FixtureRequest, MonkeyPatch

from runrms.config import DEFAULT_CONFIG_FILE


@pytest.fixture(scope="session")
def source_root(request: FixtureRequest) -> Path:
    return request.config.rootpath


@pytest.fixture
def base_ert_rms_config() -> str:
    return dedent(
        r"""
        DEFINE <USER>               user
        DEFINE <SCRATCH>            $RUNRMS_TMP_PATH/scratch
        DEFINE <CASE_DIR>           snakeoil

        DEFINE <RMS_VERSION>        14.2.2
        DEFINE <RMS_NAME>           snakeoil.rms14.2.2

        NUM_REALIZATIONS 1

        QUEUE_SYSTEM LOCAL

        RANDOM_SEED 123456

        RUNPATH  <SCRATCH>/<USER>/<CASE_DIR>/realization-<IENS>/iter-<ITER>/

        FORWARD_MODEL RMS(<IENS>=<IENS>, <RMS_VERSION>=<RMS_VERSION>, <RMS_PROJECT>=<CONFIG_PATH>/../../rms/model/<RMS_NAME>)
    """  # noqa: E501
    )


@pytest.fixture
def fmu_snakeoil_project(
    tmp_path: Path, monkeypatch: MonkeyPatch, base_ert_rms_config: str
) -> None:
    """Makes a skeleton FMU project structure into a tmp_path, with a basic ERT config
    that can be appended onto."""
    monkeypatch.setenv("RUNRMS_TMP_PATH", str(tmp_path))

    os.makedirs(tmp_path / "eclipse/model")
    for app in ("ert", "rms"):
        os.makedirs(tmp_path / f"{app}/bin")
        os.makedirs(tmp_path / f"{app}/input")
        os.makedirs(tmp_path / f"{app}/model")
    os.makedirs(tmp_path / "ert/input/distributions")

    pathlib.Path(tmp_path / "ert/model/snakeoil.ert").write_text(
        base_ert_rms_config, encoding="utf-8"
    )


@pytest.fixture
def create_multi_seed_file(tmp_path: Path) -> Callable[[str], None]:
    """Returns a function for creating a multi seed file with the given content. The
    ert/input/distributions dir needs to already exist"""

    def _create_multi_seed_file(contents: str) -> None:
        pathlib.Path(tmp_path / "ert/input/distributions/random.seeds").write_text(
            contents
        )

    return _create_multi_seed_file


@pytest.fixture
def test_env_wrapper() -> Callable[..., str]:
    def _test_env_wrapper(
        expected_path_prefix: str = "/foo/bin",
        expected_pythonpath: str = "",
        expected_rms_plugins: str = "",
        expected_lm_license_file: str = "",
    ) -> str:
        return dedent(f"""
            #!/bin/bash
            PATH_PREFIX_EXPECTED={expected_path_prefix}
            if [[ $PATH_PREFIX != $PATH_PREFIX_EXPECTED ]]
            then
                echo "PATH_PREFIX set incorrectly"
                echo $PATH_PREFIX should be $PATH_PREFIX_EXPECTED
                exit 1
            fi
            PYPATH_EXPECTED={expected_pythonpath}
            if [[ $PYTHONPATH != $PYPATH_EXPECTED ]]
            then
                echo "PYTHONPATH set incorrectly"
                echo $PYTHONPATH should be $PYPATH_EXPECTED
                exit 1
            fi
            RMS_PLUGINS_LIBRARY_EXPECTED={expected_rms_plugins}
            if [[ $RMS_PLUGINS_LIBRARY != $RMS_PLUGINS_LIBRARY_EXPECTED ]]
            then
                echo "RMS_PLUGINS_LIBRARY set incorrectly"
                echo $RMS_PLUGINS_LIBRARY should be $RMS_PLUGINS_LIBRARY_EXPECTED
                exit 1
            fi
            LM_LICENSE_FILE_EXPECTED={expected_lm_license_file}
            if [[ $LM_LICENSE_FILE != $LM_LICENSE_FILE_EXPECTED ]]
            then
                echo "LM_LICENSE_FILE set incorrectly"
                echo $LM_LICENSE_FILE should be $LM_LICENSE_FILE_EXPECTED
                exit 1
            fi
            $@
        """).strip()

    return _test_env_wrapper


@pytest.fixture
def _env_setup(
    tmp_path: Path,
    source_root: Path,
    simple_runrms_yml: Callable[[str | Path], str],
    monkeypatch: MonkeyPatch,
) -> Path:
    os.chdir(tmp_path)
    os.mkdir("run_path")
    os.mkdir("bin")
    os.mkdir("project")

    path_master = Path("project/.master")
    Path(path_master).touch()
    with open(path_master, "w", encoding="utf-8") as f:
        f.write(master_version())

    shutil.copy(source_root / "tests/bin/rms", "bin")
    exe_path = f"{os.getcwd()}/bin"
    with open("runrms.yml", "w", encoding="utf-8") as f:
        f.write(simple_runrms_yml(exe_path))

    path = os.getenv("PATH", "")
    monkeypatch.setenv("PATH", os.pathsep.join([exe_path, path]))

    return tmp_path


@pytest.fixture
def executor_env(_env_setup: Path, test_env_wrapper: Callable[..., str]) -> Path:
    disable_foo = Path("bin/disable_foo")
    with open(disable_foo, "w", encoding="utf-8") as f:
        f.write(test_env_wrapper())
    disable_foo.chmod(disable_foo.stat().st_mode | stat.S_IEXEC)

    return _env_setup


@pytest.fixture
def fm_executor_env(
    _env_setup: Path, test_env_wrapper: Callable[..., str], monkeypatch: MonkeyPatch
) -> Path:
    """This sets LM_LICENSE_FILE to mock the way a wrapper might do so, either in the
    wrapper or the executable (which can be a wrapper). The forward model can set this
    environment variable to a different file or server, which can accomplish load
    balancing."""
    license_file_from_wrapper = "foo.lic"
    monkeypatch.setenv("LM_LICENSE_FILE", license_file_from_wrapper)
    disable_foo = Path("bin/disable_foo")
    with open(disable_foo, "w", encoding="utf-8") as f:
        f.write(test_env_wrapper(expected_lm_license_file=license_file_from_wrapper))
    disable_foo.chmod(disable_foo.stat().st_mode | stat.S_IEXEC)

    return _env_setup


@pytest.fixture
def default_config_file() -> dict[str, Any]:
    with open(DEFAULT_CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def simple_runrms_yml() -> Callable[[str | Path], str]:
    def _simple_runrms_yml(exe_path: str | Path) -> str:
        return dedent(f"""
            wrapper: disable_foo
            default: 14.2.2
            exe: {exe_path}/rms
            batch_lm_license_file: /license/file.lic
            env:
              PATH_PREFIX: /foo/bin
              RMS_IPL_ARGS_TO_PYTHON: 1

            versions:
              14.2.2:
                env:
                  PYTHONPATH: /foo/bar/site-packages
                  RMS_PLUGINS_LIBRARY: /foo/plugins
                  TCL_LIBRARY: /foo/tcl
                  TK_LIBRARY: /foo/tcl
          """)

    return _simple_runrms_yml


@pytest.fixture
def simple_runrms_config(
    simple_runrms_yml: Callable[[str | Path], str],
) -> dict[str, str]:
    return yaml.safe_load(simple_runrms_yml("."))


def master_version() -> str:
    return dedent(
        """
                Begin GEOMATIC file header
                release(1395)                           = 14.2.2
                End GEOMATIC file header
                """
    )
