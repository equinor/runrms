from __future__ import annotations

from pathlib import Path


def runrms_config_path() -> Path:
    """Returns the absolute path to runrms.yml."""
    return (Path(__file__).parent / "runrms.yml").resolve()
