import sys
from argparse import ArgumentError
from pathlib import Path
from unittest.mock import patch

import pytest

from runrms.__main__ import generate_config, get_parser, main


def test_empty_invocation(executor_env: Path) -> None:
    with patch("sys.argv", ["runrms", "--setup", "runrms.yml"]):
        main()


def test_invalid_batch_invocations(executor_env: Path) -> None:
    with (
        patch("sys.argv", ["runrms", "--setup", "runrms.yml", "--seed", "123"]),
        pytest.raises(ArgumentError, match="must be combined with --batch"),
    ):
        main()

    with (
        patch(
            "sys.argv",
            ["runrms", "--setup", "runrms.yml", "--seed", "123", "--batch", "a"],
        ),
        pytest.raises(ArgumentError, match="must be combined with --batch"),
    ):
        main()

    with (
        patch("sys.argv", ["runrms", "--setup", "runrms.yml", "--seed", "123", "a"]),
        pytest.raises(ArgumentError, match="must be combined with --batch"),
    ):
        main()

    with (
        patch(
            "sys.argv",
            ["runrms", "b", "--setup", "runrms.yml", "--seed", "123", "--batch", "a"],
        ),
        pytest.raises(OSError, match="does not exist as a directory"),
    ):
        main()

    with (
        patch(
            "sys.argv", ["runrms", "project", "--setup", "runrms.yml", "-w", "a", "b"]
        ),
        pytest.raises(SystemExit),
    ):
        main()

    with patch(
        "sys.argv", ["runrms", "project", "--setup", "runrms.yml", "--batch", "a"]
    ):
        args = get_parser().parse_args(sys.argv[1:])
    config = generate_config(args)
    assert config.workflow == "a"
