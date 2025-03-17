from pathlib import Path
from typing import Self

from packaging.version import parse as version_parse
from pydantic import BaseModel, Field, model_validator


class Env(BaseModel):
    APS_TOOLBOX_PATH: str | None = Field(default=None)
    PYTHONPATH: str
    RMS_PLUGINS_LIBRARY: str
    TCL_LIBRARY: str
    TK_LIBRARY: str


class Version(BaseModel):
    """Information about different RMS versions."""

    env: Env


class GlobalEnv(BaseModel):
    """Top-level environment variables that are set for _all_ RMS versions."""

    PATH_PREFIX: str
    RMS_IPL_ARGS_TO_PYTHON: int = Field(default=1)
    LM_LICENSE_FILE: str | None = Field(default=None)


class SiteConfig(BaseModel):
    """
    Common config class for all RMSConfigs used by runrms
    """

    wrapper: str
    default: str
    exe: str
    interactive_usage_log: Path | None = Field(default=None)
    batch_lm_license_file: str | None = Field(default=None)
    env: GlobalEnv
    versions: dict[str, Version]

    def get_newest_patch_version(self, major: int, minor: int) -> int:
        latest = max(
            version_parse(v) for v in self.versions if v.startswith(f"{major}.{minor}")
        )
        _, _, patch = latest.release
        return patch

    @model_validator(mode="after")
    def default_version_exists_validator(self) -> Self:
        """Validates that the `default` provided actually exists as a key in
        `versions`."""
        try:
            self.versions[self.default]
        except KeyError as e:
            raise ValueError(
                f"Default RMS version {self.default} does not have a corresponding "
                "configuration."
            ) from e
        return self
