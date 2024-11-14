from __future__ import annotations

import os
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from runrms.config import FMRMSConfig, InteractiveRMSConfig


class RMSRuntimeError(Exception):
    """
    Custom error for run-time errors
    """


class RMSExecutor(ABC):
    """
    Executor class which should be used by all runrms executors
    """

    def __init__(self, config: InteractiveRMSConfig | FMRMSConfig) -> None:
        self._config = config

        # We want to append to or carry forward the following env vars
        pre_env = {}
        pre_env["PYTHONPATH"] = os.environ.get("PYTHONPATH", None)
        pre_env["RMS_PLUGINS_LIBRARY"] = os.environ.get("RMS_PLUGINS_LIBRARY", None)
        self._pre_env = {k: v for k, v in pre_env.items() if v}
        self._exec_env: dict[str, str]

        super().__init__()

    @property
    def config(self) -> InteractiveRMSConfig | FMRMSConfig:
        return self._config

    @property
    def pre_env(self) -> dict[str, str]:
        """Returns a dict containing a few specific environment variables we will
        carry forward from before execution."""
        return deepcopy(self._pre_env)

    def _initialize_exec_env_from_config(self) -> None:
        """Initializes the environment variables for the
        execution environment of RMS."""
        self._exec_env = self.pre_env
        config_env = self._config_env()
        for key, val in config_env.items():
            self._update_exec_env(key, val, "config")

    def _update_exec_env(
        self, key: str, val: str, val_origin: Literal["config", "json", "test_config"]
    ) -> None:
        """Updates the environment variable with name `key` in the
        execution environment of RMS with the value `val`.
        Depending on the environment variable to update and the origin of `val`,
        the entry will be updated in different ways. If the key does not match any
        of the keys that needs special handling, the default case will add the value
        to the front of the existing search path.
        """
        # TODO: Replace if/elif pattern below with a match case
        # when all RMS versions support Python 3.10
        if key == "RMS_PLUGINS_LIBRARY":
            if val_origin == "json":
                self._exec_env[key] = val
            elif val_origin == "config":
                if self._exec_env.get(key):
                    return
                self._exec_env[key] = val
            elif val_origin == "test_config" and self._exec_env.get(key):
                self._exec_env[key] = val
                return
        elif key == "LM_LICENSE_FILE":
            self._exec_env[key] = val
        elif key == "QT_SCALE_FACTOR":
            self._exec_env[key] = str(val)
        else:
            # assert this is a PATH thing...
            if key in self._exec_env:
                self._exec_env[key] = f"{val}{os.pathsep}{self._exec_env[key]}"
            else:
                self._exec_env[key] = str(val)
            if not self._exec_env[key].strip():
                self._exec_env.pop(key)

    def _config_env(self) -> dict[str, str]:
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
        return config_env

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

    @abstractmethod
    def run(self) -> int:
        """Main executor function for running rms"""
        raise NotImplementedError
