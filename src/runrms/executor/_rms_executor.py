import os
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Generic, TypeVar

from runrms.config._rms_config import RmsConfig

ConfigType = TypeVar("ConfigType", bound=RmsConfig)


class RmsExecutionMode(StrEnum):
    """The modes RMS can execute in."""

    interactive = "interactive"
    batch = "batch"
    api = "api"


class RmsExecutor(ABC, Generic[ConfigType]):
    """
    Executor class which should be used by all runrms executors
    """

    def __init__(self, config: ConfigType) -> None:
        self._config = config
        self._exec_env = self._init_exec_env()

    def _init_exec_env(self) -> dict[str, str]:
        """Returns a dict containing the key, value environment variable pairs from the
        configuration. This merges the top-level global configuration for all RMS
        versions as well as the specific RMS version environment variables. The default
        behavior is to overwrite the global variable if a variable of the same name
        exists in the version configuration."""
        config_env = {
            k: str(v) for k, v in vars(self.config.global_env).items() if v is not None
        }
        version_env = {
            k: str(v) for k, v in vars(self.config.env).items() if v is not None
        }
        # Overwrite the global env if there are conflicts.
        config_env.update(version_env)
        config_env["RUNRMS_EXEC_MODE"] = self.exec_mode.value
        return config_env

    @property
    def config(self) -> ConfigType:
        return self._config

    def update_exec_env(self, key: str, val: str) -> None:
        """Updates the environment variable with name `key` in the
        execution environment of RMS with the value `val`."""

        # Do not update these variables.
        if key in ("RUNRMS_EXEC_MODE"):
            return

        # Path prepend these variables.
        if key in ("PATH", "LD_LIBRARY_PATH") and key in self._exec_env:
            self._exec_env[key] = f"{val}{os.pathsep}{self._exec_env[key]}"
            return

        self._exec_env[key] = val
        if not self._exec_env[key].strip():
            self._exec_env.pop(key)

    def pre_rms_args(self) -> list[str]:
        """The rms exec environement needs to be injected between executing the
        wrapper and launching rms. PATH_PREFIX must be set in advance."""
        prefix_path = self._exec_env.pop("PATH_PREFIX", "")
        env_args = ["env", *(f"{key}={value}" for key, value in self._exec_env.items())]
        return (
            ["env", f"PATH_PREFIX={prefix_path}", self.config.wrapper] + env_args
            if self.config.wrapper is not None
            else env_args
        )

    @property
    def exec_mode(self) -> RmsExecutionMode:
        """The mode a derived class is executing in."""
        raise NotImplementedError

    @abstractmethod
    def run(self) -> int:
        """Main executor function for running rms"""
        raise NotImplementedError
