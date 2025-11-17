import pytest

from runrms.api.worker import ApiWorker
from runrms.config import ApiConfig


def test_config_requires_rms_version() -> None:
    """Tests initializing the ApiConfig."""
    with pytest.raises(ValueError, match="RMS version must"):
        ApiConfig()


def test_config_has_wrapper() -> None:
    """Ensure the wrapper is just python."""
    cfg = ApiConfig(version="14.2.2")
    assert cfg.wrapper == "python"


def test_config_executable_is_worker_path() -> None:
    """Ensure the wrapper is just python."""
    cfg = ApiConfig(version="14.2.2")
    assert cfg.executable == str(ApiWorker.script_path)
