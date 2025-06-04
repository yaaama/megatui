import asyncio
import re
import subprocess
from enum import Enum
from pathlib import PurePath, Path

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
}


class MegaLibError(Exception):
    """Custom exception for incorrect library usage."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal: bool = fatal


class MegaCmdError(Exception):
    """Custom exception for mega-* command errors."""

    def __init__(
        self, message: str, return_code: int | None = None, stderr: str | None = None
    ):
        super().__init__(message)
        self.return_code: int | None = return_code
        self.stderr: str | None = stderr


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
            return "?"


class MegaItem:
    # Class Variables #################################################
    __slots__ = (
        "name",
        "parent_path",
        "bytes",
        "size",
        "size_unit",
        "mtime",
        "ftype",
        "version",
        "handle",
    )

    name: str  # Name of item
    """Name of file/folder item."""

    parent_path: str
    """ Path of parent directory of file/directory. """

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

        from math import log

        self.name = name
        self.parent_path = parent_path
        self.bytes = size
        self.mtime = mtime
        self.ftype = ftype
        self.version = version
        self.handle = handle

        if (size == 0) or (self.ftype == MegaFileTypes.DIRECTORY):
            self.size = 0.0
            self.size_unit = MegaSizeUnits.B
            return

        # Calculate human friendly sizing
        unit_index: int = min(int(log(self.bytes, 1024)), len(MegaSizeUnits) - 1)

        divisor: int
        if unit_index == 0:
            divisor = 1
        else:
            # calculate 1024^unit_index using shifts
            # 1 << 10 is 1024 (2^10)
            # 1 << (10 * unit_index) is (2^10)^unit_index = 1024^unit_index
            divisor = 1 << (10 * unit_index)

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

    def get_size_in(self, unit: MegaSizeUnits) -> int:
        """Returns size of file in specified unit."""
        match unit:
            case MegaSizeUnits.B:
                return self.bytes
            # Bit shifting
            case MegaSizeUnits.KB:
                return self.bytes >> 10
            case MegaSizeUnits.MB:
                return self.bytes >> 20
            case MegaSizeUnits.GB:
                return self.bytes >> 30
            case MegaSizeUnits.TB:
                return self.bytes >> 40


# Alias
MegaItems = list[MegaItem]


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

    __slots__ = ("stdout", "stderr", "return_code")

    stdout: str
    stderr: str | None
    return_code: int | None

    def __init__(self, stdout: str, stderr: str | None, return_code: int | None):
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code

    def failed(self) -> bool:
        if (self.return_code) != 0:
            return True
        if self.stderr:
            return True
        return False


# Alias
MCResponse = MegaCmdResponse

# Default 'ls -l --show-handles' regular expression.
LS_REGEXP = re.compile(
    r"^([^\s]{4})\s+"  #  Flags: Can be either alphabetical or a hyphen
    + r"(\d+|-)\s+"  # Version ('-' or number), skip whitespace
    + r"(\d+|-)\s+"  # Size (digits for bytes or '-'), skip whitespace
    + r"(\d{2}\w{3}\d{4})\s+"  # Date (DDMonYYYY), skip whitespace
    + r"(\d{2}:\d{2}:\d{2})\s+"  # Time (HH:MM:SS), skip whitespace
    + r"(H:[^\s]+)\s+"  # File handle ('H:xxxxxxxx')
    + r"(.+)$"  # Filename (everything else)
)


def build_megacmd_cmd(command: tuple[str, ...]) -> tuple[str, ...]:
    """
    Constructs a list containing the command to run and arguments.
    This list will transform something like: [ls, -l] into [mega-ls, -l]
    Also performs checking to see if the command is valid.
    """

    if not command:
        raise MegaLibError("Command tuple cannot be empty.", fatal=True)

    if command[0] not in MEGA_COMMANDS_SUPPORTED:
        raise MegaLibError(
            f"The library does not support command '{command[0]}'.", fatal=True
        )

    # if 'command' is ('ls', '-l', '--tree'), then 'megacmd' name will be 'mega-ls'
    megacmd_name: str = f"mega-{command[0]}"

    # Get all elements from the second element onwards using slice [1:]
    remaining_args: tuple[str, ...] = command[1:]

    # (megacmd_name, followed by all elements in remaining_args)
    final: tuple[str, ...] = (megacmd_name, *remaining_args)

    return final


###############################################################################
async def run_megacmd(command: tuple[str, ...]) -> MegaCmdResponse:
    """
    Runs a specific mega-* command (e.g., mega-ls, mega-whoami)
    and returns MegaCmdResponse.

    Args:
        command (tuple[str, ...]): The base command name and its arguments.

    """

    # Construct the actual executable name (e.g., "mega-ls")
    cmd_to_exec: tuple[str, ...] = build_megacmd_cmd(command)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_to_exec,
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

        # Handle cases where mega-* commands might print errors to stdout
        if process.returncode != 0:
            error_message = stderr_str if stderr_str else stdout_str
            raise MegaCmdError(
                f"Command '{' '.join(command)}' failed: {error_message}",
                return_code=process.returncode,
                stderr=stderr_str or stdout_str,  # Use stderr if available
            )

        return megacmd_obj

    except FileNotFoundError:
        raise MegaCmdError(
            f"Command '{cmd_to_exec[0]}' not found.",
            stderr=f"{cmd_to_exec[0]} not found",
        )
    except Exception as e:
        # *** RAISE instead of print/return error response ***
        # Wrap unexpected errors
        raise MegaCmdError(f"Unexpected error running '{cmd_to_exec[0]}': {e}") from e


###########################################################################
async def mega_start_server():
    """
    Starts the mega server in the background.
    """
    pass


###########################################################################
async def check_mega_login() -> tuple[bool, str | None]:
    """
    Checks if the user is logged into MEGA using 'mega-whoami'.

    Returns:
        tuple[bool, str | None]: A tuple containing:
            - bool: True if logged in, False otherwise.
            - str | None: The username (email) if logged in, otherwise a message
                          indicating the status or error.
    """
    response: MegaCmdResponse = await run_megacmd(command=("whoami",))

    if response.return_code == 0 and response.stderr is not None:
        return False, "You are not logged in."

    # Extract username
    if response.return_code == 0 and response.stderr is None and "@" in response.stdout:
        username = response.stdout.strip()
        return True, username

    elif response.stderr:
        return False, f"Error: {response.stderr}"

    elif (
        "ERROR: Not logged in" in response.stdout or "Not logged in" in response.stdout
    ):
        return False, "Not logged in (detected in stdout)"
    elif response.return_code != 0:
        error_msg = response.stderr if response.stderr else response.stdout
        return False, f"Login check failed (Code: {response.return_code}): {error_msg}"
    else:
        return False, f"Login status uncertain. Response: {response}"


###########################################################################


def parse_ls_output(line: str) -> tuple[MegaFileTypes, tuple[str, ...]] | None:
    """
    Parse output of 'mega-ls' and return a tuple of data.
    Returned tuple will have first field as 'True' if the file is a directory, else false.
    Other fields

    """
    _line: str = line.strip()

    fields = LS_REGEXP.match(_line)

    if not fields:
        return None

    # Get field values from our regexp matches
    file_info: tuple[str, ...]
    file_info = fields.groups()
    # _flags, _vers, _size, _date, _time, _handle, _name = fields.groups()

    # If flags (first elem) contains 'd' as first elem, then return True
    if file_info[0][0] == "d":
        return (MegaFileTypes.DIRECTORY, file_info)

    else:
        return (MegaFileTypes.FILE, file_info)


async def mega_ls(
    path: str | None = "/", flags: tuple[str, ...] | None = None
) -> MegaItems:
    """
    Lists files and directories in a given MEGA path using 'mega-ls -l' (sizes in bytes).

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
        print(f"Listing contents of MEGA path: {target_path}")

    else:
        target_path = "."
        curr_path_for_items = "/"
        print("Listing contents of current path.")

    cmd: list[str] = [
        "ls",
        "-l",
        "--show-handles",
    ]

    if flags:
        cmd.extend(flags)

    cmd.append(target_path)

    response: MCResponse = await run_megacmd(tuple(cmd))

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error listing files in '{target_path}': {error_msg}")
        return []

    items: MegaItems = []
    lines = response.stdout.strip().split("\n")
    # Pop out the first element (it will be the header line)
    lines.pop(0)

    # Handle empty output
    if not lines or not lines[0].strip():
        return []

    # Parse the lines we receive
    for line in lines:

        parsed_tuple = parse_ls_output(line)
        if parsed_tuple is None:
            print(
                f"Warning: Could not parse ls line: '{line}'"
            )  # Log unparseable lines
            continue

        _file_type, (_flags, _vers, _size, _date, _time, _handle, _name) = parsed_tuple

        # Values to convert
        mtime_str: str = f"{_date} {_time}"
        handle_str: str
        item_size: int = 0
        version: int = 0

        if _file_type == MegaFileTypes.FILE:
            try:
                item_size = int(_size)
                version = int(_vers)
            except ValueError:
                # Log this unexpected case, but maybe default to None or 0
                print(
                    f"Warning: Could not convert size '{_size}' to int for item '{_name}'"
                )
                item_size = 0

        # This must be a directory
        else:
            item_size = 0
            version = 0

        # Parse the handle
        handle_str = _handle[2:] if _handle.startswith("H:") else _handle

        items.append(
            MegaItem(
                name=_name,
                parent_path=curr_path_for_items,
                size=item_size,
                mtime=mtime_str,
                ftype=_file_type,
                version=version,
                handle=handle_str,
            )
        )
    return items


