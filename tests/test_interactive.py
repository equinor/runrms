"""Test runrms script, but manual interactive testing is also needed."""

import datetime
import getpass
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
import yaml
from pytest import MonkeyPatch

from runrms.__main__ import get_parser
from runrms.config import DEFAULT_CONFIG_FILE, InteractiveConfig
from runrms.executor import InteractiveExecutor

TESTRMS1 = "tests/testdata/rms/drogon.rms12.0.2"
TESTRMS2 = "tests/testdata/rms/drogon.rms13.0.3"


def test_config_init_no_project() -> None:
    args = get_parser().parse_args(["--dryrun", "--setup", DEFAULT_CONFIG_FILE])
    config = InteractiveConfig(args)
    assert config.project is None
    assert config.dryrun is True
    assert config.site_config_file == DEFAULT_CONFIG_FILE


@pytest.mark.parametrize("project", [TESTRMS1, TESTRMS2])
def test_config_init_projects(source_root: Path, project: str) -> None:
    project_str = str(source_root / project)
    args = get_parser().parse_args(
        [project_str, "--dryrun", "--setup", DEFAULT_CONFIG_FILE]
    )
    config = InteractiveConfig(args)
    assert config.project is not None
    assert config.project.path == source_root / project
    assert config.dryrun is True
    assert config.site_config_file == DEFAULT_CONFIG_FILE


@pytest.mark.integration
def test_integration() -> None:
    """Test that the endpoint is installed."""
    assert subprocess.check_output(["runrms", "-h"])


def test_rms_version_from_project(source_root: Path, tmp_path: Path) -> None:
    """Scan master files in RMS."""
    os.chdir(tmp_path)
    args = get_parser().parse_args([str(source_root / TESTRMS1)])
    config = InteractiveConfig(args)
    assert config.project is not None
    assert config.project.master.version == "12.0.2"


def test_runlogger_writes_to_configured_usage_log(
    source_root: Path, tmp_path: Path
) -> None:
    """Tests that the 'interactive_usage_log' site configuration options works."""
    os.chdir(tmp_path)
    runrms_usage = Path(tmp_path / "runrms_usage.log").resolve()
    runrms_usage.touch()

    with open(DEFAULT_CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["interactive_usage_log"] = str(runrms_usage)
    # Just allow these to be resolved, not relevant to test.
    config["wrapper"] = "/bin/echo"
    config["exe"] = "/bin/echo"

    with open(tmp_path / "runrms.yml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)

    args = get_parser().parse_args(
        [str(source_root / TESTRMS1), "--setup", f"{tmp_path}/runrms.yml"]
    )
    config = InteractiveConfig(args)
    executor = InteractiveExecutor(config)
    executor._exec_rms()
    executor.runlogger()
    with open(runrms_usage, encoding="utf-8") as f:
        log_lines = f.readlines()
    assert len(log_lines) == 1

    log = log_lines[0].rstrip().split(",")
    assert log[0] == datetime.datetime.now().strftime("%Y-%m-%d")
    # Skip wall time
    assert log[2] == getpass.getuser()
    assert log[3] == socket.gethostname()
    assert log[4] == "client"
    assert log[5] == "/bin/echo"
    assert log[6] == f"/bin/echo -v 12.0.2 -project {source_root / TESTRMS1}"

    # Ensure it appends
    executor.runlogger()
    with open(runrms_usage, encoding="utf-8") as f:
        log_lines = f.readlines()
    assert len(log_lines) == 2


def test_interactive_run(
    tmp_path: Path, monkeypatch: MonkeyPatch, source_root: Path
) -> None:
    """Testing integration with Komodo."""
    os.chdir(tmp_path)
    shutil.copy(source_root / "tests/bin/rms", tmp_path)

    action = {"exit_status": 0}
    with open("action.json", "w") as f:
        f.write(json.dumps(action))

    args = get_parser().parse_args(["-v", "14.2.2"])
    with (
        patch.object(
            InteractiveConfig,
            "wrapper",
            new_callable=PropertyMock,
            return_value="REPLACE_WRAPPER_WITH=env_var",
        ),
        patch.object(
            InteractiveConfig,
            "executable",
            new_callable=PropertyMock,
            return_value=str(tmp_path / "rms"),
        ),
    ):
        config = InteractiveConfig(args)
        executor = InteractiveExecutor(config)
        assert executor.run() == 0

    with open("env.json") as f:
        env = json.load(f)

    assert env["RUNRMS_EXEC_MODE"] == "interactive"
