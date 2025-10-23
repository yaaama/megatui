"""Collection of constants and other useful things I could not think of a proper place for."""

import pathlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, LiteralString

# TODO ISO6081 is a typo, it should be 8601
MEGA_LS_DATEFMT_DEFAULT: LiteralString = "ISO6081_WITH_TIME"

MEGA_DEFAULT_CMD_ARGS = {
    "ls": ["-l", "--show-handles", f"--time-format={MEGA_LS_DATEFMT_DEFAULT}"],
}


"""
Regular expressions.
"""

# A dictionary defining the components of the 'ls' output.
# These keys will become the named capture groups in the final regex.
LS_PATTERN_COMPONENTS: Final[dict[str, str]] = {
    #  Flags: Can be either alphabetical or a hyphen (e.g., 'd---')
    "flags": r"[a-zA-Z-]{4}",
    # Version ('-' or a number)
    "version": r"\d+|-",
    # Size (digits for bytes or '-')
    "size": r"\d+|-",
    # Date time in ISO 8601 format (e.g., '2018-04-06T13:05:37')
    "datetime": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    # File handle (e.g., 'H:xxxxxxxx')
    "filehandle": r"H:[^\s]+",
    # Filename (captures everything until the end of the line)
    "filename": r".+",
}

# Default 'ls -l --show-handles --date-format=ISO6081_WITH_TIME' regular expression.
# re.VERBOSE allows for this clean, multi-line, and commented format.
LS_REGEXP: Final[re.Pattern[str]] = re.compile(
    rf"""
    ^
    (?P<flags>{LS_PATTERN_COMPONENTS["flags"]}) \s+
    (?P<version>{LS_PATTERN_COMPONENTS["version"]}) \s+
    (?P<size>{LS_PATTERN_COMPONENTS["size"]}) \s+
    (?P<datetime>{LS_PATTERN_COMPONENTS["datetime"]}) \s+
    (?P<filehandle>{LS_PATTERN_COMPONENTS["filehandle"]}) \s+
    (?P<filename>{LS_PATTERN_COMPONENTS["filename"]})
    $
    """,
    re.VERBOSE,
)

# 'df' parsing regular expression
# e.g.
#       Cloud drive:          250770805753 in   17210 file(s) and    1352 folder(s)
#       Inbox:                           0 in       0 file(s) and       1 folder(s)
#       Rubbish bin:                  1368 in       4 file(s) and       2 folder(s)
#       ---------------------------------------------------------------------------
#       USED STORAGE:         250770069025                  11.40% of 2199023255552
#       ---------------------------------------------------------------------------
#       Total size taken up by file versions:    306416706
#
_DF_PATTERN_COMPONENTS: Final[dict[str, str]] = {
    "location": r"^(.+?):\s+(\d+)\s+in\s+(\d+)\s+file\(s\) and\s+(\d+)\s+folder\(s\)",
    "summary": r"^USED STORAGE:\s+(\d+)\s+([\d\.]+)%\s+of\s+(\d+)",
    "versions": r"^Total size taken up by file versions:\s+(\d+)",
}

DF_REGEXPS: Final[dict[str, re.Pattern[str]]] = {
    key: re.compile(pattern) for key, pattern in _DF_PATTERN_COMPONENTS.items()
}


_DU_PATTERN_COMPONENTS: Final[dict[str, str]] = {
    # Parses du output for 'FILENAME SIZE'
    "header": r"^FILENAME\s+SIZE$",
    # Parses du output for a real filename and their size
    "file_size": r"^(.+?):\s+(\d+)",
}


DU_REGEXPS: Final[dict[str, re.Pattern[str]]] = {
    key: re.compile(pattern) for key, pattern in _DU_PATTERN_COMPONENTS.items()
}


