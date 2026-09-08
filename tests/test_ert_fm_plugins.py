import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

try:
    from ert import (  # type: ignore[import-untyped]
        ForwardModelStepJSON,
        ForwardModelStepValidationError,
    )
    from ert.plugins.plugin_manager import ErtPluginManager  # type: ignore
except ImportError:
    pytest.skip(
        "Not testing ERT plugins when ERT is not installed", allow_module_level=True
    )

import runrms._forward_model as ert_plugins
from runrms.__main__ import get_parser
from runrms._forward_model import Rms

EXPECTED_JOBS = {"RMS"}


@pytest.mark.requires_ert
def test_rms_opts_invalid_quotes() -> None:
    job = cast("ForwardModelStepJSON", {"argList": ["project.rms", "--setup 'open"]})
    with pytest.raises(ForwardModelStepValidationError, match="Invalid RMS_OPTS"):
        Rms().validate_pre_realization_run(job)


@pytest.mark.requires_ert
def test_that_installable_fm_steps_work_as_plugins() -> None:
    """Test that the forward models are included as ERT plugin."""
    fms = ErtPluginManager(plugins=[ert_plugins]).forward_model_steps

    assert Rms in fms
    assert len(fms) == len(EXPECTED_JOBS)


@pytest.mark.requires_ert
def test_fm_plugin_implementations() -> None:
    """Test hook implementation."""
    ert_pm = ErtPluginManager(plugins=[ert_plugins])

    installable_fm_step_jobs = [fms().name for fms in ert_pm.forward_model_steps]
    assert set(installable_fm_step_jobs) == set(EXPECTED_JOBS)

    installable_workflow_jobs = ert_pm.get_installable_workflow_jobs()
    assert len(installable_workflow_jobs) == 0


@pytest.mark.requires_ert
@pytest.mark.integration
def test_fm_plugin_executables() -> None:
    """Test executables in the configured ert forward models."""
    ert_pm = ErtPluginManager(plugins=[ert_plugins])
    for fm_step in ert_pm.forward_model_steps:
        assert shutil.which(fm_step().executable)


@pytest.mark.requires_ert
def test_fm_plugin_docs() -> None:
    """For each installed forward model, we require the associated
    description and example string to be nonempty,
    and the category to be as expected"""

    ert_pm = ErtPluginManager([ert_plugins])
    for fm_step in ert_pm.forward_model_steps:
        docs = fm_step.documentation()
        assert docs.description is not None
        assert docs.examples is not None
        assert "RMS" in docs.description
        assert "FORWARD_MODEL RMS" in docs.examples
        assert docs.category == "modelling.reservoir"


@pytest.mark.requires_ert
@pytest.mark.parametrize(
    ("num_cpu", "rms_opts", "expected_threads"),
    [
        (None, "", 1),
        (4, "", 4),
        (4, "--threads 2", 2),
        (4, "--threads 2 --export-path 'path with spaces'", 2),
    ],
)
def test_rms_forward_model_ok(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    fmu_snakeoil_project: None,
    num_cpu: int | None,
    rms_opts: str,
    expected_threads: int,
) -> None:
    """Test that when running ert with the given configuration file,
    the rms forward model runs rms with the given arguments"""
    monkeypatch.chdir(tmp_path / "ert/model")

    with open("snakeoil.ert", "a") as f:
        if num_cpu is not None:
            f.write(f"\nNUM_CPU {num_cpu}\n")
    if rms_opts:
        config = Path("snakeoil.ert").read_text()
        config = config.replace(
            "FORWARD_MODEL RMS(", f'FORWARD_MODEL RMS(<RMS_OPTS>="{rms_opts}", '
        )
        Path("snakeoil.ert").write_text(config)

    subprocess.run(["ert", "test_run", "snakeoil.ert", "--verbose"], check=False)

    with open(tmp_path / "scratch/user/snakeoil/realization-0/iter-0/jobs.json") as f:
        jobs_json = json.load(f)
        assert jobs_json["config_file"] == "snakeoil.ert"
        assert jobs_json["jobList"][0]["executable"] == "runrms"
        assert jobs_json["jobList"][0]["name"] == "RMS"
        assert jobs_json["jobList"][0]["argList"][4] == "0"
        assert jobs_json["jobList"][0]["argList"][12] == "14.2.2"
        args = jobs_json["jobList"][0]["argList"]
        assert args[args.index("--threads") + 1] == str(num_cpu or 1)
        parsed = get_parser().parse_args(args)
        assert parsed.threads == expected_threads
        if "--export-path" in rms_opts:
            assert parsed.export_path == "path with spaces"


@pytest.mark.requires_ert
def test_rms_forward_model_seed_invalid(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    fmu_snakeoil_project: None,
    create_multi_seed_file: Callable[[str], None],
) -> None:
    """Test that when the seed file used by RMS has an invalid format,
    the validation leads to an aborted run"""
    monkeypatch.chdir(tmp_path / "ert/model")
    create_multi_seed_file("text\n")

    output = subprocess.run(
        ["ert", "test_run", "snakeoil.ert"], capture_output=True, text=True, check=False
    )

    assert re.search(
        "Forward model step pre-experiment validation failed: "
        + r"ForwardModelConfig: Multi seed file \S+ contains non-number values",
        output.stderr,
    )
