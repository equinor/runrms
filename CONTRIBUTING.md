# Contributing

This document contains information for contributing to this project.
All contributions are welcome!

## Developing

Clone and install into a virtual environment.

```sh
git clone git@github.com:equinor/runrms.git
cd runrms
# Create or source virtual/Komodo env
pip install -U pip
pip install -e ".[dev]"
# Make a feature branch for your changes
git checkout -b some-feature-branch
```

Run the tests with

```sh
pytest -n auto tests
```

Ensure your changes will pass the various linters before making a pull
request. It is expected that all code will be typed and validated with
mypy.

```sh
ruff check
ruff format --check
mypy src
```
