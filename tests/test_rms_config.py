from __future__ import annotations

import os
import stat
from pathlib import Path
from textwrap import dedent

import pydantic
import pytest
import yaml

from runrms.__main__ import get_parser
from runrms.config import DEFAULT_CONFIG_FILE
from runrms.config._rms_config import (
    RMSConfig,
    RMSConfigNotFoundError,
    RMSExecutableError,
    RMSVersionError,
    RMSWrapperError,
    _load_site_config,
    _resolve_version,
)
from runrms.config._rms_project import RMSProject
from runrms.config._site_config import SiteConfig
from runrms.config.interactive_rms_config import InteractiveRMSConfig


def test_resolve_version(default_config_file) -> None:
    site_config = SiteConfig.model_validate(default_config_file)
    assert _resolve_version("14.2.1", site_config, None) == "14.2.1"
    assert _resolve_version("14.5.0", site_config, None) == "14.5.0"
    assert _resolve_version(None, site_config, None) == "14.2.2"

    with pytest.raises(
        RMSVersionError, match="RMS version '123.4.5' is not supported."
    ):
        _resolve_version("123.4.5", site_config, None)

    with pytest.raises(RMSVersionError, match="RMS version 'latest' is not supported."):
        _resolve_version("latest", site_config, None)


def test_resolve_version_from_project_master(default_config_file, executor_env):
    site_config = SiteConfig.model_validate(default_config_file)
    rms_project = RMSProject.from_filepath("project")
    version = _resolve_version(None, site_config, rms_project)
    assert version == "14.2.2"

    rms_project.master.version = "14.2.2"
    version = _resolve_version(None, site_config, rms_project)
    assert version == "14.2.2"

    rms_project.master.version = "10.0.0"
    with pytest.raises(
        RMSVersionError,
        match="RMS version '10.0.0' configured in the RMS project is not supported.",
    ):
        _resolve_version(None, site_config, rms_project)


@pytest.mark.parametrize(
    "config_location, raises",
    [
        ("/foo/bar", True),
        (f"{DEFAULT_CONFIG_FILE}.yml", True),
        (DEFAULT_CONFIG_FILE, False),
    ],
)
def test_load_site_config(config_location, raises) -> None:
    if not raises:
        _load_site_config(config_location)
    else:
        with pytest.raises(RMSConfigNotFoundError, match="Unable to locate"):
            _load_site_config(config_location)


def test_valid_config(simple_runrms_config) -> None:
    SiteConfig.model_validate(simple_runrms_config)


def test_invalid_default_version(simple_runrms_config) -> None:
    simple_runrms_config["default"] = "./foo"
    with pytest.raises(pydantic.ValidationError, match="Default RMS version"):
        SiteConfig.model_validate(simple_runrms_config)


def test_init_rmsconfig_default() -> None:
    with open(DEFAULT_CONFIG_FILE, encoding="utf-8") as f:
        config_yml = yaml.safe_load(f)
    config = RMSConfig()
    assert config.version == config_yml["default"]
    assert config.site_config.exe == config_yml["exe"]


def test_init_rmsconfig_default_version(default_config_file) -> None:
    config = RMSConfig()
    assert config.version == default_config_file["default"]
    assert str(config.site_config.exe) == default_config_file["exe"]
    assert (
        default_config_file["versions"][config.version]["env"]["PYTHONPATH"]
        == config.version_config.env.PYTHONPATH
    )


@pytest.mark.parametrize("version", ["14.2.2", "14.5.0"])
def test_init_rmsconfig_given_version(default_config_file, version) -> None:
    config = RMSConfig(version=version)
    assert config.version == version
    assert str(config.site_config.exe) == default_config_file["exe"]
    assert (
        default_config_file["versions"][config.version]["env"]["PYTHONPATH"]
        == config.version_config.env.PYTHONPATH
    )


def test_init_rmsconfig_nondefault_setup(
    tmp_path, simple_runrms_yml, simple_runrms_config
) -> None:
    """Tests that RMSConfig properly handles non-default runrms site configs."""
    runrms_yml = f"{tmp_path}/runrms.yml"
    with open(runrms_yml, "w", encoding="utf-8") as f:
        f.write(simple_runrms_yml("."))

    config = RMSConfig(config_path=runrms_yml)
    assert config.version == "14.2.2"
    assert str(config.site_config.exe) == simple_runrms_config["exe"]
    assert (
        simple_runrms_config["versions"][config.version]["env"]["PYTHONPATH"]
        == config.version_config.env.PYTHONPATH
    )


