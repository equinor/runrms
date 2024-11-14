from __future__ import annotations

import json
import os
import stat
import subprocess
from unittest.mock import Mock

import pytest

from runrms.config import FMRMSConfig
from runrms.executor import FMRMSExecutor, RMSRuntimeError


def _create_config(
    iens: int,
    run_path: str,
    project: str,
    workflow: str,
    allow_no_env: bool,
    config_file: str,
    version: str = "14.2.2",
    target_file: str | None = None,
) -> FMRMSConfig:
    args = Mock()
    args.iens = iens
    args.run_path = run_path
    args.project = project
    args.workflows = [workflow]
    args.version = version
    args.readonly = False
    args.import_path = "import/path"
    args.export_path = "export/path"
    args.allow_no_env = allow_no_env
    args.target_file = target_file
    args.setup = config_file
    args.threads = 1

    config = FMRMSConfig(args)
    config._site_config.exe = f"{os.getcwd()}/bin/rms"
    return config


def test_run_class(fm_executor_env, capsys):
    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        config_file="runrms.yml",
    )
    rms = FMRMSExecutor(config)
    rms.run()

    # -----------------------------------------------------------------

    action = {"exit_status": 1}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    workflow_log = rms.config.run_path / "workflow.log"
    workflow_log.touch()
    rms_log = rms.config.run_path / "2024_RMS.log"
    rms_log.touch()

    assert rms.run() == 1
    captured = capsys.readouterr()
    assert "failed with exit status: 1. Typically this means" in captured.err
    assert f"* {workflow_log.resolve()}\n* {rms_log.resolve()}" in captured.err

    # -----------------------------------------------------------------

    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    with pytest.raises(RMSRuntimeError) as e:
        rms.run()
        assert e.match("target-file")

    # -----------------------------------------------------------------

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


@pytest.mark.parametrize(
    "val, carry_over",
    [
        ("    ", False),
        ("", False),
        (None, False),
        ("SOME_VAL", True),
    ],
)
def test_rms_load_nonempty_exec_env_values(val, carry_over, fm_executor_env):
    # This function is to be removed when exec_env support is dropped.
    rms_exec = "runrms"
    with open(f"{rms_exec}_exec_env.json", "w") as f:
        json.dump({"RMS_TEST_VAR": val}, f)

    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    subprocess.check_call(
        [
            rms_exec,
            "project",
            "--batch",
            "workflow",
            "--run-path",
            "run_path",
            "--iens",
            "0",
            "--version",
            "14.2.2",
            "--import-path",
            "./",
            "--export-path",
            "./",
            "--allow-no-env",
            "--setup",
            "runrms.yml",
        ]
    )

    with open("run_path/env.json") as f:
        env = json.load(f)

    if carry_over:
        assert "RMS_TEST_VAR" in env
    else:
        assert "RMS_TEST_VAR" not in env


