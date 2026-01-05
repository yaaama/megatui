import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from megatui.mega import data, megacmd
from megatui.mega.data import (
    MegaCmdResponse,
    MegaFileTypes,
    MegaNode,
    MegaPath,
    MegaSizeUnits,
)

# Create a logger for this specific file
logger = logging.getLogger(__name__)
# pyright: reportPrivateUsage=false, reportOptionalMemberAccess=false


@pytest.fixture
def mock_exec():
    """
    Fixture that mocks _exec_megacmd.
    It yields the mock object so we can configure its return value in tests.
    """
    with patch("megatui.mega.megacmd._exec_megacmd") as mock:
        yield mock


def str_dtfmt(iso_fmt: str) -> datetime:
    """Return iso formatted string as datetime object."""
    return datetime.fromisoformat(iso_fmt)


class TestLogInStatus:
    async def test_logged_in_success(self, mock_exec):
        """Test 'check_mega_login' function."""
        mock_exec.return_value = MegaCmdResponse(
            stdout="Account e-mail: user@example.com", stderr=None, return_code=0
        )

        result = await megacmd.check_mega_login()

        assert result is True
        # Verify it called 'whoami'
        mock_exec.assert_called_with(command=("whoami",))

    async def test_not_logged_in(self, mock_exec):
        """Test login check returns False on error or empty output."""
        # Simulator a "Not logged in" state (usually non-zero exit or empty stdout)
        mock_exec.return_value = MegaCmdResponse(
            stdout="",
            stderr="[2024-03-01_21-24-25.135158 cmd ERR  Not logged in.]",
            return_code=57,
        )

        result = await megacmd.check_mega_login()
        assert result is False


class TestLS:
    LS_DIR_TO_OUTPUT = {
        "/books": """FLAGS VERS      SIZE             DATE          HANDLE NAME
d---    -            - 2025-03-14T09:51:33 H:8lx13R4Q C
d---    -            - 2025-03-14T09:51:33 H:33x33aaa subdir2
----    1      3866012 2023-08-07T17:53:35 H:Z84xkZbI linux-programming.pdf
----    3      0 2023-08-07T17:53:35 H:Z84xkxxx 0sizefile.pdf
 ----    1      1 2023-08-07T17:53:35 H:Z84xkyyy 1sizefile.pdf""",
        "/emptyDir": """/emptyDir:
FLAGS VERS      SIZE             DATE          HANDLE NAME""",
        "invalidDir": """[2026-01-05_22-16-16.956535 cmd ERR  Couldn't find invalidDir]""",
    }

    async def test_parsing(self, mock_exec):
        """Test that mega_ls correctly parses raw output into MegaNode objects."""
        mock_exec.return_value = MegaCmdResponse(
            stdout=self.LS_DIR_TO_OUTPUT["/books"], stderr=None, return_code=0
        )

        path = MegaPath("/books")
        nodes = await megacmd.mega_ls(path=path)

        # We expect 2 items based on LS_OUTPUT_SAMPLE
        assert len(nodes) == 5

        # Check Directory Parsing
        # Directory 1
        folder = nodes[0]
        assert folder.name == "C"
        assert folder.ftype == MegaFileTypes.DIRECTORY
        assert folder.is_dir
        assert folder.handle == "H:8lx13R4Q"

        # Directory 2
        folder2 = nodes[1]
        assert folder2.name == "subdir2"
        assert folder2.handle == "H:33x33aaa"
        assert folder2.ftype == MegaFileTypes.DIRECTORY
        assert folder2.is_dir

        # File
        file = nodes[2]
        assert file.name == "linux-programming.pdf"
        assert file.ftype == MegaFileTypes.FILE
        assert file.handle == "H:Z84xkZbI"
        assert file.is_file
        assert file.bytes == 3866012
        # Check formatted size object
        assert file.size.unit == MegaSizeUnits.MB
        assert file.size.size == pytest.approx(
            3.69, abs=0.01
        )  # 3.69 MiB with tolerance of 0.01
        assert file.version == 1

        # File 2 : 0 Size Filed
        file2 = nodes[3]
        assert file2.name == "0sizefile.pdf"
        assert file2.ftype == MegaFileTypes.FILE
        assert file2.handle == "H:Z84xkxxx"
        assert file2.is_file
        assert file2.bytes == 0
        assert file2.size.unit == MegaSizeUnits.B
        assert file2.size.size == 0
        assert file2.version == 3

        # File 3 : 1 sized file
        file3 = nodes[4]
        assert file3.name == "1sizefile.pdf"
        assert file3.ftype == MegaFileTypes.FILE
        assert file3.handle == "H:Z84xkyyy"
        assert file3.is_file
        assert file3.bytes == 1
        # Check formatted size object
        assert file3.size.unit == MegaSizeUnits.B
        assert file3.size.size == 1
        assert file3.version == 1

    async def test_empty_dir(self, mock_exec):
        mock_exec.return_value = MegaCmdResponse(
            stdout=self.LS_DIR_TO_OUTPUT["/emptyDir"], stderr=None, return_code=0
        )

        path = MegaPath("/emptyDir")
        nodes = await megacmd.mega_ls(path=path)

        assert len(nodes) == 0

    async def test_invalid_directory(self, mock_exec):
        mock_exec.return_value = MegaCmdResponse(
            stdout=self.LS_DIR_TO_OUTPUT["invalidDir"],
            stderr="[2026-01-05_22-16-16.956535 cmd ERR  Couldn't find invalidDir]",
            return_code=53,
        )

        path = MegaPath("invalidDir")

        nodes = await megacmd.mega_ls(path=path)

        assert len(nodes) == 0


class TestCommandCreation:
    """Test suite for command creation."""


class TestMegaNode:
    """Test suite for nodes."""

    def test_human_size_calc(self):
        """Test for human readable size calculations."""
        bytes = 51200
        item = MegaNode(
            name="test.txt",
            path=MegaPath("/remote/test.txt"),
            bytes=bytes,
            mtime=str_dtfmt("2025-01-22T14:08:10"),
            ftype=MegaFileTypes.FILE,
            version=1,
            handle="handle",
        )
        assert item.bytes == bytes
        assert item.size
        assert item.size.size == 50.0
        assert item.size.unit == MegaSizeUnits.KB

        assert item.is_file
        assert not item.is_dir
        assert str(item.path) == "/remote/test.txt"

    def test_directory_creation(self):
        """Test for successful DIRECTORY node creation."""
        item = data.MegaNode(
            name="folder",
            path=MegaPath("/folder"),
            bytes=0,
            mtime=str_dtfmt("2025-03-04T10:02:02"),
            ftype=MegaFileTypes.DIRECTORY,
            version=0,
            handle="handle",
        )
        assert item.size is None
        assert item.is_dir
        assert not item.is_file

    def test_file_creation(self):
        """Test for successful FILE node creation."""
        item = data.MegaNode(
            name="filex.txt",
            path=MegaPath("/folder/filex.txt"),
            bytes=10293,
            mtime=str_dtfmt("2025-03-04T10:02:02"),
            ftype=MegaFileTypes.FILE,
            version=0,
            handle="handle",
        )
        assert not item.is_dir
        assert item.is_file

        assert str(item.path) == "/folder/filex.txt"
