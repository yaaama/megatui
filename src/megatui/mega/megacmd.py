"""'megacmd' library provides an easy way of interacting with the 'mega-cmd' CLI."""

import asyncio
import logging
import math
import pathlib
import re
from collections import deque
from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import override

from megatui.mega.data import (
    DF_REGEXPS,
    DU_REGEXPS,
    LS_REGEXP,
    MEGA_COMMANDS_SUPPORTED,
    MEGA_DEFAULT_CMD_ARGS,
    MEGA_ROOT_PATH,
    MegaDiskFree,
    MegaDiskUsage,
    MegaPath,
)

MEGA_LOGTOFILE = False

if MEGA_LOGTOFILE:
    logging.basicConfig(
        filename="etc/megacmd.log",
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(funcName)s :: %(message)s",
    )


logger = logging.getLogger(__name__)

# Get the logger for the 'asyncio' library and set its level to WARNING.
# This will hide all INFO and DEBUG messages from asyncio.
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger.info("'megacmd' LOADED.")


# Response from running mega commands.
class MegaCmdResponse:
    __slots__ = ("return_code", "stderr", "stdout")

    stdout: str
    stderr: str | None
    return_code: int | None

    def __init__(self, *, stdout: str, stderr: str | None, return_code: int | None):
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

    @property
    def err_output(self) -> str | None:
        """Return stderr from command if failed, else None."""
        if self.failed:
            return self.stderr

        return None