def test_run_class_with_existing_target_file(fm_executor_env):
    target_file = os.path.join(fm_executor_env, "rms_target_file")
    action = {
        "exit_status": 0,
        "target_file": target_file,
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    with open(target_file, "w") as f:
        f.write("This is a dummy target file")

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        target_file=target_file,
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


def test_run_wrapper(fm_executor_env, monkeypatch, capsys):
    wrapper_file_name = f"{fm_executor_env}/bin/rms_wrapper"
    with open(wrapper_file_name, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("exec ${@:1}\n")
    st = os.stat(wrapper_file_name)
    os.chmod(wrapper_file_name, st.st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{fm_executor_env}/bin:{os.environ['PATH']}")

    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()
    assert rms.run() == 0

    # -----------------------------------------------------------------

    action = {"exit_status": 1}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    (rms.config.run_path / "workflow.log").touch()

    assert rms.run() == 1
    captured = capsys.readouterr()
    assert "failed with exit status: 1. Typically this means" in captured.err

    # -----------------------------------------------------------------

    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    with pytest.raises(RMSRuntimeError):
        rms.run()

    # -----------------------------------------------------------------

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    rms.run()


def test_run_version_env(test_env_wrapper, fm_executor_env, monkeypatch):
    wrapper_file_name = f"{fm_executor_env}/bin/rms_wrapper"
    with open(wrapper_file_name, "w") as f:
        rms_wrapper = test_env_wrapper(
            expected_path_prefix="/some/path",
            expected_pythonpath="/abc/pythonpath",
        )
        f.write(rms_wrapper)

    st = os.stat(wrapper_file_name)
    os.chmod(wrapper_file_name, st.st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fm_executor_env}/bin:{os.environ['PATH']}")

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=False,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


def test_pythonpath_carried_over_from_pre_env(
    test_env_wrapper, fm_executor_env, mocker, monkeypatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/abc/def")
    with open(f"{fm_executor_env}/bin/disable_foo", "w", encoding="utf-8") as f:
        disable_foo = test_env_wrapper(
            expected_path_prefix="/baz/bin:/foo/bin",
            expected_pythonpath="/abc/def",
            expected_lm_license_file="foo.lic",
        )
        f.write(disable_foo)
    with open("rms_exec_env.json", "w") as f:
        f.write(
            """\
{
    "PATH_PREFIX" : "/baz/bin",
    "PYTHONPATH" : "/baz/site-packages"
}
"""
        )
    mocker.patch("sys.argv", ["bin/rms"])

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=False,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()

    with open("run_path/env.json") as f:
        env = json.load(f)

    assert env["PYTHONPATH"] == "/baz/site-packages:/foo/bar/site-packages:/abc/def"


def test_run_version_env_with_user_env(
    test_env_wrapper, fm_executor_env, mocker
) -> None:
    """Tests that a user execution environment specific in rms_exec_env.json is
    prepended to the environment already given from the configuration."""
    with open(f"{fm_executor_env}/bin/disable_foo", "w", encoding="utf-8") as f:
        disable_foo = test_env_wrapper(
            expected_path_prefix="/baz/bin:/foo/bin",
        )
        f.write(disable_foo)
    with open("rms_exec_env.json", "w") as f:
        f.write(
            """\
{
    "PATH_PREFIX" : "/baz/bin",
    "PYTHONPATH" : "/baz/site-packages"
}
"""
        )
    mocker.patch("sys.argv", ["bin/rms"])

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=False,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


def test_user_rms_plugins_library_env_var_preferred(
    test_env_wrapper, fm_executor_env, mocker
) -> None:
    """Tests that if a user sets the RMS_PLUGINS_LIBRARY environment variable in their
    ERT configuration, it is preferred alone over the one in the site configuration."""
    with open(f"{fm_executor_env}/bin/disable_foo", "w", encoding="utf-8") as f:
        disable_foo = test_env_wrapper(
            expected_path_prefix="/baz/bin:/foo/bin",
        )
        f.write(disable_foo)
    with open("rms_exec_env.json", "w") as f:
        f.write(
            """\
{
    "PATH_PREFIX": "/baz/bin",
    "PYTHONPATH": "/baz/site-packages",
    "RMS_PLUGINS_LIBRARY": "/user/foo"
}
"""
        )
    mocker.patch("sys.argv", ["bin/rms"])

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=False,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


def test_run_allow_no_env(fm_executor_env, monkeypatch):
    monkeypatch.setenv("PATH", f"{fm_executor_env}/bin:{os.environ['PATH']}")

    action = {
        "exit_status": 0,
        "target_file": os.path.join(fm_executor_env, "some_file"),
    }
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=False,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    config._version_given = "non-existing"
    rms = FMRMSExecutor(config)
    with pytest.raises(RMSRuntimeError, match="non-existing"):
        rms.run()

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        version="14.2.2",
        target_file="some_file",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()


def test_rms_job_script_parser(fm_executor_env, monkeypatch):
    monkeypatch.setenv("RMS_TEST_VAR", "fdsgfdgfdsgfds")

    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    rms_exec = "runrms"
    subprocess.check_call(
        [
            rms_exec,
            "project",
            "--batch",
            "workflow",
            "--run-path",
            "run_path",
            "--iens",
            "0",
            "--version",
            "14.2.2",
            "--import-path",
            "./",
            "--export-path",
            "./",
            "--setup",
            "runrms.yml",
        ]
    )

    subprocess.check_call(
        [
            rms_exec,
            "project",
            "-batch",
            "workflow",
            "--run-path",
            "run_path",
            "--iens",
            "0",
            "--version",
            "14.2.2",
            "--allow-no-env",
            "--setup",
            "runrms.yml",
        ]
    )


@pytest.mark.parametrize("exit_status", [1, 2, 137])
def test_print_failure_when_no_logs_found_in_rms_model(
    exit_status, fm_executor_env, capsys
):
    action = {"exit_status": exit_status}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        config_file="runrms.yml",
    )
    rms = FMRMSExecutor(config)
    rms.run()

    assert rms.run() == exit_status
    captured = capsys.readouterr()
    assert f"failed with exit status: {exit_status}" in captured.err
    if exit_status == 137:
        assert (
            "This often means that the compute node ran out of memory" in captured.err
        )
    else:
        assert f"* {fm_executor_env}/run_path" in captured.err
        assert "This may mean that the compute node ran out of memory" in captured.err

    for line in captured.err.split("\n"):
        assert line.startswith("\t") is False


def test_print_failure_when_logs_found_in_rms_model(fm_executor_env, capsys):
    action = {"exit_status": 1}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        config_file="runrms.yml",
    )
    (fm_executor_env / "run_path" / "2025_RMS.log").touch()
    (fm_executor_env / "run_path" / "workflow.log").touch()

    rms = FMRMSExecutor(config)
    rms.run()

    assert rms.run() == 1
    captured = capsys.readouterr()
    print(captured.err)
    assert "failed with exit status: 1" in captured.err
    assert f"* {fm_executor_env}/run_path" in captured.err
    assert "workflow.log" in captured.err
    assert "2025_RMS.log" in captured.err

    for line in captured.err.split("\n"):
        assert line.startswith("\t") is False


def test_lm_license_server_overwritten_during_batch(fm_executor_env) -> None:
    action = {"exit_status": 0}
    with open("run_path/action.json", "w") as f:
        f.write(json.dumps(action))

    config = _create_config(
        iens=0,
        project="project",
        workflow="workflow",
        run_path="run_path",
        allow_no_env=True,
        version="14.2.2",
        config_file="runrms.yml",
    )

    rms = FMRMSExecutor(config)
    rms.run()

    with open("run_path/env.json") as f:
        env = json.load(f)

    assert env["LM_LICENSE_FILE"] == "/license/file.lic"
