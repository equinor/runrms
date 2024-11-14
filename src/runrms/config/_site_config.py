from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from packaging.version import parse as version_parse
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

if TYPE_CHECKING:
    from pathlib import Path


class Env(BaseModel):
    APS_TOOLBOX_PATH: Optional[str] = Field(default=None)
    PYTHONPATH: str
    RMS_PLUGINS_LIBRARY: str
    TCL_LIBRARY: str
    TK_LIBRARY: str


class Version(BaseModel):
    """Information about different RMS versions."""

    restricted: bool = Field(default=False)
    env: Env


class GlobalEnv(BaseModel):
    """Top-level environment variables that are set for _all_ RMS versions."""

    PATH_PREFIX: str
    RMS_IPL_ARGS_TO_PYTHON: int = Field(default=1)
    LM_LICENSE_FILE: Optional[str] = Field(default=None)


class SiteConfig(BaseModel):
    """
    Common config class for all RMSConfigs used by runrms
    """

    wrapper: str
    default: str
    exe: str
    interactive_usage_log: Optional[Path] = Field(default=None)
    batch_lm_license_file: Optional[str] = Field(default=None)
    env: GlobalEnv
    versions: Dict[str, Version]

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
        except KeyError:
            raise ValueError(
                f"Default RMS version {self.default} does not have a corresponding "
                "configuration."
            )
        return self