class MegaCmdErrorCode(Enum):
    """An enumeration for 'megacmd' output codes, with their descriptions.
    Reference for errors in megaCMD:
    https://github.com/meganz/MEGAcmd/blob/e6ea71c9e4f7d606d8b3555507b3a733e5914bed/src/megacmdcommonutils.h#L63.
    """

    OK = (0, "Everything OK")
    CONFIRM_NO = (-12, 'User response to confirmation is "no"')
    EARGS = (-51, "Wrong arguments")
    INVALIDEMAIL = (-52, "Invalid email")
    NOTFOUND = (-53, "Resource not found")
    INVALIDSTATE = (-54, "Invalid state")
    INVALIDTYPE = (-55, "Invalid type")
    NOTPERMITTED = (-56, "Operation not allowed")
    NOTLOGGEDIN = (-57, "Needs logging in")
    NOFETCH = (-58, "Nodes not fetched")
    EUNEXPECTED = (-59, "Unexpected failure")
    REQCONFIRM = (-60, "Confirmation required")
    REQSTRING = (-61, "String required")
    PARTIALOUT = (-62, "Partial output provided")
    PARTIALERR = (-63, "Partial error output provided")
    EXISTS = (-64, "Resource already exists")
    REQRESTART = (-71, "Restart required")

    @property
    def code(self) -> int:
        """The integer error code."""
        return self.value[0]

    @property
    def description(self) -> str:
        """The string description of the code."""
        return self.value[1]


class MegaPath(pathlib.PurePosixPath):
    """A path object that always behaves like a POSIX path for MEGA operations.
    Inherits from pathlib.PurePosixPath to ensure forward slashes
    are always used as path separators.
    """

    @property
    def str(self) -> str:
        return self.__str__()


MEGA_ROOT_PATH: Final[MegaPath] = MegaPath("/")


@dataclass(frozen=True)
class MegaDiskUsage:
    location: MegaPath
    size_bytes: int | None


@dataclass(frozen=True)
class MegaDFOutput:
    """Dataclass representing parsed 'df' output."""

    @dataclass(frozen=True)
    class LocationInfo:
        """Represents storage information for a single location."""

        name: str
        size_bytes: int
        files: int
        folders: int

    @dataclass(frozen=True)
    class UsageSummary:
        """Represents the overall storage usage summary."""

        used_bytes: int
        percentage: float
        total_bytes: int

    locations: list[LocationInfo]
    usage_summary: UsageSummary | None
    version_size_bytes: int | None


#
# megacmd commands
MEGA_COMMANDS_ALL: set[str] = {
    "attr",
    "fuse-remove",
    "proxy",
    "backup",
    "fuse-show",
    "psa",
    "cancel",
    "get",
    "put",
    "cat",
    "graphics",
    "pwd",
    "cd",
    "help",
    "quit",
    "clear",
    "https",
    "reload",
    "completion",
    "import",
    "rm",
    "confirm",
    "invite",
    "session",
    "confirmcancel",
    "ipc",
    "share",
    "cp",
    "killsession",
    "showpcr",
    "debug",
    "lcd",
    "signup",
    "deleteversions",
    "log",
    "speedlimit",
    "df",
    "login",
    "sync",
    "du",
    "logout",
    "sync-config",
    "errorcode",
    "lpwd",
    "sync-ignore",
    "exclude",
    "ls",
    "sync-issues",
    "exit",
    "masterkey",
    "thumbnail",
    "export",
    "mediainfo",
    "transfers",
    "find",
    "mkdir",
    "tree",
    "ftp",
    "mount",
    "userattr",
    "fuse-add",
    "mv",
    "users",
    "fuse-config",
    "passwd",
    "version",
    "fuse-disable",
    "permissions",
    "webdav",
    "fuse-enable",
    "preview",
    "whoami",
}
"""All Mega commands."""

MEGA_COMMANDS_SUPPORTED: set[str] = {
    "get",
    "put",
    "cat",
    "cd",
    "rm",
    "cp",
    "du",
    "ls",
    "whoami",
    "pwd",
    "mv",
    "mkdir",
    "df",
}
"""Mega commands that are supported."""
