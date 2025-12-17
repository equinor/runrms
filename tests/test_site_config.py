"""Tests the SiteConfig class, containing the user defined configuration."""

import pytest

from runrms.config._site_config import Env, GlobalEnv, SiteConfig, Version


@pytest.fixture
def site_config() -> SiteConfig:
    """Loads and return the site config object."""
    version = Version(
        env=Env(PYTHONPATH="", RMS_PLUGINS_LIBRARY="", TCL_LIBRARY="", TK_LIBRARY="")
    )
    return SiteConfig(
        wrapper="",
        default="2.2.0.0",
        exe="",
        env=GlobalEnv(PATH_PREFIX=""),
        versions={
            "1.1.0": version,
            "1.2.0": version,
            "1.2.1": version,
            "1.2.2": version,
            "1.2.3": version,
            "2.2.0.0": version,
            "2.2.0.1": version,
            "2.2.0.2": version,
            "2.2.1.0": version,
        },
    )


def test_get_newest_patch_version(site_config: SiteConfig) -> None:
    """Tests that getting the newest patch version works as expected."""
    assert site_config.get_newest_patch_version(1, 1) == 0
    assert site_config.get_newest_patch_version(1, 2) == 3


def test_get_newest_build_version(site_config: SiteConfig) -> None:
    """Tests that getting the newest build version works as expected."""
    assert site_config.get_newest_build_version(2, 2, 0) == 2
    assert site_config.get_newest_build_version(2, 2, 1) == 0