def test_rmsconfig_get_executable(
    tmp_path,
    monkeypatch,
    simple_runrms_yml,
) -> None:
    """Tests that the wrapper functions correctly."""
    monkeypatch.chdir(tmp_path)
    exe_path = tmp_path / "bin"
    with open("runrms.yml", "w", encoding="utf-8") as f:
        f.write(simple_runrms_yml(exe_path))
    config = RMSConfig(config_path="runrms.yml")
    with pytest.raises(RMSExecutableError, match=f"{exe_path}/rms cannot be found"):
        _ = config.executable

    os.mkdir("bin")
    with open("bin/rms", "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\necho 1")

    with pytest.raises(RMSExecutableError, match=f"{exe_path}/rms cannot be found"):
        _ = config.executable

    os.chmod("bin/rms", stat.S_IEXEC)
    assert config.executable == f"{exe_path}/rms"


def test_rmsconfig_get_wrapper(
    tmp_path,
    monkeypatch,
    simple_runrms_yml,
) -> None:
    """Tests that the wrapper functions correctly."""
    monkeypatch.chdir(tmp_path)
    with open("runrms.yml", "w", encoding="utf-8") as f:
        f.write(simple_runrms_yml(tmp_path))
    config = RMSConfig(config_path="runrms.yml")
    with pytest.raises(RMSWrapperError, match="disable_foo cannot be found"):
        _ = config.wrapper

    disable_foo = Path("disable_foo")
    with open(disable_foo, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n")
    disable_foo.chmod(disable_foo.stat().st_mode | stat.S_IEXEC)

    path = os.getenv("PATH", "")
    monkeypatch.setenv("PATH", f"{path}{os.pathsep}{os.getcwd()}")

    assert config.wrapper == "disable_foo"


def test_rmsconfig_get_env(
    tmp_path,
    monkeypatch,
    simple_runrms_yml,
) -> None:
    """Tests that the wrapper functions correctly."""
    monkeypatch.chdir(tmp_path)
    with open("runrms.yml", "w", encoding="utf-8") as f:
        f.write(simple_runrms_yml(tmp_path))
    config = RMSConfig(config_path="runrms.yml")
    assert config.global_env.PATH_PREFIX == "/foo/bin"
    assert config.env.PYTHONPATH == "/foo/bar/site-packages"


@pytest.mark.parametrize(
    "project_version, master_version, expected_version",
    [
        ("14.2.2", "14.2.2", "14.2.2"),
        ("14.5.0", "14.2.2", "14.2.2"),
        ("14.2.1", "V14.2", "14.2.2"),
        ("14.2.2", "V14.2", "14.2.2"),
        ("14.2.1", "V14.2", "14.2.2"),
        ("14.5.0", "V14.5", "14.5.0"),
    ],
)
def test_rmsconfig_with_v14_from_master_resolves_to_latest_patch(
    project_version,
    master_version,
    expected_version,
    tmp_path,
    monkeypatch,
) -> None:
    """Tests that if the .master file does not contain a patch version, as is the case
    in RMS 14.1, it will default to resolving to the latest patch version rather than
    the 0 default version. This test must be updated whenever a new RMS 14.2.x patch
    version is added."""
    monkeypatch.chdir(tmp_path)

    project = f"drogon.{project_version}"
    os.mkdir(project)
    with open(f"{project}/.master", "w", encoding="utf-8") as f:
        f.write(
            dedent(
                f"""
        Begin GEOMATIC file header
        date(1395)                              = 2022.09.08
        time(1395)                              = 10:58:55
        user(1395)                              = user
        release(1395)                           = {master_version}
        operation(1395)                         = Save
        description(1395)                       =
        branch(1395)                            = 14_0
        build(1395)                             = 833
        variant(1395)                           = linux-amd64-gcc_4_8-release
        elements                                = 29
        filetype                                = BINARY
        fileversion                             = 2021.0000
        End GEOMATIC file header
        """
            )
        )

    args = get_parser().parse_args([project])
    config = InteractiveRMSConfig(args)
    assert config.version == expected_version
