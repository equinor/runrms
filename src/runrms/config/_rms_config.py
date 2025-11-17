import logging
import os
import shutil
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Final

import yaml
from packaging.version import parse as version_parse

from runrms.exceptions import (
    RmsConfigNotFoundError,
    RmsExecutableError,
    RmsVersionError,
    RmsWrapperError,
)

from ._rms_project import RmsProject
from ._site_config import Env, GlobalEnv, SiteConfig, Version

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_FILE: Final = os.path.join(os.path.dirname(__file__), "runrms.yml")
DEFAULT_VERSION: Final = "DEFAULT"


def _detect_os() -> str:
    """Detect operating system string in runtime. Use default if not found."""

    default_os_version = "x86_64_RH_8"
    release_file = Path("/etc/redhat-release")
    if release_file.is_file():
        with open(release_file, encoding="utf-8") as f:
            tokens = f.read().split()
            for t in tokens:
                if "." in t:
                    major = t.split(".")[0]
                    osver = f"x86_64_RH_{major}"
                    logger.debug(f"RHEL version {osver} found in {release_file}")
                    return osver
        raise ValueError("Could not detect RHEL version")
    return default_os_version


def _load_site_config(site_config_file: str) -> SiteConfig:
    if not os.path.exists(site_config_file):
        raise RmsConfigNotFoundError(
            f"Unable to locate config file for rms\n{site_config_file} does not exist!"
        )
    with open(site_config_file) as f:
        config = yaml.safe_load(f)
    return SiteConfig.model_validate(config)


def _resolve_version(
    version: str | None, site_config: SiteConfig, rms_project: RmsProject | None
) -> str:
    if version:
        if version in site_config.versions:
            return version
        raise RmsVersionError(
            f"RMS version '{version}' is not supported. "
            "To see the supported versions, run `rms -l` or `runrms -l`."
        )
    if rms_project:
        if rms_project.master.version in site_config.versions:
            master_version = version_parse(rms_project.master.version)
            major = master_version.major
            minor = master_version.minor

            # Handle RMS 14.2 specially as it stores no patch version internally.
            if major == 14 and minor <= 2:
                newest_patch = site_config.get_newest_patch_version(major, minor)
                return f"{major}.{minor}.{newest_patch}"

            return rms_project.master.version

        raise RmsVersionError(
            f"RMS version '{rms_project.master.version}' "
            "configured in the RMS project is not supported. "
            "To see the supported versions, run `rms -l` or `runrms -l`."
        )

    return site_config.default


class RmsConfig:
    """
    Common config class for all RmsConfigs used by runrms
    """

    def __init__(
        self,
        *,
        config_path: str | None = None,
        version: str | None = None,
        project: str | None = None,
    ) -> None:
        super().__init__()
        self._osver = _detect_os()

        self._site_config_file = self._set_config_file(config_path)
        self._site_config = _load_site_config(self._site_config_file)
        self._project = RmsProject.from_filepath(project) if project else None

        self._version_given = version
        self._version = _resolve_version(version, self._site_config, self._project)
        self._version_config = self._site_config.versions[self._version]

    def _set_config_file(self, config_path: str | None) -> str:
        """Determines which configuration file to use.

        Starts with the one included within this package, then looks for any exposed by
        a runrms entry point, and finally prefers one given by '--setup'."""
        config_file = DEFAULT_CONFIG_FILE

        entry_points = importlib_metadata.entry_points()
        # Python 3.12 does not implement __iter__ on this object.
        selections = entry_points.select(group="runrms", name="config_path")
        if selections:
            runrms_config_path, *_ = selections
            config_file = runrms_config_path.load()()

        # Override if given from --setup
        if config_path:
            config_file = config_path

        return str(config_file)

    @property
    def osver(self) -> str:
        return self._osver

    @property
    def site_config_file(self) -> str:
        return self._site_config_file

    @property
    def site_config(self) -> SiteConfig:
        return self._site_config

    @property
    def project(self) -> RmsProject | None:
        return self._project

    @property
    def version_given(self) -> str | None:
        return self._version_given

    @property
    def version(self) -> str:
        return self._version

    @property
    def version_config(self) -> Version:
        return self._version_config

    @property
    def executable(self) -> str:
        """RMS executable, assert if permissions are correct"""
        exe = self._site_config.exe
        if shutil.which(exe) is None:
            raise RmsExecutableError(f"The executable: {exe} cannot be found")
        if not os.access(exe, os.X_OK):
            raise RmsExecutableError(
                f"The executable: {exe} cannot be run (invalid access)"
            )
        return exe

    @property
    def wrapper(self) -> str:
        """wrapper executable, assert if permissions are correct"""
        exe = self._site_config.wrapper
        if shutil.which(exe) is None:
            raise RmsWrapperError(f"The executable: {exe} cannot be found")
        return exe

    @property
    def global_env(self) -> GlobalEnv:
        return self._site_config.env

    @property
    def env(self) -> Env:
        """Environment given by the config file"""
        return self._version_config.env

    @property
    def threads(self) -> int:
        """Number of threads to use in RMS. Defaults to one, the recommended number in
        batch mode."""
        return 1
