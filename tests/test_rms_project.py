import shutil
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from runrms.config._rms_project import (
    RmsProject,
    _parse_master_file_header,
    _sanitize_version,
)
from runrms.exceptions import RmsProjectNotFoundError


@pytest.mark.parametrize(
    "given, expected",
    [
        ("13", "13.0.0"),
        ("13.1", "13.1.0"),
        ("V14", "14.0.0"),
        ("v14.1.3", "14.1.3"),
        ("14.2b", "14.2b"),
    ],
)
def test_sanitize_version(given: str, expected: str) -> None:
    assert _sanitize_version(given) == expected


def test_make_rmsproject_with_nonexistent_project_dir(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RmsProjectNotFoundError, match="does not exist as a directory"):
        RmsProject.from_filepath("notreal")


def test_make_rmsproject_with_project_dir_as_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("notreal").touch()
    with pytest.raises(RmsProjectNotFoundError, match="does not exist as a directory"):
        RmsProject.from_filepath("notreal")


def test_make_rmsproject_without_master_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("notreal").mkdir()
    with pytest.raises(FileNotFoundError, match="RMS project .master file not found"):
        RmsProject.from_filepath("notreal")


def test_rmsproject_parses_correct_master(source_root: Path) -> None:
    drogon_master = source_root / "tests/testdata/rms/drogon.rms13.0.3/.master"
    master = _parse_master_file_header(drogon_master)
    assert master.version == "13.0.3"
    assert master.user == "jriv"
    assert master.time == "10:58:55"
    assert master.date == "2022.09.08"
    assert master.variant == "linux-amd64-gcc_4_8-release"
    assert master.fileversion == "2021.0000"


def test_make_rmsproject_without_lock(source_root: Path) -> None:
    drogon_master = source_root / "tests/testdata/rms/drogon.rms13.0.3"
    rmsproject = RmsProject.from_filepath(str(drogon_master))
    assert rmsproject.path == drogon_master
    assert rmsproject.name == "drogon.rms13.0.3"
    assert rmsproject.locked is False
    assert rmsproject.lockfile is None
    assert rmsproject.master.version == "13.0.3"
    assert rmsproject.master.user == "jriv"
    assert rmsproject.master.time == "10:58:55"
    assert rmsproject.master.date == "2022.09.08"
    assert rmsproject.master.variant == "linux-amd64-gcc_4_8-release"
    assert rmsproject.master.fileversion == "2021.0000"


def test_make_rmsproject_with_lock(
    tmp_path: Path, monkeypatch: MonkeyPatch, source_root: Path
) -> None:
    test_path = tmp_path / "drogon.rms13.0.3"
    drogon_master = source_root / "tests/testdata/rms/drogon.rms13.0.3"
    shutil.copytree(drogon_master, test_path)

    monkeypatch.chdir(test_path)
    lock_txt = (
        "Locked by abc on s6.st.so.no with process id (pid) 123 at 2037.03.14 09:00:00"
    )
    Path("project_lock_file").write_text(lock_txt)
    rmsproject = RmsProject.from_filepath(str(test_path))
    assert rmsproject.path == test_path
    assert rmsproject.name == "drogon.rms13.0.3"
    assert rmsproject.locked is True
    assert rmsproject.lockfile == lock_txt
