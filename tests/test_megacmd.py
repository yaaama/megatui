import logging
from datetime import datetime

from megatui.mega import data
from megatui.mega.data import (
    MegaFileTypes,
    MegaNode,
    MegaPath,
    MegaSizeUnits,
)

# Create a logger for this specific file
logger = logging.getLogger(__name__)


def str_dtfmt(iso_fmt: str) -> datetime:
    """Return iso formatted string as datetime object."""
    return datetime.fromisoformat(iso_fmt)


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