###############################################################################
async def mega_du(
    dir: str = "/",
    recurse: bool = True,
    units: MegaSizeUnits = MegaSizeUnits.MB,
):
    """
    Get disk usage.
    If recurse 'True', then calculate disk usage for all subfolders too.
    'units' must be one of the values specified by SIZE_UNIT enum.
    """
    pass


###############################################################################
async def mega_cd(target_path: str = "/"):
    """
    Change directories.
    """
    print(f"CDing to {target_path}")

    cmd: list[str] = ["cd", target_path]
    response = await run_megacmd(tuple(cmd))

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error changing directories to '{target_path}': {error_msg}")
        return


async def mega_pwd() -> str:
    """
    Change directories.
    """
    print("Printing working directory.")

    cmd: tuple[str, ...] = ("pwd",)
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error printing working directory: {error_msg}")
        return ""

    return response.stdout.strip()


###############################################################################
async def mega_cd_ls(
    target_path: str | None = "/", ls_flags: tuple[str, ...] | None = None
) -> MegaItems:
    """
    Change directories and ls.
    """
    effective_target_path = target_path if target_path else "/"
    print(f"cdls to {effective_target_path}")

    await mega_cd(effective_target_path)
    items = await mega_ls(effective_target_path, ls_flags)

    return items


###############################################################################
async def mega_cp(file_path: str, target_path: str) -> None:
    """
    Copy file from 'file_path' to 'target_path'
    """
    print(f"Copying file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("cp", file_path, target_path)
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error copying file '{file_path}' to '{target_path}': {error_msg}")
        return  # Consider raising

    print(f"Successfully copied '{file_path}' to '{target_path}'")


###############################################################################
async def mega_mv(file_path: str, target_path: str) -> None:
    """
    Move a file (or rename it).
    """
    print(f"Moving file {file_path} to {target_path}")

    cmd: tuple[str, ...] = ("mv", file_path, target_path)
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error moving file '{file_path}' to '{target_path}': {error_msg}")
        # TODO Make this raise an exception
        return

    print(f"Successfully moved '{file_path}' to '{target_path}'")


###############################################################################
async def mega_rm(file: str, flags: tuple[str, ...] | None) -> None:
    """
    Remove a file.
    """

    print(f"Removing file {file} with flags: {flags} ")

    cmd: tuple[str, ...]

    if flags:
        cmd = ("rm", file, *flags)
    else:
        cmd = ("rm", file)

    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error removing file '{file}' with flags '{flags}': {error_msg}")
        return

    print(f"Successfully removed '{file}' with flags '{flags}'")


###############################################################################
async def mega_put(
    local_path: str | tuple[str, ...],
    target_path: str = "/",
    queue: bool = True,
    create_remote_dir: bool = True,
):
    """
    Upload a file from the local system to a remote path.

    Args:
        'queue' refers to whether we should queue the file (prevents blocking).
        'create_remote_dir' will mean we create a directory on the remote if it does not yet exist.
    """

    if not local_path:
        print("Error! We need a local file to upload.")
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
    else:
        cmd.append(local_path)

    # Remote destination
    cmd.append(target_path)

    response = await run_megacmd(tuple(cmd))

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error uploading files '{local_path}' to '{target_path}': {error_msg}")
        return


###############################################################################
async def mega_get(
    target_path: str,
    remote_path: str,
    is_dir: bool,
    queue: bool = True,
    merge: bool = True,
):
    """
    Download a file from the remote system to a local path.

    Args:
    'merge' == True means a folder of the same name on the local will be merged with
    the remote folder being downloaded.
    'is_dir' is a flag for whether the file downloaded is a directory or not.
    'queue' will add it to the downloads queue.
    'merge' will ensure local files are not overriden by the remote files and directories are merged instead.
    """

    cmd: list[str] = ["get"]

    if not remote_path:
        print("Error! We need a remote path.")
        raise MegaLibError("Remote path not specified!", fatal=False)

    # Optional args
    if queue:
        cmd.append("-q")

    if is_dir and merge:
        cmd.append("-m")

    # Append remote path
    cmd.append(remote_path)

    # TODO Check that the path is writable and has the correct permissions
    if not target_path:
        target_path = str(Path.home())

    cmd.append(target_path)

    response = await run_megacmd(tuple(cmd))

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error downloading in '{target_path}': {error_msg}")
        return