class MegaLibError(Exception):
    """Custom exception for incorrect library usage."""

    def __init__(self, *, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal: bool = fatal
        logger.error(f"MegaLibError: {message} (Fatal: {fatal})")


class MegaCmdError(Exception):
    """Custom exception for mega-* command errors."""

    message: str
    response: MegaCmdResponse | None

    def __init__(
        self,
        message: str,
        response: MegaCmdResponse | None = None,
    ):
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
        assert self.response, "No response object."
        if self.response.stderr:
            return self.response.stderr

        return None

    @property
    def return_code(self) -> int:
        assert self.response, "No response object."
        if self.response.return_code:
            return self.response.return_code

        return 0


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
        "path",
        "size",
        "size_unit",
        "version",
    )

    name: str
    """Name of file/folder item."""
    path: MegaPath
    """ Full path of item. """
    bytes: int
    """ Size of file in BYTES, will be 0 for dirs."""
    size: float
    """ Size of file (human readable) """

    size_unit: MegaSizeUnits
    """ Unit for human readable size. """

    mtime: datetime
    """ Modification date + time of file."""

    ftype: MegaFileTypes
    """ Type of file. """

    version: int
    """ File version. """

    handle: str
    """ Unique handle. """

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

    @property
    def is_file(self) -> bool:
        return self.ftype == MegaFileTypes.FILE

    @property
    def is_dir(self) -> bool:
        return self.ftype == MegaFileTypes.DIRECTORY

    @staticmethod
    def get_size_in(bytes_used: int, unit: MegaSizeUnits) -> float:
        """Returns size of file in specified unit.
        Args: 'bytes_used' Size of file in bytes.
              'unit' Unit of size to convert bytes to.
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


# Alias
# MegaItems = list[MegaItem]
type MegaItems = tuple[MegaItem, ...]


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


def _build_megacmd_cmd(command: tuple[str, ...]) -> tuple[str, ...]:
    """Constructs a list containing the command to run and arguments.
    This list will transform something like: [ls, -l] into [mega-ls, -l]
    Also performs checking to see if the command is valid.
    """
    if not command:
        logger.critical("Command tuple cannot be empty.")
        raise MegaLibError(message="Command tuple cannot be empty.", fatal=True)

    if command[0] not in MEGA_COMMANDS_SUPPORTED:
        logger.critical(f"Unsupported command '{command[0]}' requested.")
        raise MegaLibError(
            message=f"The library does not support command '{command[0]}'.", fatal=True
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
    cmd_to_exec: tuple[str, ...] = _build_megacmd_cmd(command)
    logger.info(f"Running cmd:\n'{' '.join(cmd_to_exec)}'")
    cmd, *cmd_args = cmd_to_exec

    try:
        process = await asyncio.create_subprocess_exec(
            cmd,
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )

        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        cmd_response = MegaCmdResponse(
            stdout=stdout_str,
            stderr=None,  # Initialize stderr as None
            return_code=process.returncode,
        )

        if stderr_str:
            cmd_response.stderr = stderr_str
            logger.error(f"'{cmd[0]}' produced stderr: : {cmd_response.err_output}")
            raise MegaCmdError(message=f"Error running '{cmd[0]}'", response=cmd_response)

        # Handle cases where mega-* commands might print errors to stdout
        if process.returncode != 0:
            # Error printed by megacmd
            command_error_output = stderr_str if stderr_str else stdout_str
            # Formatted error
            formatted_err_msg = f"Non zero return code when executing '{cmd[0]}', ReturnCode='{process.returncode}', StdErr='{command_error_output}'"
            logger.error(formatted_err_msg)
            raise MegaCmdError(message=formatted_err_msg, response=cmd_response)

        logger.debug(f"OK : '{' '.join(cmd_to_exec)}' 'SUCCESS'.")
        return cmd_response

    except FileNotFoundError:
        logger.error(f"mega-cmd executable '{cmd_to_exec[0]}' not found. Is it in PATH?")
        raise MegaLibError(message=f"Command '{cmd_to_exec[0]}' not found.", fatal=True)


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
            logger.warning(f"Login status uncertain. Unexpected response: {response.stdout}")
            return False, f"Login status uncertain. Response: {response}"
    except MegaCmdError as e:
        logger.error(f"MegaCmdError during login check: {e}")
        return False, f"Login check failed due to command error: {e.message}"


###########################################################################


async def mega_ls(
    path: MegaPath | None = None, flags: tuple[str, ...] | None = None
) -> MegaItems:
    """Lists files and directories in a given MEGA path using 'mega-ls -l' (sizes in bytes).

    Args:
        path (str): The MEGA path to list (e.g., "/", "/Backups"). Defaults to "/".
        flags (tuple[str, ...], optional): Additional flags for mega-ls.

    Returns:
        list[MegaItem]: A list of MegaItem objects representing the contents.
                        Returns an empty list if the path is invalid or an error occurs.
    """
    cmd: list[str] = ["ls"]
    cmd.extend(MEGA_DEFAULT_CMD_ARGS["ls"])

    if flags:
        cmd.extend(flags)

    if not path:
        logger.debug("Target path not specified: Listing nodes of current path.")
        target_path = await mega_pwd()
    else:
        target_path = path

    logger.info(f"Listing contents of MEGA path: {target_path}")

    cmd.append(target_path.str)
    response: MegaCmdResponse = await run_megacmd(tuple(cmd))

    items: deque[MegaItem] = deque()

    lines = response.stdout.strip().split("\n")
    # Remove first element (it will be the header line)
    del lines[0]

    # Handle empty output
    if not lines or not lines[0].strip():
        logger.info(f"No items found in '{target_path}' or dir is empty.")
        return ()

    # Parse the lines we receive
    for line in lines:
        # Parse each line of the ls output
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
            # logger.debug(f"Parsed directory: {__file_info[-1]}")
            parsed_tuple = (MegaFileTypes.DIRECTORY, __file_info)

        else:
            # Else it is a regular file
            # logger.debug(f"Parsed file: {__file_info[-1]}")
            parsed_tuple = (MegaFileTypes.FILE, __file_info)

        # Tuple values
        _file_type, (_flags, _vers, _size, _date, _handle, _name) = parsed_tuple

        # Values to convert
        mtime_str: str = f"{_date}"
        try:
            mtime_obj = datetime.fromisoformat(mtime_str)
        except ValueError:
            logger.fatal(f"Failed to parse time: {mtime_str}")
            raise MegaLibError(message=f"Failed to parse time: {mtime_str}")

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
                path=MegaPath(target_path, _name),
                size=item_size,
                mtime=mtime_obj,
                ftype=_file_type,
                version=version,
                handle=_handle,
            )
        )
    logger.info(f"Successfully listed {len(items)} items in '{target_path}'.")
    _debug_files = [file.name for file in items if file.is_file]
    _debug_dirs = [file.name for file in items if file.is_dir]
    logger.debug(
        f"LOADED '{len(_debug_dirs)}' DIRS and '{len(_debug_files)}' FILES in '{target_path}'."
    )
    return tuple(items)


###############################################################################


async def mega_du(
    dir_path: MegaPath | None,
    include_version_info: bool = False,
    # TODO Integrate units param into func
    units: MegaSizeUnits | None = None,  # pyright: ignore[reportUnusedParameter]
):
    """Get disk usage.
    'dir_path' is the path of the directory or if None, the current directory.
    'include_version_info' includes sizes of versions.
    'units' must be one of the values specified by SIZE_UNIT enum.
    """
    # Prepare our command
    cmd: list[str] = ["du"]

    if not dir_path:
        dir_path = MEGA_ROOT_PATH

    if include_version_info:
        cmd.append("--versions")

    cmd.append(dir_path.str)

    response = await run_megacmd(tuple(cmd))

    logger.debug(f"Successfully ran 'du' for path '{dir_path}'")

    # TODO Finish this off by parsing the headers (we can discard) and the file paths and size
    output = response.stdout.splitlines()

    assert len(output) > 3, "Output of 'du' should be 3 lines or more."

    # We can ignore the header
    _header = DU_REGEXPS["header"].match(output[0])

    file_line_match = DU_REGEXPS["location"].match(output[1])
    assert file_line_match, f"No matches for du file lines: {file_line_match}"

    _filename, _size = file_line_match.groups()

    assert _filename
    assert _size
    return MegaDiskUsage(location=MegaPath(_filename), size_bytes=int(_size))


###############################################################################
async def mega_cd(target_path: MegaPath | None):
    """Change directories."""
    if not target_path:
        logger.debug("No target path. Will cd to root")
        target_path = MEGA_ROOT_PATH

    logger.info(f"Changing directory to {target_path}")

    cmd: list[str] = ["cd", target_path.str]
    await run_megacmd(tuple(cmd))
    logger.info(f"Successfully changed directory to '{target_path}'")


async def mega_pwd() -> MegaPath:
    """Returns current working directory."""
    logger.info("Getting current working directory.")

    cmd: tuple[str, ...] = ("pwd",)
    response = await run_megacmd(cmd)

    pwd_path = MegaPath(response.stdout.strip())
    return pwd_path


###############################################################################
async def mega_cd_ls(
    target_path: MegaPath | None, ls_flags: tuple[str, ...] | None = None
) -> MegaItems:
    """Change directories and ls."""
    if not target_path:
        target_path = MegaPath("/")

    logger.debug(f"Changing directory and listing contents for {target_path}")

    results = await asyncio.gather(mega_cd(target_path), mega_ls(target_path, ls_flags))

    items: MegaItems = results[1]

    logger.debug(f"Finished cd and ls for {target_path}. Found {len(items)} items.")

    return items


###############################################################################
###############################################################################
async def mega_cp(file_path: MegaPath, target_path: MegaPath) -> None:
    """Copy file from 'file_path' to 'target_path'."""
    logger.info(f"Copying file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("cp", file_path.str, target_path.str)
    await run_megacmd(cmd)

    logger.info(f"Successfully copied '{file_path}' to '{target_path}'")


###############################################################################
async def mega_mv(file_path: MegaPath, target_path: MegaPath) -> None:
    """Move a file (or rename it)."""
    logger.info(f"Moving file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("mv", file_path.str, target_path.str)
    await run_megacmd(cmd)

    logger.info(f"Successfully moved '{file_path}' to '{target_path}'")


async def mega_node_exists(node_path: MegaPath) -> bool:
    """Check for the existence of a node using its path."""
    try:
        _ = await mega_ls(path=node_path)
    except MegaCmdError:
        return False

    return True


async def mega_node_rename(file_path: MegaPath, new_name: str) -> None:
    """Rename a node.

    Args:
        file_path: Path of node to rename.
        new_name: New name for node.
    """
    assert file_path and new_name, f"Cannot have empty args: `{file_path}`, `{new_name}`"
    exists = await mega_node_exists(file_path)
    if not exists:
        logger.warning(f"Path '{file_path}' does not exist!")
        raise MegaCmdError(f"Path '{file_path}' does not exist!", response=None)

    # Check if we are at the root path
    if file_path.match("/"):
        logger.error("Cannot rename root directory!")
        raise MegaCmdError("Cannot rename root directory!", None)

    new_path: MegaPath = MegaPath(file_path.parent / new_name)

    await mega_mv(file_path, new_path)


###############################################################################
async def mega_rm(fpath: MegaPath, flags: tuple[str, ...] | None) -> None:
    """Remove a file."""
    str_path = fpath.str
    logger.info(f"Removing file {fpath!s} with flags: {flags} ")

    cmd: list[str] = ["rm", str_path, *flags] if flags else ["rm", str_path]

    await run_megacmd(tuple(cmd))

    logger.info(f"Successfully removed '{fpath}' with flags '{flags}'")


###############################################################################
async def mega_put(
    local_paths: Path | Iterable[Path],
    target_path: MegaPath | None = None,
    queue: bool = True,
    create_remote_dir: bool = True,
):
    """Upload a file from the local system to a remote path.

    Args:
        'queue' refers to whether we should queue the file (prevents blocking).
        'create_remote_dir' will mean we create a directory on the remote if it does not yet exist.
    """
    if not local_paths:
        logger.error("Error! Local file is not specified for upload.")
        raise MegaLibError(message="Local file is not specified for upload.", fatal=True)

    if not target_path:
        target_path = await mega_pwd()

    path_str = str(target_path)
    # Base of the command
    cmd = ["put"]

    # Optional arguments
    if queue:
        cmd.append("-q")

    if create_remote_dir:
        cmd.append("-c")

    # Add path to upload
    # This correctly handles the ambiguity of Path also being an Iterable.
    if isinstance(local_paths, Path):
        logger.info(f"Uploading file: {local_paths} to {path_str}")
        # Convert the single Path to a string before appending.
        cmd.append(str(local_paths))
    else:
        # If it's not a single Path, it must be our intended Iterable[Path].
        # Convert to a list to safely get its length and prevent issues with one-time iterators.
        paths_to_upload = [str(p) for p in local_paths]
        logger.info(f"Uploading {len(paths_to_upload)} files to {path_str}")
        # Extend the command list with the new list of strings.
        cmd.extend(paths_to_upload)

    # Remote destination
    cmd.append(path_str)

    await run_megacmd(tuple(cmd))

    logger.info(f"Successfully initiated upload of '{local_paths}' to '{target_path}'")


def _verify_handle_structure(handle: str) -> bool:
    """Verifies the structure of a handle.

    Args:
        handle: The handle string to verify.

    Returns:
        True if the handle has a valid structure, False otherwise.
    """
    logger.info(f"Verifying handle: '{handle}'")

    match handle:
        case "":
            logger.error("Empty string cannot be a valid handle.")
            return False
        case str() if len(handle) < 8:
            logger.error("Handle should be longer than 8 characters.")
            return False
        case str() if not handle.startswith("H:"):
            logger.error("Handles should start with 'H:'")
            return False
        case _:
            pass

    content = handle[2:]
    if not content.isalnum():
        logger.error("Handle content is not alpha-numerical.")
        return False

    return True


async def path_from_handle(handle: str) -> MegaPath | None:
    assert _verify_handle_structure(handle), "Handle does not conform to structure."

    # cd to root
    await mega_cd(MEGA_ROOT_PATH)

    # Have to use the 'ls' command to get the full path of a handle
    cmd: list[str] = ["ls", handle]

    response = await run_megacmd(tuple(cmd))

    # Parse result
    try:
        split = response.stdout.partition("\n")
        # Parse Path (first partition)
        path = MegaPath(split[0])
    except pathlib.UnsupportedOperation as e:
        logger.error(f"Failed to parse path: {e}")
        raise MegaCmdError(message=f"Could not parse path from handle `{handle}` :: {e}")

    return path


async def mega_get_from_handle(
    target_path: str | Path, handle: str, queue: bool = True, merge: bool = False
):
    """Download file using its HANDLE to `target_path`."""
    assert target_path, "You must specify a 'target_path'"
    assert handle, "'handle' not specified."
    assert _verify_handle_structure(handle), "Handle verification failed."

    cmd: list[str] = ["get"]

    if queue:
        cmd.append("-q")

    if merge:
        cmd.append("-m")
        logger.debug("Merge option enabled ('-m')")

    cmd.append(handle)

    io_path = Path(target_path) if not isinstance(target_path, Path) else target_path

    if not io_path.exists():
        logger.info(f"Target path '{target_path}' does not exist, will create it.")
        io_path.mkdir(exist_ok=False, parents=True)

    cmd.append(str(target_path))

    await run_megacmd(tuple(cmd))

    logger.info(f"Successfully initiated download of '{handle}' to '{target_path}'")


###############################################################################
async def mega_get(
    target_path: str | Path, remote_path: str, queue: bool = True, merge: bool = False
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
        raise MegaLibError(message="Remote path not specified!", fatal=False)

    # Optional args
    if queue:
        cmd.append("-q")

    if merge:
        cmd.append("-m")
        logger.info(f"Downloading '{remote_path}' to '{target_path}' using '-m' (merge)")
    else:
        logger.info(f"Downloading node '{remote_path}' to '{target_path}'")

    # Append remote path
    cmd.append(remote_path)

    # TODO Check that the path is writable and has the correct permissions
    if not target_path:
        target_path = str(Path.home())
        logger.info(
            f"Target local path not specified, defaulting to home directory: {target_path}"
        )

    io_path = Path(target_path) if not isinstance(target_path, Path) else target_path

    if not io_path.exists():
        logger.info(f"Target path '{target_path}' does not exist, will create it.")
        io_path.mkdir(exist_ok=False, parents=True)

    cmd.append(str(target_path))

    await run_megacmd(tuple(cmd))

    logger.info(f"Successfully initiated download of '{remote_path}' to '{target_path}'")


async def mega_df(human: bool = True) -> MegaDiskFree | None:
    """Returns storage information for main folders.

    Args:
        human (bool): Request human readable file sizes or bytes.
    """
    cmd = ["df"]
    if human:
        cmd.append("-h")

    response = await run_megacmd(tuple(cmd))

    return _parse_df(response.stdout)


def _parse_df(df_output: str) -> MegaDiskFree | None:
    """Returns overview of mounted folders as a dictionary."""
    if not df_output:
        logger.error("Received no output from 'mega_df'")
        return None

    logger.debug(f"'df' output:\n`{df_output}`")

    # Split by lines
    lines = df_output.strip().split("\n")

    locations_list: list[MegaDiskFree.LocationInfo] = []
    summary_data: MegaDiskFree.UsageSummary | None = None
    versions_size: int | None = None

    for line_base in lines:
        line = line_base.strip()

        # Skip over empty lines or header seperators
        if (not line) or line.startswith("---"):
            continue

        for key, pattern in DF_REGEXPS.items():
            if match := pattern.match(line):
                if key == "location":
                    name, size, files, folders = match.groups()
                    locations_list.append(
                        MegaDiskFree.LocationInfo(
                            name=name.strip(),
                            size_bytes=int(size),
                            files=int(files),
                            folders=int(folders),
                        )
                    )
                elif key == "summary":
                    used, pct, total = match.groups()
                    summary_data = MegaDiskFree.UsageSummary(
                        used_bytes=int(used),
                        percentage=float(pct),
                        total_bytes=int(total),
                    )
                elif key == "versions":
                    versions_size = int(match.group(1))
                break

    return MegaDiskFree(
        locations=locations_list,
        usage_summary=summary_data,
        version_size_bytes=versions_size,
    )


async def mega_mkdir(name: str, path: MegaPath | None = None) -> bool:
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

    remote_path = MegaPath(path, clean_name).str if path else f"{clean_name}"

    cmd.append(remote_path)

    # Try running command
    try:
        logger.info(f"Attempting to create remote directory: '{remote_path}'")
        await run_megacmd(tuple(cmd))

        logger.info(f"Successfully created directory: '{remote_path}'")
        return True

    except MegaCmdError as e:
        logger.error(f"MegaCmdError while creating directory '{remote_path}': {e}")
        return False
