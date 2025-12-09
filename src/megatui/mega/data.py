"""Collection of constants and other useful things I could not think of a proper place for."""

import logging
import math
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Final, LiteralString, NamedTuple, override

logger = logging.getLogger(__name__)


class MegaPath(pathlib.PurePosixPath):
    """A path object that always behaves like a POSIX path for MEGA operations.
    Inherits from pathlib.PurePosixPath to ensure forward slashes
    are always used as path separators.
    """

    @property
    def str(self) -> str:
        return self.__str__()


# Constants
MEGA_ROOT_PATH: Final[MegaPath] = MegaPath("/")
"""The root path for a MEGA cloud drive."""

MEGA_CURR_DIR: Final[MegaPath] = MegaPath(".")
"""Current path in its symbolic form ('.')."""

MEGA_PARENT_DIR: Final[MegaPath] = MegaPath("..")
"""Parent directory in its symbolic form ('..')."""

# TODO ISO6081 is a typo, it should be 8601
MEGA_LS_DATEFMT_DEFAULT: LiteralString = "ISO6081_WITH_TIME"
"""Default date formatting for `ls` output."""

MEGA_TRANSFERS_DELIMITER = "|"
"""Field delimiter for 'mega-transfers' output."""

MEGA_DEFAULT_CMD_ARGS = {
    "ls": ["-l", "--show-handles", f"--time-format={MEGA_LS_DATEFMT_DEFAULT}"],
    "transfers": [f"--col-separator={MEGA_TRANSFERS_DELIMITER}"],
}
"""Default arguments for `mega` commands."""


