# runrms

[![runrms](https://github.com/equinor/runrms/actions/workflows/runrms.yml/badge.svg)](https://github.com/equinor/runrms/actions/workflows/runrms.yml)

**runrms** is a package to run and open [Aspen
RMS™](https://www.aspentech.com/en/products/sse/aspen-rms) under a site
installation environment. It also provides an
[Ert](https://github.com/equinor/ert) forward model to do so under an
ensemble simulation context.

> [!NOTE]
> #### Trademark Notice and Disclaimer
> **Aspen RMS™** is a registered trademark of [Aspen Technology, Inc.](https://www.aspentech.com/en)
> (AspenTech). Use of RMS™ is governed by AspenTech's licensing terms and
> conditions. It is proprietary software and is neither open-source nor free. A
> valid license agreement with AspenTech is required for its use.
>
> **runrms** is an independent project developed by Equinor and is neither
> produced by nor affiliated with AspenTech. It is open-source and free software
> released under the GPL v3 license.

---

## Usage

### Interactive

To open the default RMS version simply run:

```sh
runrms
```

You can provide a particular version to open it with if that version is
configured:

```sh
runrms -v 14.5.0
```

`runrms` can also create or interact with existing RMS projects:

```sh
# 1. If this project doesn't exist, it creates it
# 2. If it does exist, it will read and open the project with the version
#    given in the project files.
runrms project.rms.14.5.0
```

You may force-open a project to a _greater_ version, which will upgrade the
project:

```sh
runrms project.rms.14.5.0 -v 15.0.0
```

### Ert forward model

When installed in an environment with [Ert](https://github.com/equinor/ert)
this package makes an RMS forward model available. It is invoked like so:

```ert
DEFINE <RMS_NAME>        drogon.rms14.2.2
DEFINE <RMS_VERSION>     14.2.2
DEFINE <RMS_WF_NAME>     MAIN

FORWARD_MODEL RMS(<IENS>=<IENS>, <RMS_VERSION>=<RMS_VERSION>, <RMS_PROJECT>=<CONFIG_PATH>/../../rms/model/<RMS_NAME>, <RMS_WORKFLOW>=<RMS_WF_NAME>, <RMS_TARGET_FILE>=RMS_TARGET_MAIN)
```

A synthetic case with a full Fast Model Update (FMU) modeling set-up using this
forward model is available at
[fmu-drogon](https://github.com/equinor/fmu-drogon).

## Configuration

A default configuration is included in this repository at
[src/runrms/config/runrms.yml](src/runrms/config/runrms.yml). If installed in a Python
environment this default configuration will be used, but is probably not fit
for your site installation.

There are two options to use a modified configuration file on your site:

### Give a configuration path for interactive or test usage

You can invoke `runrms` interactively like so and provide a path to a
configuration file to use instead:

```sh
runrms --setup path/to/runrms.yml
```

A current limitation is that this configuration **will not** and **cannot** be
used for the Ert forward model. The primary use case for this option is
testing.

### Install a configuration package with a `runrms` entry point

You may also configure your environment through an entry-point defined in a
separate package. This package can have any name, but let us suppose it is
called `rmsconfig`. This package must add a `runrms` entry point into its
`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "rmsconfig"
version = "1.0.0"

[tool.setuptools.package-data]
rmsconfig = ["runrms.yml"]

[project.entry-points.runrms]
config_path = "rmsconfig:runrms_config_path"
```

`runrms_config_path` must be a function that returns a path to the
configuration file. The name and location of this function may be arbitrary
so long as it returns a `pathlib.Path` absolute path to the configuration
location.

Note that how the yaml file is included with your package may vary depending
on the packaging build tool you use. However, most will support a MANIFEST.in
file as an option outside of `pyproject.toml`.

```python
# src/rmsconfig/__init__.py
# src/rmsconfig/runrms.yml
from pathlib import Path

def runrms_config_path() -> Path:
    """Returns the absolute path to runrms.yml."""
    return (Path(__file__).parent / "runrms.yml").resolve()
```

`runrms` will then load, read, and use this configuration. It **does** apply
to the forward model!

A simple package that implements this is included in [examples/](examples/).

## Configuration values

As mentioned in the previous section you can find the default configuration
file included in this package at [src/runrms/config/runrms.yml](src/runrms/config/runrms.yml).
Here is a brief explanation of what these values mean.

- `wrapper`: This is an executable that is executed _between_ the RMS
    invocation. It can be used, for example, for unsetting environment
    variables before establishing the execution context for RMS.
- `default`: The default version to run when `runrms` is invoked. It must
    contain a valid entry in the `versions` entries (see below).
- `exe`: The RMS executable to invoke. This may also be another wrapper,
    depending on your set-up.
- `interactive_usage_log`: Optional. A location to write a log entry whenever
    an _interactive_ (i.e., GUI) invocation of RMS occurs.
- `env`: Contains key-value mappings defining environment variables and their
    values that will be applied to _all_ RMS versions.
- `versions`: Contains mappings of supported RMS versions and the environment
    variables to set for them, respectively. Each version can contain an `env`
    mapping.

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

See the [contributing document](CONTRIBUTING.md) for more.
