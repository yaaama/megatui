"""'megacmd' library provides an easy way of interacting with the 'mega-cmd' CLI."""

import asyncio
import logging
import math
import pathlib
import re
import subprocess
from enum import Enum
from pathlib import Path, PurePath
from typing import Annotated, NamedTuple, TypedDict, override

logging.basicConfig(
    filename="megacmd.log",
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger(__name__)
# Get the logger for the 'asyncio' library and set its level to WARNING.
# This will hide all INFO and DEBUG messages from asyncio.
logging.getLogger("asyncio").setLevel(logging.WARNING)
logger.debug("This is a debug message.")

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


class MegaLibError(Exception):
    """Custom exception for incorrect library usage."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal: bool = fatal
        logger.error(f"MegaLibError: {message} (Fatal: {fatal})")


class MegaCmdError(Exception):
    """Custom exception for mega-* command errors."""

    def __init__(
        self, message: str, return_code: int | None = None, stderr: str | None = None
    ):
        super().__init__(message)
        self.return_code: int | None = return_code
        self.stderr: str | None = stderr
        self.message: str = message
        logger.error(
            f"MegaCmdError: {message} (Return Code: {return_code}, Stderr: {stderr})"
        )


class MegaFileTypes(Enum):
    """File types."""

    DIRECTORY = 0
    FILE = 1


class MegaSizeUnits(Enum):
    """File size units."""

    B = 0
    KB = 1
    MB = 2
    GB = 3
    TB = 4

    # Helper to get the string representation used in the size calculation
    def unit_str(self) -> str:
        """Returns the unit best suited for the size of the file."""
        # Match the order in the Enum
        _unit_strings = ["B", "KB", "MB", "GB", "TB"]
        try:
            return _unit_strings[self.value]
        # Raise an error for unknown units
        except IndexError:
            logger.warning(f"Unknown MegaSizeUnits value: {self.value}")
            return "?"


class MegaItem:
    # Class Variables #################################################
    __slots__ = (
        "bytes",
        "ftype",
        "handle",
        "mtime",
        "name",
        "parent_path",
        "path",
        "size",
        "size_unit",
        "version",
    )

    name: str  # Name of item
    """Name of file/folder item."""

    parent_path: str
    """ Path of parent directory of file/directory. """

    path: str
    """ Full path of item. """

    bytes: int
    """ Size of file in BYTES, will be 0 for dirs."""

    size: float
    """ Size of file (human readable) """

    size_unit: MegaSizeUnits
    """ Unit for human readable size. """

    mtime: str  # Parse into date if needed
    """ Modification time of file."""

    ftype: MegaFileTypes
    """ Type of file. """

    version: int
    """ File version. """

    handle: str
    """ Unique handle. """

    def __init__(
        self,
        name: str,
        parent_path: str,
        size: int,
        mtime: str,
        ftype: MegaFileTypes,
        version: int,
        handle: str,
    ):
        self.name = name
        self.parent_path = parent_path
        self.bytes = size
        self.mtime = mtime
        self.ftype = ftype
        self.version = version
        self.handle = handle

        self.path = str(self.full_path)

        # Human friendly sizing #############################################################
        if (size == 0) or (self.ftype == MegaFileTypes.DIRECTORY):
            self.size = 0.0
            self.size_unit = MegaSizeUnits.B
            return

        # Calculate human friendly sizing
        unit_index: int = min(int(math.log(self.bytes, 1024)), len(MegaSizeUnits) - 1)

        divisor: int
        # calculate 1024^unit_index using shifts
        # 1 << 10 is 1024 (2^10)
        # 1 << (10 * unit_index) is (2^10)^unit_index = 1024^unit_index
        divisor = 1 if (unit_index == 0) else (1 << (10 * unit_index))

        # Perform floating point division for the final readable value
        self.size = float(self.bytes) / divisor

        match unit_index:
            case 0:
                self.size_unit = MegaSizeUnits.B
            case 1:
                self.size_unit = MegaSizeUnits.KB
            case 2:
                self.size_unit = MegaSizeUnits.MB
            case 3:
                self.size_unit = MegaSizeUnits.GB
            case _:
                # Anything larger than 3 should be shown in terabytes
                logger.warning(
                    f"Calculated unit index {unit_index} for size {self.bytes} is unexpected. Defaulting to TB."
                )
                self.size_unit = MegaSizeUnits.TB

    def is_file(self) -> bool:
        return self.ftype == MegaFileTypes.FILE

    def is_dir(self) -> bool:
        return self.ftype == MegaFileTypes.DIRECTORY

    @property
    def full_path(self) -> PurePath:
        folder: PurePath = PurePath(self.parent_path)
        path: PurePath = folder / self.name
        return path

    @staticmethod
    def get_size_in(bytes: int, unit: MegaSizeUnits) -> int:
        """Returns size of file in specified unit.
        Args: 'bytes' Size of file in bytes.
              'unit' Unit of size to convert bytes to.
        """
        match unit:
            case MegaSizeUnits.B:
                return bytes
            # Bit shifting
            case MegaSizeUnits.KB:
                return bytes >> 10
            case MegaSizeUnits.MB:
                return bytes >> 20
            case MegaSizeUnits.GB:
                return bytes >> 30
            case MegaSizeUnits.TB:
                return bytes >> 40

        return self.bytes


# Alias
# MegaItems = list[MegaItem]
type MegaItems = list[MegaItem]


# TODO
class MegaMediaInfo:
    path: str
    width: int | None
    height: int | None
    fps: float | None
    playtime: str

    def __init__(self, path: str, width: int, height: int, fps: float, playtime: str):
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.playtime = playtime


# Response from running mega commands.
class MegaCmdResponse:
    __slots__ = ("return_code", "stderr", "stdout")

    stdout: str
    stderr: str | None
    return_code: int | None

    def __init__(self, stdout: str, stderr: str | None, return_code: int | None):
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        # logger.debug(f"MegaCmdResponse created. Return code: {return_code}")

    @property
    def failed(self) -> bool:
        """
        Check if the command either returned non-zero or had any standard
        error output.
        """
        if (self.return_code) or (self.stderr):
            return True
        return False

    @override
    def __repr__(self) -> str:
        return (
            f"MegaCmdResponse(return_code={self.return_code},\n"
            + f"stdout={self.stdout},\n"
            + f"stderr={self.stderr}\n)"
        )

    @property
    def err_output(self) -> str | None:
        return self.stderr or self.stdout if self.failed else None


# Default 'ls -l --show-handles' regular expression.
LS_REGEXP: re.Pattern[str] = re.compile(
    r"^([^\s]{4})\s+"  #  Flags: Can be either alphabetical or a hyphen
    + r"(\d+|-)\s+"  # Version ('-' or number), skip whitespace
    + r"(\d+|-)\s+"  # Size (digits for bytes or '-'), skip whitespace
    + r"(\d{2}\w{3}\d{4})\s+"  # Date (DDMonYYYY), skip whitespace
    + r"(\d{2}:\d{2}:\d{2})\s+"  # Time (HH:MM:SS), skip whitespace
    + r"(H:[^\s]+)\s+"  # File handle ('H:xxxxxxxx')
    + r"(.+)$"  # Filename (everything else)
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
__DF_LOCATION_REGEXP: re.Pattern[str] = re.compile(
    r"^(.+?):\s+(\d+)\s+in\s+(\d+)\s+file\(s\) and\s+(\d+)\s+folder\(s\)"
)  # Regexp to parse mount info

__DF_SUMMARY_REGEXP: re.Pattern[str] = re.compile(
    r"^USED STORAGE:\s+(\d+)\s+([\d\.]+)%\s+of\s+(\d+)"
)  # Regexp to parse total storage usage.
__DF_VERSIONS_REGEXP: re.Pattern[str] = re.compile(
    r"^Total size taken up by file versions:\s+(\d+)"
)  # Regexp to parse storage taken up by file versions

__DU_HEADER_REGEXP: re.Pattern[str] = re.compile(
    r"^FILENAME\s+SIZE$"
)  # Parses du output for 'FILENAME SIZE'
__DU_REGEXP: re.Pattern[str] = re.compile(
    r"^(.+?):\s+(\d+)"
)  # Parses du output for a real filename and their size


def build_megacmd_cmd(command: tuple[str, ...]) -> tuple[str, ...]:
    """Constructs a list containing the command to run and arguments.
    This list will transform something like: [ls, -l] into [mega-ls, -l]
    Also performs checking to see if the command is valid.
    """
    if not command:
        logger.critical("Command tuple cannot be empty.")
        raise MegaLibError("Command tuple cannot be empty.", fatal=True)

    if command[0] not in MEGA_COMMANDS_SUPPORTED:
        logger.critical(f"Unsupported command '{command[0]}' requested.")
        raise MegaLibError(
            f"The library does not support command '{command[0]}'.", fatal=True
        )

    # if 'command' is ('ls', '-l', '--tree'), then 'megacmd' name will be 'mega-ls'
    megacmd_name: str = f"mega-{command[0]}"

    # Get all elements from the second element onwards using slice [1:]
    remaining_args: tuple[str, ...] = command[1:]

    # (megacmd_name, followed by all elements in remaining_args)
    final: tuple[str, ...] = (megacmd_name, *remaining_args)
    logger.debug(f"Built mega-cmd: {' '.join(final)}")

    return final


###############################################################################
async def run_megacmd(command: tuple[str, ...]) -> MegaCmdResponse:
    """Runs a specific mega-* command (e.g., mega-ls, mega-whoami)
    and returns MegaCmdResponse.

    Args:
        command (tuple[str, ...]): The base command name and its arguments.

    """
    # Construct the actual executable name (e.g., "mega-ls")
    cmd_to_exec: tuple[str, ...] = build_megacmd_cmd(command)
    logger.info(f"Executing mega-cmd: {' '.join(cmd_to_exec)}")
    cmd, *cmd_args = cmd_to_exec

    try:
        process = await asyncio.create_subprocess_exec(
            cmd,
            *cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        megacmd_obj = MegaCmdResponse(
            stdout=stdout_str,
            stderr=None,  # Initialize stderr as None
            return_code=process.returncode,
        )

        if stderr_str:
            megacmd_obj.stderr = stderr_str
            logger.warning(
                f"Command {' '.join(cmd_to_exec)} produced stderr: {stderr_str}"
            )

        # Handle cases where mega-* commands might print errors to stdout
        if process.returncode != 0:
            error_message = stderr_str if stderr_str else stdout_str
            logger.error(
                f"Command '{' '.join(command)}' failed with return code {process.returncode}: {error_message}"
            )
            raise MegaCmdError(
                f"Command '{' '.join(command)}' failed: {error_message}",
                return_code=process.returncode,
                stderr=stderr_str or stdout_str,  # Use stderr if available
            )

        logger.debug(f"Command '{' '.join(command)}' completed successfully.")
        return megacmd_obj

    except FileNotFoundError:
        logger.error(
            f"Mega-cmd executable '{cmd_to_exec[0]}' not found. Is it in PATH?"
        )
        raise MegaCmdError(
            f"Command '{cmd_to_exec[0]}' not found.",
            stderr=f"{cmd_to_exec[0]} not found",
        )
    except Exception as e:
        logger.exception(f"Unexpected error running '{cmd_to_exec[0]}'")
        # Wrap unexpected errors
        raise MegaCmdError(f"Unexpected error running '{cmd_to_exec[0]}': {e}") from e


###########################################################################
async def mega_start_server():
    """Starts the mega server in the background."""
    pass


###########################################################################
async def check_mega_login() -> tuple[bool, str | None]:
    """Checks if the user is logged into MEGA using 'mega-whoami'.

    Returns:
        tuple[bool, str | None]: A tuple containing:
            - bool: True if logged in, False otherwise.
            - str | None: The username (email) if logged in, otherwise a message
                          indicating the status or error.
    """
    logger.info("Checking MEGA login status with 'mega-whoami'.")

    try:
        response: MegaCmdResponse = await run_megacmd(command=("whoami",))

        error_msg = response.err_output
        if error_msg:
            logger.info(f"Received error output: {error_msg}")
            return False, "You are not logged in."

        # Extract username
        if "@" in response.stdout:
            username = response.stdout.strip()
            logger.info(f"Successfully logged in as: {username}")
            return True, username

        else:
            logger.warning(
                f"Login status uncertain. Unexpected response: {response.stdout}"
            )
            return False, f"Login status uncertain. Response: {response}"
    except MegaCmdError as e:
        logger.error(f"MegaCmdError during login check: {e}")
        return False, f"Login check failed due to command error: {e.message}"
    except Exception as e:
        logger.exception("An unexpected error occurred during login check.")
        return False, f"An unexpected error occurred: {e}"


###########################################################################


async def mega_ls(
    path: str | None = "/", flags: tuple[str, ...] | None = None
) -> MegaItems:
    """Lists files and directories in a given MEGA path using 'mega-ls -l' (sizes in bytes).

    Args:
        path (str): The MEGA path to list (e.g., "/", "/Backups"). Defaults to "/".
        flags (tuple[str, ...], optional): Additional flags for mega-ls.

    Returns:
        list[MegaItem]: A list of MegaItem objects representing the contents.
                        Returns an empty list if the path is invalid or an error occurs.
    """
    curr_path_for_items: str

    if path:
        target_path: str = path if path.startswith("/") else f"/{path}"
        curr_path_for_items = target_path
        logger.info(f"Listing contents of MEGA path: {target_path}")

    else:
        target_path = "."
        curr_path_for_items = "/"
        logger.info("Target path not specified: Listing nodes of current path.")

    cmd: list[str] = [
        "ls",
        "-l",
        "--show-handles",
    ]

    if flags:
        cmd.extend(flags)

    cmd.append(target_path)

    response: MegaCmdResponse = await run_megacmd(tuple(cmd))

    error_msg = response.err_output
    if error_msg:
        logger.error(f"Error listing files in '{target_path}': {error_msg}")
        return []

    items: MegaItems = []

    # Pop out the first element (it will be the header line)
    lines = response.stdout.strip().split("\n")[0:]

    # Handle empty output
    if not lines or not lines[0].strip():
        logger.info(f"No items found in '{target_path}' or output is empty.")
        return []

    # Parse the lines we receive
    for line in lines:
        """Parse each line of the ls output"""
        parsed_tuple: tuple[MegaFileTypes, tuple[str, ...]]

        # Stripped line
        __line: str = line.strip()

        # Fields matched from regular expression
        __fields: re.Match[str] | None = LS_REGEXP.match(__line)

        # If we don't have any values, then we have failed this line
        if not __fields:
            logger.debug(f"Line did not match LS_REGEXP: '{__line}'")
            continue

        # Get field values from our regexp matches
        __file_info: tuple[str, ...] = __fields.groups()

        # If flags (first elem) contains 'd' as first elem, then we have a directory
        if __file_info[0][0] == "d":
            logger.debug(f"Parsed directory: {__file_info[-1]}")
            parsed_tuple = (MegaFileTypes.DIRECTORY, __file_info)

        else:
            # Else it is a regular file
            logger.debug(f"Parsed file: {__file_info[-1]}")
            parsed_tuple = (MegaFileTypes.FILE, __file_info)

        # Tuple values
        _file_type, (_flags, _vers, _size, _date, _time, _handle, _name) = parsed_tuple

        # Values to convert
        mtime_str: str = f"{_date} {_time}"
        item_size: int
        version: int

        # If we have a regular file
        if _file_type == MegaFileTypes.FILE:
            try:
                item_size = int(_size)
                version = int(_vers)
            except ValueError:
                logger.warning(
                    f"Could not convert size '{_size}' or version '{_vers}' to int for item '{_name}'. Defaulting to 0."
                )
                item_size = 0
                version = 0

        # Node must be a directory then and so we have no size or version counter
        else:
            item_size = 0
            version = 0

        items.append(
            MegaItem(
                name=_name,
                parent_path=curr_path_for_items,
                size=item_size,
                mtime=mtime_str,
                ftype=_file_type,
                version=version,
                handle=_handle,
            )
        )
    logger.info(f"Successfully listed {len(items)} items in '{target_path}'.")
    return items


###############################################################################


class DiskUsage(NamedTuple):
    location: str
    usage: int | None


async def mega_du(
    dir_path: str = "/",
    include_version_info: bool = False,
    units: MegaSizeUnits | None = None,
):
    """
    Get disk usage. 'recurse' if 'True', will then calculate disk
    usage for all subfolders too.
    'human' toggles whether it should use the '-h' flag and return the value in those units.
    'units' must be one of the values specified by SIZE_UNIT enum.
    If human is 'True' then 'units' value will be ignored.
    """

    # Prepare our command
    cmd: list[str] = ["du"]

    if include_version_info:
        cmd.append("--versions")

    cmd.append(dir_path)

    try:
        response = await run_megacmd(tuple(cmd))
        err_msg = response.err_output
        if err_msg:
            logger.error(
                f"Ran into problems running 'du' for path '{dir_path}': {err_msg}"
            )
            raise MegaCmdError(
                f"Ran into problems running 'du' for path '{dir_path}': {err_msg}"
            )

        logger.debug(f"Successfully ran 'du' for path '{dir_path}'")

        # TODO Finish this off by parsing the headers (we can discard) and the file paths and size
        output = response.stdout.splitlines()

        assert len(output) > 3, "Output of 'du' should be 3 lines or more."

        # We can ignore the header
        _header = __DU_HEADER_REGEXP.match(output[0])

        file_line_match = __DU_REGEXP.match(output[1])
        assert file_line_match, f"No matches for du file lines: {file_line_match}"

        _filename, _size = file_line_match.groups()

        assert _filename
        assert _size

        return DiskUsage(location=_filename, usage=int(_size))

    except MegaCmdError as e:
        logger.error(f"MegaCmdError during mega_du for '{dir_path}': {e}")
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_du for '{dir_path}'."
        )


###############################################################################
async def mega_cd(target_path: str = "/"):
    """Change directories."""
    logger.info(f"Changing directory to {target_path}")

    cmd: list[str] = ["cd", target_path]
    try:
        response = await run_megacmd(tuple(cmd))

        error_msg = response.err_output
        if error_msg:
            logger.error(f"Error changing directories to '{target_path}': {error_msg}")
            raise MegaCmdError(
                f"Failed to change directory to '{target_path}': {error_msg}"
            )

        logger.info(f"Successfully changed directory to '{target_path}'")
    except MegaCmdError as e:
        logger.error(f"MegaCmdError during mega_cd for '{target_path}': {e}")
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_cd for '{target_path}'."
        )


async def mega_pwd() -> str:
    """Change directories."""
    logger.info("Getting current working directory.")

    cmd: tuple[str, ...] = ("pwd",)
    try:
        response = await run_megacmd(cmd)

        error_msg = response.err_output
        if error_msg:
            logger.error(f"Error printing working directory: {error_msg}")
            return ""

        pwd_path = response.stdout.strip()
        logger.info(f"Current working directory: {pwd_path}")
        return pwd_path
    except MegaCmdError as e:
        logger.error(f"MegaCmdError during mega_pwd: {e}")
        return ""
    except Exception:
        logger.exception("An unexpected error occurred during mega_pwd.")
        return ""


###############################################################################
async def mega_cd_ls(
    target_path: str | None = "/", ls_flags: tuple[str, ...] | None = None
) -> MegaItems:
    """Change directories and ls."""
    effective_target_path = target_path if target_path else "/"
    logger.info(f"Changing directory and listing contents for {effective_target_path}")

    await mega_cd(effective_target_path)
    items = await mega_ls(effective_target_path, ls_flags)
    logger.info(
        f"Finished cd and ls for {effective_target_path}. Found {len(items)} items."
    )

    return items


###############################################################################
###############################################################################
async def mega_cp(file_path: str, target_path: str) -> None:
    """Copy file from 'file_path' to 'target_path'"""
    logger.info(f"Copying file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("cp", file_path, target_path)
    try:
        response = await run_megacmd(cmd)

        error_msg = response.err_output
        if error_msg:
            logger.error(
                f"Error copying file '{file_path}' to '{target_path}': {error_msg}"
            )
            raise MegaCmdError(
                "Error copying file '{file_path}' to '{target_path}'",
                response.return_code,
                response.stderr,
            )

        logger.info(f"Successfully copied '{file_path}' to '{target_path}'")
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_cp from '{file_path}' to '{target_path}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_cp from '{file_path}' to '{target_path}'."
        )


###############################################################################
async def mega_mv(file_path: str, target_path: str) -> None:
    """Move a file (or rename it)."""
    logger.info(f"Moving file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("mv", file_path, target_path)
    try:
        response = await run_megacmd(cmd)

        error_msg = response.err_output
        if error_msg:
            error_msg = response.stderr if response.stderr else response.stdout
            logger.error(
                f"Error moving file '{file_path}' to '{target_path}': {error_msg}"
            )
            # TODO Make this raise an exception
            return

        logger.info(f"Successfully moved '{file_path}' to '{target_path}'")
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_mv from '{file_path}' to '{target_path}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_mv from '{file_path}' to '{target_path}'."
        )


async def node_exists(file_path: str) -> bool:
    ls_result = await mega_ls(path=file_path)

    return len(ls_result) > 0


async def node_rename(file_path: str, new_name: str) -> None:
    assert file_path and new_name, (
        f"Cannot have empty args: `{file_path}`, `{new_name}`"
    )

    assert node_exists(file_path), f"Node path does not exist: `{file_path}`"

    fpath_pure: PurePath = PurePath(file_path)

    # Check if we are at the root path
    if str(fpath_pure) == "/":
        logger.error("Cannot rename root directory!")
        raise AssertionError("Cannot rename root directory!")
        return

    new_path: PurePath = PurePath(fpath_pure.parent / new_name)

    await mega_mv(file_path, str(new_path))


###############################################################################
async def mega_rm(file: str, flags: tuple[str, ...] | None) -> None:
    """Remove a file."""
    logger.info(f"Removing file {file} with flags: {flags} ")

    cmd: tuple[str, ...]

    cmd = ("rm", file, *flags) if flags else ("rm", file)

    try:
        response = await run_megacmd(cmd)

        error_msg = response.err_output
        if error_msg:
            logger.error(
                f"Error removing file '{file}' with flags '{flags}': {error_msg}"
            )
            return

        logger.info(f"Successfully removed '{file}' with flags '{flags}'")
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_rm for '{file}' with flags '{flags}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_rm for '{file}' with flags '{flags}'."
        )


###############################################################################
async def mega_put(
    local_path: str | tuple[str, ...],
    target_path: str = "/",
    queue: bool = True,
    create_remote_dir: bool = True,
):
    """Upload a file from the local system to a remote path.

    Args:
        'queue' refers to whether we should queue the file (prevents blocking).
        'create_remote_dir' will mean we create a directory on the remote if it does not yet exist.
    """
    if not local_path:
        logger.error("Error! Local file is not specified for upload.")
        raise MegaLibError("Local file is not specified for upload.", fatal=True)

    # Base of the command
    cmd = ["put"]

    # Optional arguments
    if queue:
        cmd.append("-q")

    if create_remote_dir:
        cmd.append("-c")

    # Add path to upload
    if isinstance(local_path, tuple):
        cmd.extend(local_path)
        logger.info(f"Uploading {len(local_path)} files: {local_path} to {target_path}")
    else:
        cmd.append(local_path)
        logger.info(f"Uploading file: {local_path} to {target_path}")

    # Remote destination
    cmd.append(target_path)

    try:
        response = await run_megacmd(tuple(cmd))

        error_msg = response.err_output
        if error_msg:
            logger.error(
                f"Error uploading files '{local_path}' to '{target_path}': {error_msg}"
            )
            return

        logger.info(
            f"Successfully initiated upload of '{local_path}' to '{target_path}'"
        )
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_put from '{local_path}' to '{target_path}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_put from '{local_path}' to '{target_path}'."
        )


def verify_handle(handle: str) -> bool:
    logger.info(f"Verifying handle: '{handle}'")

    if not handle:
        logger.error("Empty string cannot be a valid handle.")
        return False

    handle_len = len(handle)
    if handle_len < 8:
        logger.error("Handle should be longer than 8 characters.")
        return False

    if not handle.startswith("H:"):
        logger.error("Handles should start with 'H:'")
        return False

    if not handle.isalnum():
        logger.error("Handle received is not alpha-numerical.")
        return False

    return True


async def path_from_handle(handle: str) -> PurePath | None:
    assert verify_handle(handle), "Handle failed verification."

    # cd to root
    try:
        await mega_cd("/")
    except MegaCmdError as e:
        logger.error(f"Could not navigate to root directory: {e}")
        return None

    # Have to use the 'ls' command to get the full path of a handle
    cmd: list[str] = ["ls", handle]

    try:
        response = await run_megacmd(tuple(cmd))

        error_msg = response.err_output
        if error_msg:
            logger.error(f"Error verifying handle: '{handle}': {error_msg}")
            return

    except MegaCmdError as e:
        logger.error(f"MegaCmdError raised whilst verifying '{handle}': {e}")
        return None

    # Parse result
    try:
        split = response.stdout.partition("\n")
        # Parse Path
        path = PurePath(split[0])
    except pathlib.UnsupportedOperation as e:
        logger.error(f"Failed to parse path: {e}")
        return None
    except Exception as e:
        logger.error(f"Some other error occured: {e}")
        return None

    return path


async def mega_get_handle(
    target_path: str, handle: str, queue: bool = True, merge: bool = False
):
    """Download file using its HANDLE."""
    assert target_path, "You must specify a 'target_path'"
    assert handle, "'handle' not specified."
    assert verify_handle(handle), "Handle verification failed."

    cmd: list[str] = ["get"]
    if queue:
        cmd.append("-q")
        logger.debug("Queuing option enabled ('-q')")

    if merge:
        cmd.append("-m")
        logger.debug("Merge option enabled ('-m')")

    cmd.append(handle)

    io_path: Path = Path(target_path)

    if not io_path.exists():
        logger.info(f"Target path '{target_path}' does not exist, will create it.")
        io_path.mkdir(exist_ok=False, parents=True)
    else:
        logger.info(f"Target path '{target_path}' exists.")

    cmd.append(target_path)

    try:
        response = await run_megacmd(tuple(cmd))

        error_msg = response.err_output
        if error_msg:
            logger.error(f"Error downloading in '{target_path}': {error_msg}")
            return

        logger.info(f"Successfully initiated download of '{handle}' to '{target_path}'")
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_get_handle for '{handle}' to '{target_path}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_get_handle for '{handle}' to '{target_path}'."
        )


###############################################################################
async def mega_get(
    target_path: str,
    remote_path: str,
    is_dir: bool,
    queue: bool = True,
    merge: bool = False,
):
    """Download a file from the remote system to a local path.

    Args:
      'merge' == True means a folder of the same name on the local will be merged with
      the remote folder being downloaded.
      'is_dir' is a flag for whether the file downloaded is a directory or not.
      'queue' will add it to the downloads queue.
      'merge' will ensure local files are not overriden by the remote files and directories are merged instead.
    'merge=True' is only useful when the 'target_path' on the local filesystem already exists.
    """
    cmd: list[str] = ["get"]

    if not remote_path:
        logger.error("Error! Remote path not specified for download.")
        raise MegaLibError("Remote path not specified!", fatal=False)

    # Optional args
    if queue:
        cmd.append("-q")

    if is_dir and merge:
        cmd.append("-m")
        logger.info(
            f"Downloading directory '{remote_path}' to '{target_path}' with merge option."
        )
    elif is_dir:
        logger.info(f"Downloading directory '{remote_path}' to '{target_path}'.")
    else:
        logger.info(f"Downloading file '{remote_path}' to '{target_path}'.")

    # Append remote path
    cmd.append(remote_path)

    # TODO Check that the path is writable and has the correct permissions
    if not target_path:
        target_path = str(Path.home())
        logger.info(
            f"Target local path not specified, defaulting to home directory: {target_path}"
        )
    io_path: Path = Path(target_path)

    if not io_path.exists():
        logger.info(f"Target path '{target_path}' does not exist, will create it.")
        io_path.mkdir(exist_ok=False, parents=True)
    else:
        logger.info(f"Target path '{target_path}' exists.")

    cmd.append(target_path)

    try:
        response = await run_megacmd(tuple(cmd))

        error_msg = response.err_output
        if error_msg:
            logger.error(f"Error downloading in '{target_path}': {error_msg}")
            return

        logger.info(
            f"Successfully initiated download of '{remote_path}' to '{target_path}'"
        )
    except MegaCmdError as e:
        logger.error(
            f"MegaCmdError during mega_get from '{remote_path}' to '{target_path}': {e}"
        )
    except Exception:
        logger.exception(
            f"An unexpected error occurred during mega_get from '{remote_path}' to '{target_path}'."
        )


async def mega_df(human: bool = True) -> str | None:
    """Returns storage information for main folders.

    Args:
        human (bool): Request human readable file sizes or bytes.
    """
    cmd = ["df"]
    if human:
        cmd.append("-h")

    try:
        response = await run_megacmd(tuple(cmd))

        if response.err_output:
            logger.error(f"Error running 'df': {response.err_output}")
            return None

        return response.stdout
    except MegaCmdError as e:
        logger.error(f"MegaCmdError during mega_df: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during mega_df: {e}")


class LocationInfo(TypedDict):
    """Type definition for a single location entry."""

    name: str
    size_bytes: int
    files: int
    folders: int


class UsageSummary(TypedDict):
    """Type definition for the usage summary line."""

    used_bytes: int
    percentage: float
    total_bytes: int


class StorageOverview(TypedDict):
    """Dictionary representing parsed 'df' output."""

    locations: list[LocationInfo]
    usage_summary: UsageSummary | None  # Can be UsageSummary or None
    version_size_bytes: int | None  # Can be int or None


async def mega_df_dict() -> StorageOverview | None:
    """Returns overview of mounted folders as a dictionary."""
    output: str | None = await mega_df()
    if not output:
        logger.error("Received no output from 'mega_df'")
        return None

    logger.debug(f"'df' output:\n`{output}`")

    # Split by lines
    lines = output.strip().split("\n")

    # Initialise our dict
    parsed_data: StorageOverview = {
        "locations": [],
        "usage_summary": None,
        "version_size_bytes": None,
    }

    for line in lines:
        line = line.strip()
        if match := __DF_LOCATION_REGEXP.match(line):
            name, size, files, folders = match.groups()
            parsed_data["locations"].append(
                {
                    "name": name.strip(),
                    "size_bytes": int(size),
                    "files": int(files),
                    "folders": int(folders),
                }
            )
        elif match := __DF_SUMMARY_REGEXP.match(line):
            used, pct, total = match.groups()
            parsed_data["usage_summary"] = {
                "used_bytes": int(used),
                "percentage": float(pct),
                "total_bytes": int(total),
            }
        elif match := __DF_VERSIONS_REGEXP.match(line):
            parsed_data["version_size_bytes"] = int(match.group(1))

    return parsed_data


async def mega_mkdir(name: str, path: str | None = None) -> bool:
    """Create a new directory in the current path.

    Args:
        name (str): Name of directory.
    If name contains a slash e.g. 'folder1/folder2', the directories will be created.
        path (str | None): Absolute path to create directory. Defaults to 'None' which
        will create a path in the current directory.
    """
    clean_name = name.strip()
    if not clean_name:
        logger.error("Cannot create a directory with an empty name.")
        raise ValueError("Directory name cannot be empty.")

    # Base command. The -p flag creates parent directories as needed (e.g., for 'a/b/c').
    cmd = ["mkdir", "-p"]

    if path:
        # Remove whitespace and '/' from the right
        base_path = path.strip().rstrip("/")

        # If 'path' was '/'
        if not base_path:
            remote_path = f"/{clean_name}"
        else:
            remote_path = f"{base_path}/{clean_name}"

    # Else if no path was given
    else:
        remote_path = f"{clean_name}"

    cmd.append(remote_path)

    # Try running command
    try:
        logger.info(f"Attempting to create remote directory: '{remote_path}'")
        response = await run_megacmd(tuple(cmd))

        # megacmd often puts non-critical info or warnings in stderr.
        error_msg = response.err_output
        if error_msg:
            # Check for the common "already exists" case, which we treat as a success.
            if "already exists" in error_msg:
                logger.warning(f"Directory '{remote_path}' already exists.")
                return True
            else:
                # A real error occurred.
                logger.error(f"Error creating directory '{remote_path}': {error_msg}")
                return False

        logger.info(f"Successfully created directory: '{remote_path}'")
        return True

    except MegaCmdError as e:
        logger.error(f"MegaCmdError while creating directory '{remote_path}': {e}")
        raise
    except Exception:
        logger.exception(
            f"An unexpected error occurred while creating directory '{remote_path}'."
        )
        raise