# A dictionary defining the components of the 'ls' output.
# These keys will become the named capture groups in the final regex.
_LS_PATTERN_COMPONENTS: Final[dict[str, str]] = {
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
"""Regular expressions for different pieces of output of `ls`."""

# Default 'ls -l --show-handles --date-format=ISO6081_WITH_TIME' regular expression.
# re.VERBOSE allows for this clean, multi-line, and commented format.
LS_REGEXP: Final[re.Pattern[str]] = re.compile(
    rf"""
    ^
    (?P<flags>{_LS_PATTERN_COMPONENTS["flags"]}) \s+
    (?P<version>{_LS_PATTERN_COMPONENTS["version"]}) \s+
    (?P<size>{_LS_PATTERN_COMPONENTS["size"]}) \s+
    (?P<datetime>{_LS_PATTERN_COMPONENTS["datetime"]}) \s+
    (?P<filehandle>{_LS_PATTERN_COMPONENTS["filehandle"]}) \s+
    (?P<filename>{_LS_PATTERN_COMPONENTS["filename"]})
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


# Response from running mega commands.
class MegaCmdResponse:
    __slots__ = ("return_code", "stderr", "stdout")

    stdout: str | None
    stderr: str | None
    return_code: int | None

    def __init__(
        self, *, stdout: str | None, stderr: str | None, return_code: int | None
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        # logger.debug(f"MegaCmdResponse created. Return code: {return_code}")

    @property
    def failed(self) -> bool:
        """Return True if cmd returned non-zero or has stderr output."""
        return bool(self.return_code or self.stderr)

    @override
    def __repr__(self) -> str:
        return (
            f"MegaCmdResponse(return_code={self.return_code},\n"
            + f"stdout={self.stdout},\n"
            + f"stderr={self.stderr}\n)"
        )

    @override
    def __str__(self) -> str:
        return f"code='{self.return_code}',\nstdout='{self.stdout}'\nstderr='{self.stderr}'"

    @property
    def err_output(self) -> str | None:
        """Return stderr from command if failed, else None."""
        if self.failed:
            return self.stderr

        return None


class MegaFileTypes(Enum):
    """File types."""

    DIRECTORY = 0
    FILE = 1


class MegaSizeUnits(Enum):
    """Enumeration for file size units allowing conversion from bytes.

    Values correspond to the power of 1024 used for conversion:
    0: Bytes (1024^0)
    1: KB (1024^1)
    2: MB (1024^2)
    3: GB (1024^3)
    4: TB (1024^4)
    """

    B = 0
    KB = 1
    MB = 2
    GB = 3
    TB = 4

    # Helper to get the string representation used in the size calculation
    def unit_str(self) -> str:
        """Returns the string representation of the current unit.

        Returns:
            str: The label for the unit (e.g., "MB", "GB").
        """
        return self.name

    def bytes_to_unit(self, size_in_bytes: int) -> float:
        """Converts a raw byte count into the current unit size.

        The calculation uses binary prefixes (1024), not decimal (1000).

        Args:
            byte_count (int): The size in bytes to convert.

        Returns:
            float: The converted size (e.g., converting 1024 bytes
                   on the .KB unit returns 1.0).
        """
        if not size_in_bytes:
            return 0

        # Calculate the divisor using bitwise shifting.
        # 1 << 10 is 1024 (2^10) (KiloBytes)
        # 1 << 20 is 1,048,576 (2^20) (MegaBytes)
        # Logic: 1 * (2 ^ (10 * unit_index))
        divisor = 1 if (self.value == 0) else (1 << (10 * self.value))

        return float(size_in_bytes) / divisor


MegaFileSize = tuple[float, MegaSizeUnits]


class MegaNode:
    # Class Variables #################################################
    __slots__ = (
        "bytes",
        "ftype",
        "handle",
        "mtime",
        "name",
        "path",
        "size",
        "version",
    )

    name: str
    """ Name of node."""
    path: MegaPath
    """ Full path of node. """
    bytes: int
    """ Size of node in BYTES, will be 0 for directories."""
    size: MegaFileSize | None
    """ Human readable size for a file, or None for directory. """

    mtime: datetime
    """ Modification date + time of file."""

    ftype: MegaFileTypes
    """ Type of node. """

    version: int
    """ Node version. """

    handle: str
    """ Unique handle of node. """

    def __init__(
        self,
        name: str,
        path: MegaPath,
        size: int,
        mtime: datetime,
        ftype: MegaFileTypes,
        version: int,
        handle: str,
    ):
        self.name = name
        self.bytes = size
        self.mtime = mtime
        self.ftype = ftype
        self.version = version
        self.handle = handle

        self.path = path

        # Human friendly sizing
        if (self.ftype == MegaFileTypes.DIRECTORY) or (size == 0):
            self.size = None
            return

        # Calculate human friendly sizing
        unit_index: int = min(int(math.log(self.bytes, 1024)), len(MegaSizeUnits) - 1)

        divisor: int
        # calculate 1024^unit_index using shifts
        # 1 << 10 is 1024 (2^10)
        # 1 << (10 * unit_index) is (2^10)^unit_index = 1024^unit_index
        divisor = 1 if (unit_index == 0) else (1 << (10 * unit_index))

        # Perform floating point division for the final readable value
        _size = float(self.bytes) / divisor

        match unit_index:
            case 0:
                _size_unit = MegaSizeUnits.B
            case 1:
                _size_unit = MegaSizeUnits.KB
            case 2:
                _size_unit = MegaSizeUnits.MB
            case 3:
                _size_unit = MegaSizeUnits.GB
            case _:
                # Anything larger than 3 should be shown in terabytes
                logger.warning(
                    f"Calculated unit index {unit_index} for size {self.bytes} is unexpected. Defaulting to TB."
                )
                _size_unit = MegaSizeUnits.TB

        self.size = (_size, _size_unit)

    @property
    def is_file(self) -> bool:
        """TRUE if node is a file."""
        return self.ftype == MegaFileTypes.FILE

    @property
    def is_dir(self) -> bool:
        """TRUE if node is a directory."""
        return self.ftype == MegaFileTypes.DIRECTORY

    @override
    def __str__(self) -> str:
        return f"path='{self.path.str}',\nftype='{self.ftype.name}',\nhandle='{self.handle}',\nbytes='{self.bytes}',\nmtime='{self.mtime}'\nversion='{self.version}'"


# Alias
# MegaItems = list[MegaItem]
type MegaNodes = tuple[MegaNode, ...]


class MegaCmdErrorCode(Enum):
    """An enumeration for 'megacmd' output codes, with their descriptions.
    Reference for errors in megaCMD:
    https://github.com/meganz/MEGAcmd/blob/e6ea71c9e4f7d606d8b3555507b3a733e5914bed/src/megacmdcommonutils.h#L63.
    """

    OK = (0, "Everything OK")
    CONFIRM_NO = (12, 'User response to confirmation is "no"')
    EARGS = (51, "Wrong arguments")
    INVALID_EMAIL = (52, "Invalid email")
    NOT_FOUND = (53, "Resource not found")
    INVALID_STATE = (54, "Invalid state")
    INVALID_TYPE = (55, "Invalid type")
    NOT_PERMITTED = (56, "Operation not allowed")
    NOT_LOGGED_IN = (57, "Needs logging in")
    NO_FETCH = (58, "Nodes not fetched")
    E_UNEXPECTED = (59, "Unexpected failure")
    REQ_CONFIRM = (60, "Confirmation required")
    REQ_STRING = (61, "String required")
    PARTIAL_OUTPUT = (62, "Partial output provided")
    PARTIAL_ERROR = (63, "Partial error output provided")
    EXISTS = (64, "Resource already exists")
    REQ_RESTART = (71, "Restart required")

    @classmethod
    def get_all_codes(cls) -> set[int]:
        """Return a set of all error codes defined in the Enum."""
        # Use a set comprehension for a concise and efficient implementation
        return {member.code for member in cls}

    @classmethod
    def is_an_error(cls, err_code: int) -> bool:
        if err_code == cls.OK.code:
            return False
        return any(member.code == err_code for member in cls)

    @classmethod
    def code_to_string(cls, err_code: int) -> str:
        if err_code == 0:
            return cls.OK.description

        for member in cls:
            if member.code == err_code:
                return member.description

        raise ValueError(
            f"Error code '{err_code}' is not in the set of values returned by a mega-cmd process."
        )

    @property
    def code(self) -> int:
        """The integer error code for an enum member."""
        return self.value[0]

    @property
    def description(self) -> str:
        """Description of error for enum member."""
        return self.value[1]


class MegaError(Exception): ...


class MegaUnknownError(MegaError): ...


class MegaNodeNotFound(MegaError): ...


class MegaCmdError(Exception):
    """Custom exception for mega-* command errors."""

    message: str
    response: MegaCmdResponse | None

    def __init__(self, message: str, response: MegaCmdResponse | None = None):
        super().__init__(message)
        self.message = message

        # If a response object is given, use its data.
        # This makes it the source of truth.

        if response:
            self.response = response

        # Centralized logging
        logger.error(
            f"MegaCmdError: {self.message} (Return Code: {self.return_code}, Stderr: {self.stderr})"
        )

    @property
    def stderr(self) -> str | None:
        if not self.response:
            logger.debug("Failed to retrieve stderr: No response object.")
            return None
        if self.response.stderr:
            return self.response.stderr

        return None

    @property
    def return_code(self) -> int | None:
        if not self.response:
            logger.debug("No response object.")
            return None
        if self.response.return_code:
            return self.response.return_code

        return 0


@dataclass(frozen=True)
class MegaDiskUsage:
    location: MegaPath
    size_bytes: int | None


@dataclass(frozen=True)
class MegaDiskFree:
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


@dataclass(frozen=True, slots=True, eq=False, match_args=False)
class MegaMediaInfo:
    """Class to store media information for a file."""

    path: str
    width: int | None
    height: int | None
    fps: float | None
    playtime: str | None

    @property
    def resolution(self) -> str:
        """Resolution details."""
        if self.width and self.height:
            resolution = f"({self.width}x{self.height})"
        else:
            resolution = "(Unknown resolution)"
        return resolution


MEGA_TRANSFERS_REGEXP = re.compile(
    r"^(?P<TYPE>.+?)\|"
    + r"(?P<TAG>\d+)\|"
    + r"(?P<SOURCEPATH>.+?)\|"
    + r"(?P<DESTINYPATH>.+?)\|"
    + r"(?P<PROGRESS>.+?)\|"
    + r"(?P<STATE>.+)"
    + r"$"
)
"""Regular expression to parse the output of `mega-transfers`."""


class MegaTransferOperationType(Enum):
    PAUSE = auto()
    RESUME = auto()
    CANCEL = auto()


class MegaTransferOperationTarget:
    UPLOADS = auto()
    DOWNLOADS = auto()
    ALL = auto()


class MegaTransferGlobalState(Enum):
    ALL_PAUSED = "DOWNLOADS AND UPLOADS ARE PAUSED"
    DOWNLOADS_PAUSED = "DOWNLOADS ARE PAUSED"
    UPLOADS_PAUSED = "UPLOADS ARE PAUSED"
    NO_STATE = None


class MegaTransferType(Enum):
    UPLOAD = "⇑"
    DOWNLOAD = "⇓"
    SYNC = "⇵"
    BACKUP = "⏫"


# TODO
# Implement usage of this
class MegaTransferProgress(NamedTuple):
    """Percentage done of the transfer, and the size of the transfer."""

    percent_done: float
    size: str


class MegaTransferState(Enum):
    """States for a transfer.
    These states are directly taken from the megacmd source-code.
    """

    QUEUED = "QUEUED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class MegaTransferItem:
    __slots__ = ("destination_path", "progress", "source_path", "state", "tag", "type")

    def __init__(
        self,
        type: MegaTransferType,
        tag: int,
        source_path: str,
        destination_path: str,
        progress: str,
        state: MegaTransferState,
    ):
        self.type = type
        self.tag = tag
        self.source_path = source_path
        self.destination_path = destination_path
        self.progress = progress
        self.state = state

    @override
    def __str__(self):
        return f"state='{self.type}', name='{self.type.name}' source_path='{self.source_path}', destination_path='{self.destination_path}', progress='{self.progress}', state='{self.state.name}'"

    @override
    def __repr__(self):
        return f"MegaTransferItem(state='{self.type}', name='{self.type.name}' source_path='{self.source_path}', destination_path='{self.destination_path}', progress='{self.progress}', state='{self.state.name}')"


def get_size_in(bytes_used: int, unit: MegaSizeUnits) -> float:
    """Converts bytes to another unit specified by `unit`.
    Args: 'bytes_used' Size in bytes.
          'unit' Unit to convert to.
    """
    match unit:
        case MegaSizeUnits.B:
            return bytes_used
        # Bit shifting
        case MegaSizeUnits.KB:
            return bytes_used >> 10
        case MegaSizeUnits.MB:
            return bytes_used >> 20
        case MegaSizeUnits.GB:
            return bytes_used >> 30
        case MegaSizeUnits.TB:
            return bytes_used >> 40
    return bytes_used


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
    "transfers",
    "mediainfo",
}
"""Mega commands that are supported."""
