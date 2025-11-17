import subprocess
import sys
from pathlib import Path

from pytest import MonkeyPatch


def test_entry_point(
    tmp_path: Path, monkeypatch: MonkeyPatch, source_root: Path
) -> None:
    venv_path = tmp_path / "venv"
    rmsconfig = source_root / "examples/rmsconfig"

    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
    make_venv = subprocess.run(
        f"python -m venv {venv_path};"
        f"source {venv_path}/bin/activate;"
        f"pip install -U pip; pip install {source_root};",
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    assert make_venv.returncode == 0

    get_version_cmd = (
        f"source {venv_path}/bin/activate;"
        'python -c "from runrms.config._rms_config import RmsConfig;'
        'print(RmsConfig()._site_config_file)";'
    )

    runrms_default_config = subprocess.run(
        get_version_cmd,
        capture_output=True,
        text=True,
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    assert runrms_default_config.returncode == 0
    # It may end up in lib64/ over lib/
    assert runrms_default_config.stdout.rstrip() in [
        f"{venv_path}/lib/python{pyver}/site-packages/runrms/config/runrms.yml",
        f"{venv_path}/lib64/python{pyver}/site-packages/runrms/config/runrms.yml",
    ]

    install_rmsconfig = subprocess.run(
        f"source {venv_path}/bin/activate; pip install {rmsconfig};",
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    assert install_rmsconfig.returncode == 0

    check_config_file = subprocess.run(
        get_version_cmd,
        capture_output=True,
        text=True,
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    assert check_config_file.returncode == 0
    assert check_config_file.stdout.rstrip() in [
        f"{venv_path}/lib/python{pyver}/site-packages/rmsconfig/runrms.yml",
        f"{venv_path}/lib64/python{pyver}/site-packages/rmsconfig/runrms.yml",
    ]

    check_dryrun = subprocess.run(
        f"source {venv_path}/bin/activate; runrms -v 19.0.0;",
        capture_output=True,
        text=True,
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    # Command will fail, but assert against the error message
    assert check_dryrun.returncode == 1
    # The example configured exe (which throws this error) differs from the default
    # configuration file.
    assert "/opt/example/rms/ cannot be found" in check_dryrun.stderr
