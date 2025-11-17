"""Configuration for RMS API mode."""

from runrms.api.worker import ApiWorker

from ._rms_config import RmsConfig


class ApiConfig(RmsConfig):
    """Configuration for launching RMS in API mode."""

    def __init__(
        self,
        *,
        config_path: str | None = None,
        version: str | None = None,
        project: str | None = None,
    ) -> None:
        """Initializes API RMS configuration."""
        if version is None:
            raise ValueError("RMS version must be specified for API mode.")

        super().__init__(
            config_path=config_path,
            version=version,
            project=project,
        )

    @property
    def wrapper(self) -> str:
        """Wrapper executable. In this case, just 'python'."""
        return "python"

    @property
    def executable(self) -> str:
        return str(ApiWorker.script_path)
