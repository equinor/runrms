import sys
from argparse import ArgumentError

import pytest

from runrms.__main__ import generate_config, get_parser, main


def test_empty_invocation(executor_env, patch_argv) -> None:
    patch_argv(["--setup", "runrms.yml"])
    main()


def test_invalid_batch_invocations(executor_env, patch_argv) -> None:
    patch_argv(["--setup", "runrms.yml", "--seed", "123"])
    with pytest.raises(ArgumentError, match="must be combined with --batch"):
        main()

    patch_argv(["--setup", "runrms.yml", "--seed", "123", "--batch", "a"])
    with pytest.raises(ArgumentError, match="must be combined with --batch"):
        main()

    patch_argv(["--setup", "runrms.yml", "--seed", "123", "a"])
    with pytest.raises(ArgumentError, match="must be combined with --batch"):
        main()

    patch_argv(["b", "--setup", "runrms.yml", "--seed", "123", "--batch", "a"])
    with pytest.raises(OSError, match="does not exist as a directory"):
        main()

    patch_argv(["project", "--setup", "runrms.yml", "-w", "a", "b"])
    with pytest.raises(SystemExit):
        main()

    patch_argv(["project", "--setup", "runrms.yml", "--batch", "a"])
    args = get_parser().parse_args(sys.argv[1:])
    config = generate_config(args)
    assert config.workflow == "a"
