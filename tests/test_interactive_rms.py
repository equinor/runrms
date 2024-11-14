"""Test runrms script, but manual interactive testing is also needed."""

from __future__ import annotations

import datetime
import getpass
import os
import socket
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from runrms.__main__ import get_parser
from runrms.config import DEFAULT_CONFIG_FILE, InteractiveRMSConfig
from runrms.executor import InteractiveRMSExecutor

TESTRMS1 = "tests/testdata/rms/drogon.rms12.0.2"
TESTRMS2 = "tests/testdata/rms/drogon.rms13.0.3"


def test_config_init_no_project():
    args = get_parser().parse_args(["--dryrun", "--setup", DEFAULT_CONFIG_FILE])
    config = InteractiveRMSConfig(args)
    assert config.project is None
    assert config.dryrun is True
    assert config.site_config_file == DEFAULT_CONFIG_FILE


@pytest.mark.parametrize("project", [TESTRMS1, TESTRMS2])
def test_config_init_projects(source_root, project):
    project_str = str(source_root / project)
    args = get_parser().parse_args(
        [project_str, "--dryrun", "--setup", DEFAULT_CONFIG_FILE]
    )
    config = InteractiveRMSConfig(args)
    assert config.project.path == source_root / project
    assert config.dryrun is True
    assert config.site_config_file == DEFAULT_CONFIG_FILE


@pytest.mark.integration
def test_integration():
    """Test that the endpoint is installed."""
    assert subprocess.check_output(["runrms", "-h"])


def test_rms_version_from_project(source_root, tmp_path):
    """Scan master files in RMS."""
    os.chdir(tmp_path)
    args = get_parser().parse_args([str(source_root / TESTRMS1)])
    config = InteractiveRMSConfig(args)
    assert config.project.master.version == "12.0.2"


def test_runlogger_writes_to_configured_usage_log(source_root, tmp_path):
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
    config = InteractiveRMSConfig(args)
    executor = InteractiveRMSExecutor(config)
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


@pytest.mark.xfail(reason="The executable disable_komodo_exec is not available")
def test_runrms_disable_komodo_exec(tmp_path, monkeypatch):
    """Testing integration with Komodo."""
    os.chdir(tmp_path)
    Path("rms_fake").write_text(
        """\
#!/usr/bin/env python3
import os
import sys

errors = []

BACKUPS_check=set([
    "PATH",
    "KOMODO_RELEASE",
    "MANPATH",
    "LD_LIBRARY_PATH",
    "PYTHONPATH"
])
BACKUPS = set(os.environ["BACKUPS"].split(":"))

if BACKUPS != BACKUPS_check:
    errors.append(f"BACKUP error: {BACKUPS} not equal to {BACKUPS_check}")

for backup in BACKUPS:
    if f"{backup}_BACKUP" not in os.environ:
        errors.append(f"The backup for {backup} is not set")

PATH = os.environ["PATH"]
PATH_PREFIX = os.environ["PATH_PREFIX"]
if PATH.split(":")[0] != PATH_PREFIX:
    errors.append(f"PATH_PREFIX ({PATH_PREFIX}), was not prepended to PATH ({PATH})")
if PATH_PREFIX != "/some/bin/path":
    errors.append(f"The path for run_external is not corrent {PATH_PREFIX}")

if "KOMODO_RELEASE" in os.environ:
    errors.append(f"komodo release set: {os.environ['KOMODO_RELEASE']}")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)
sys.exit(0)
"""
    )

    st = os.stat("rms_fake")
    os.chmod("rms_fake", st.st_mode | stat.S_IEXEC)
    monkeypatch.setenv("KOMODO_RELEASE", f"{os.getcwd()}/bleeding")
    monkeypatch.setenv("_PRE_KOMODO_MANPATH", "some/man/path")
    monkeypatch.setenv("_PRE_KOMODO_LD_LIBRARY_PATH", "some/ld/path")

    args = get_parser().parse_args(["-v", "13.0.3"])
    config = InteractiveRMSConfig(args)

    config.path_prefix = "/some/bin/path"
    config.version_requested = "13.0.3"
    config.exe = "./rms_fake"
    config.pythonpath = ""
    config.pluginspath = "rms/plugins/path"

    executor = InteractiveRMSExecutor(config)

    return_code = executor.run()
    assert return_code == 0
