import asyncio
from enum import Enum
import math
import os
import re
import shlex
import subprocess
from dataclasses import dataclass


class MegaCmdError(Exception):
    """Custom exception for mega-* command errors."""

    def __init__(
        self, message: str, return_code: int | None = None, stderr: str | None = None
    ):
        super().__init__(message)
        self.return_code: int | None = return_code
        self.stderr: str | None = stderr


class FILE_TYPE(Enum):
    """File types."""

    DIRECTORY = 0
    FILE = 1


class F_SizeUnit(Enum):
    """File size units."""

    B = 0
    KB = 1
    MB = 2
    GB = 3
    TB = 4

    # Helper to get the string representation used in the size calculation
    def get_unit_str(self):
        _unit_strings = ["B", "KB", "MB", "GB", "TB"]  # Match the order in the Enum
        try:
            return _unit_strings[self.value]
        # Raise an error for unknown units
        except IndexError:
            return "?"


@dataclass
class MegaItem:
    name: str  # Name of item
    size: int  # Size of the file item (in bytes)
    mtime: str  # Parse into date if needed
    ftype: FILE_TYPE  # 'd' for dir, 'f' for file

    def is_file(self) -> bool:
        if self.ftype == FILE_TYPE.FILE:
            return True
        return False


    def is_dir(self) -> bool:
        if self.ftype == FILE_TYPE.DIRECTORY:
            return True
        return False


    def ftype_str(self) -> str:
        """Returns a string for the 'type'."""
        match self.ftype:
            case FILE_TYPE.DIRECTORY:
                return "D"
            case FILE_TYPE.FILE:
                return "F"


    def get_size(self) -> tuple[float, F_SizeUnit]:
        """Returns size in a human-friendly unit."""

        # Calculate the logarithm base 1024 to find the scale
        # math.log(num_bytes, 1024) gives the power of 1024
        # Floor gives the index for the correct unit
        # Example: log(2048, 1024) = 1.0 -> index 1 (KB)
        # Example: log(1000, 1024) = 0.99... -> index 0 (B)
        # Example: log(xxxx, 1024) = 4... -> index 4 (TB)
        # We cap the index at the maximum available unit
        unit_index: int = min(int(math.log(self.size, 1024)), len(F_SizeUnit) - 1)

        # Calculate the divisor using bit shift (1 << (10 * unit_index))
        # This is equivalent to 1024 ** unit_index or 2**(10 * unit_index)
        divisor: int
        if unit_index == 0:
            divisor = 1
        else:
            # calculate 1024^unit_index using shifts
            # 1 << 10 is 1024 (2^10)
            # 1 << (10 * unit_index) is (2^10)^unit_index = 1024^unit_index
            divisor = 1 << (10 * unit_index)

        # Perform floating point division for the final readable value
        scaled_value: float = float(self.size) / divisor
        return (scaled_value, F_SizeUnit(unit_index))

    def get_size_in_units(self, unit: F_SizeUnit) -> int:
        """Returns size in units of 'unit'"""
        match unit:
            case F_SizeUnit.B:
                return self.size
            # Bit shifting
            case F_SizeUnit.KB:
                return self.size >> 10
            case F_SizeUnit.MB:
                return self.size >> 20
            case F_SizeUnit.GB:
                return self.size >> 30
            case F_SizeUnit.TB:
                return self.size >> 40


# Alias
MegaItems = list[MegaItem]


# Response from running mega commands.
@dataclass
class MegaCmdResponse:
    stdout: str
    stderr: str | None
    return_code: int | None


# Alias
MCResponse = MegaCmdResponse

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
}


# Default 'ls -l' regular expression.
LS_REGEXP = re.compile(
    r"^([d-])"  # Group 1: Type ('d' or '-')
    + r"\S+\s+"  # Matches permissions ('---'), skip whitespace
    + r"(\d+|-)\s+"  # Group 2: Version ('-' or number), skip whitespace
    + r"(\d+|-)\s+"  # Group 3: Size (digits for bytes or '-'), skip whitespace
    + r"(\d{2}\w{3}\d{4})\s+"  # Group 4: Date (DDMonYYYY), skip whitespace
    + r"(\d{2}:\d{2}:\d{2})\s+"  # Group 5: Time (HH:MM:SS), skip whitespace
    + r"(.+)$"  # Group 6: Filename (everything else)
)


