from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from runrms.exceptions import RmsProjectNotFoundError


@dataclass
class RMSMaster:
    raw_version: str
    version: str
    fileversion: str
    variant: str
    user: str
    date: str
    time: str


def _sanitize_version(version: str) -> str:
    """Get complete RMS version.

    For RMS 10.0.0 and 11.0.0 (etc) the release is reported as
    10 or 11 in the .master file. Extend this to always have 3
    fields e.g. 10 --> 10.0.0.

    For version 14, there is now a V in front
    """

    if version[0].upper() == "V":  # e.g. version V14.1
        version = version[1:]

    # Valid for beta versions:
    if not version[-1].isdigit():
        return version

    numdots = version.count(".")
    if numdots == 0:
        return f"{version}.0.0"
    if numdots == 1:
        # TODO: Remove this hack _if_ RMS
        # can get its versioning act together.
        if version == "14.5":
            return version
        return f"{version}.0"
    return version


def _parse_master_file_header(filepath: Path) -> RMSMaster:
    """The root .master file creates an entry whenever there is a save event. This
    function does a light parsing of each save log entry, which are in the following
    format:

        Begin GEOMATIC file header
        ...
        date(1395)                              = 2022.09.08
        time(1395)                              = 10:58:55
        user(1395)                              = jriv
        release(1395)                           = 13.0.3
        operation(1395)                         = Save
        description(1395)                       =
        branch(1395)                            = 13_0
        build(1395)                             = 833
        variant(1395)                           = linux-amd64-gcc_4_8-release
        ...
        elements                                = 29
        filetype                                = BINARY
        fileversion                             = 2021.0000
        End GEOMATIC file header

    The number in parantheses indicates the n'th save event. The "release" is the RMS
    version that users are familiar with, hence it is renamed to version with special
    handling. 'fileversion' indicates the version of the .master file formats.
    """

    data = {
        "date": "unknown",
        "time": "unknown",
        "user": "unknown",
        "raw_version": "unknown",
        "version": "uknown",
        "variant": "unknown",
        "fileversion": "unknown",
    }

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            # We only need to read the header
            if line.startswith("End GEOMATIC"):
                break

            split_line = line.split()
            if line.startswith("release"):
                data["raw_version"] = split_line[2]
                data["version"] = _sanitize_version(split_line[2])

            for key in data:
                if line.startswith(key) and len(split_line) == 3:
                    data[key] = split_line[2]

    return RMSMaster(**data)


@dataclass
class RmsProject:
    path: Path
    locked: bool
    lockfile: str | None
    master: RMSMaster

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def from_filepath(cls, project: str) -> "RmsProject":
        project_path = Path(project)
        if not project_path.is_dir():
            raise RmsProjectNotFoundError(
                f"The project: {project_path} does not exist as a directory."
            )

        master_file = project_path / ".master"
        if not master_file.exists():
            raise FileNotFoundError(
                dedent(f"""
                RMS project .master file not found at {master_file}.
                Possible causes:
                 * The project does not exist
                 * The project data has been corrupted
                 * The project is of an unsupported version, i.e. RMS 2013.0.0x
                """)
            )
        master = _parse_master_file_header(master_file)

        lockfile = project_path / "project_lock_file"
        lockfile_content: str | None = None
        locked = lockfile.exists()
        if locked:
            with open(lockfile) as f:
                lockfile_content = f.read().strip()

        return cls(
            path=project_path,
            locked=locked,
            lockfile=lockfile_content,
            master=master,
        )
