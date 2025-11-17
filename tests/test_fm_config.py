from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest import MonkeyPatch

from runrms.config import (
    DEFAULT_CONFIG_FILE,
    ForwardModelConfig,
)
from runrms.exceptions import (
    RmsProjectNotFoundError,
)


def _mocked_args() -> Mock:
    args = Mock()
    args.iens = -1
    args.project = "project"
    args.workflow = "workflow"
    args.run_path = "run_path"
    args.version = "14.2.2"
    args.readonly = False
    args.import_path = "./"
    args.export_path = "./"
    args.allow_no_env = False
    args.target_file = "some/file"
    args.setup = DEFAULT_CONFIG_FILE
    return args


def test_config_ok(fm_executor_env: Path) -> None:
    args = _mocked_args()

    config = ForwardModelConfig(args)
    assert config is not None


def test_missing_project() -> None:
    args = _mocked_args()
    args.project = "another_project"

    with pytest.raises(RmsProjectNotFoundError):
        ForwardModelConfig(args)


@pytest.mark.parametrize("rms_seed", ["", "a", "123x"])
def test_bad_seed_from_env_var(
    fm_executor_env: Path, monkeypatch: MonkeyPatch, rms_seed: str
) -> None:
    args = _mocked_args()
    monkeypatch.setenv("RMS_SEED", rms_seed)

    with pytest.raises(ValueError, match="'RMS_SEED' environment variable"):
        ForwardModelConfig(args)


@pytest.mark.parametrize(
    "iens, expected_result",
    [
        (0, 422851785),
        (1, 422851785),
        (2, 422851785),
    ],
)
def test_single_seed_ok(fm_executor_env: Path, iens: int, expected_result: int) -> None:
    args = _mocked_args()
    args.iens = iens
    contents = "422851785"
    with open("run_path/RMS_SEED", "w") as f:
        f.write(contents)

    config = ForwardModelConfig(args)
    assert config.seed == expected_result


@pytest.mark.parametrize(
    "iens, expected_result",
    [
        (0, 422851785),
        (1, 723121249),
        (2, 132312123),
    ],
)
def test_multi_seed_ok(fm_executor_env: Path, iens: int, expected_result: int) -> None:
    args = _mocked_args()
    args.iens = iens
    contents = ["3", "422851785", "723121249", "132312123"]
    with open("run_path/random.seeds", "w") as f:
        f.write("\n".join(contents))

    config = ForwardModelConfig(args)
    assert config.seed == expected_result


@pytest.mark.parametrize(
    "contents, expected_error",
    [
        ("", r"Single seed file \S+ is empty"),
        ("text", r"Single seed file \S+ contains non-number values"),
        (
            "\n".join(["1000", "1001"]),
            r"Single seed file \S+ contains multiple seed values",
        ),
    ],
)
def test_single_seed_invalid(
    fm_executor_env: Path, contents: str, expected_error: str
) -> None:
    args = _mocked_args()
    with open("run_path/RMS_SEED", "w") as f:
        f.write(contents)

    with pytest.raises(ValueError, match=expected_error):
        ForwardModelConfig(args)


@pytest.mark.parametrize(
    "contents, iens, expected_error",
    [
        ([""], 0, r"Multi seed file \S+ is empty"),
        (["1", "text"], 0, r"Multi seed file \S+ contains non-number values"),
        (["0"], 0, r"Multi seed file \S+ has no seed values"),
        (
            ["1", "1000"],
            1,
            r"Multi seed file \S+ has too few seed values \(1\) "
            + r"for the needed realization number \(2\)",
        ),
    ],
)
def test_multi_seed_invalid(
    fm_executor_env: Path, contents: list[str], iens: int, expected_error: str
) -> None:
    args = _mocked_args()
    args.iens = iens
    with open("run_path/random.seeds", "w") as f:
        f.write("\n".join(contents))

    with pytest.raises(ValueError, match=expected_error):
        ForwardModelConfig(args)