###############################################################################
async def run_megacmd(command: list[str]) -> MegaCmdResponse:
    """
    Runs a specific mega-* command (e.g., mega-ls, mega-whoami)
    and returns MegaCmdResponse.

    Args:
        command (str): The base command name (e.g., "ls", "whoami").
        *args (str): Arguments and flags for the command.
    """

    # Construct the actual executable name (e.g., "mega-ls")

    # Form the exectuable name
    executable: str = f"mega-{command[0]}"

    # Check if the command is supported
    if command[0] not in MEGA_COMMANDS_SUPPORTED:
        print(f"Command '{command[0]}' is not supported.")
        exit(1)

    command.pop(0)
    cmd: list[str] = [executable]

    # Add the rest of the items
    cmd.extend(command)

    print(
        f"Running command: {' '.join(shlex.quote(c) for c in command)}"
    )  # Debug print

    try:
        process = await asyncio.create_subprocess_exec(
            executable, *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
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
        # *** RAISE instead of print/return error response ***
        raise MegaCmdError(
            f"Command '{executable}' not found.", stderr=f"{executable} not found"
        )
    except Exception as e:
        # *** RAISE instead of print/return error response ***
        # Wrap unexpected errors
        raise MegaCmdError(f"Unexpected error running '{executable}': {e}") from e


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
    response: MegaCmdResponse = await run_megacmd(command=["whoami"])

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
async def mega_ls(path: str | None = "/", flags: list[str] | None = None) -> MegaItems:
    """
    Lists files and directories in a given MEGA path using 'mega-ls -l' (sizes in bytes).

    Args:
        path (str): The MEGA path to list (e.g., "/", "/Backups"). Defaults to "/".

    Returns:
        list[MegaItem]: A list of MegaItem objects representing the contents.
                        Returns an empty list if the path is invalid or an error occurs.
    """
    if path:
        target_path: str = path if path.startswith("/") else f"/{path}"
        print(f"Listing contents of MEGA path: {target_path}")
    else:
        target_path = "."
        print("Listing contents of current path.")

    cmd: list[str] = ["ls", "-l"]

    if flags:
        cmd.extend(flags)

    cmd.append(target_path)

    response: MCResponse = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error listing files in '{target_path}': {error_msg}")
        return []

    items: MegaItems = []
    lines = response.stdout.strip().split("\n")
    header_skipped = False

    # Parse the lines we receive
    for line in lines:
        line = line.strip()
        # Skip this line if it is empty space
        if not line:
            continue
        if not header_skipped and line.startswith("FLAGS VERS"):  # Skip header
            header_skipped = True
            continue
        if not header_skipped:
            print(f"Warning: Skipping unexpected line before header: '{line}'")
            continue

        # Use our regex to match the output headers
        match = LS_REGEXP.match(line)
        if not match:
            print(f"Warning: Could not parse line: '{line}'")
            continue

        # Assign variables from our regexp matches
        type_char, _version, size_str, date_str, time_str, name_str = match.groups()

        item_type = FILE_TYPE.DIRECTORY if type_char == "d" else FILE_TYPE.FILE
        mtime_str = f"{date_str} {time_str}"

        # --- Parse Size ---
        item_size: int = 0

        if size_str.isdigit():
            try:
                item_size = int(size_str)
            except ValueError:
                # Log this unexpected case, but maybe default to None or 0
                print(
                    f"Warning: Could not convert size '{size_str}' to int for item '{name_str}'"
                )
                item_size = 0
        # Directory size is 0
        elif size_str == "-":
            item_size = 0
        else:
            # Unexpected value...
            print(f"Warning: Unexpected size format '{size_str}' for item '{name_str}'")
            item_size = 0

        items.append(
            MegaItem(
                name=name_str.strip(),
                size=item_size,
                mtime=mtime_str,
                ftype=item_type,
            )
        )
    return items


###############################################################################
async def mega_du(
    dir: str = "/", recurse: bool = True, units: F_SizeUnit = F_SizeUnit.MB
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

    cmd: list[str] = ["cd"]
    cmd.append(target_path)
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error changing directories to '{target_path}': {error_msg}")
        return


###############################################################################
async def mega_cd_ls(
    target_path: str | None = "/", ls_flags: list[str] | None = None
) -> MegaItems:
    """
    Change directories and ls.
    """
    if target_path:
        print(f"cdls to {target_path}")
    else:
        print("cdls to root")
        target_path = "/"

    await mega_cd(target_path)
    items = await mega_ls(target_path, ls_flags)

    return items


###############################################################################
async def mega_cp(file_path: str, target_path: str):
    """
    Copy file from 'file_path' to 'target_path'
    """
    print(f"Copying file {file_path} to {target_path}")

    cmd = ["cp", file_path, target_path]
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error copying file '{file_path} to '{target_path}': {error_msg}")
        return

    print(f"Successfully copied '{file_path}' to '{target_path}'")


###############################################################################
async def mega_mv(file_path: str, target_path: str):
    """
    Move a file (or rename it).
    """

    print(f"Moving file {file_path} to {target_path}")

    cmd = ["mv", file_path, target_path]
    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error moving file '{file_path} to '{target_path}': {error_msg}")
        return

    print(f"Successfully moved '{file_path}' to '{target_path}'")


###############################################################################
async def mega_rm(file: str, flags: list[str] | None):
    """
    Remove a file.
    """

    print(f"Removing file {file} with flags: {flags} ")

    cmd = ["rm", file]

    if flags:
        cmd.extend(flags)

    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error removing file '{file}' with flags '{flags}': {error_msg}")
        return

    print(f"Successfully removed '{file}' with flags '{flags}'")


###############################################################################
async def mega_put(
    local_path: str | list[str],
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
        return

    # Base of the command
    cmd = ["put"]

    # Optional arguments
    if queue:
        cmd.append("-q")

    if create_remote_dir:
        cmd.append("-c")

    # Add path to upload
    if type(local_path) is list[str]:
        cmd.extend(local_path)
    else:
        cmd.append(str(local_path))

    # Remote destination
    cmd.append(target_path)

    response = await run_megacmd(cmd)

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
        return

    # Optional args
    if queue:
        cmd.append("-q")

    if is_dir and merge:
        cmd.append("-m")

    # Append remote path
    cmd.append(remote_path)

    # TODO Check that the path is writable and has the correct permissions
    if not target_path:
        # Get the users home dir
        target_path = os.path.expanduser("~")

    cmd.append(target_path)

    response = await run_megacmd(cmd)

    if response.return_code != 0 or response.stderr:
        error_msg = response.stderr if response.stderr else response.stdout
        print(f"Error downloading in '{target_path}': {error_msg}")
        return
