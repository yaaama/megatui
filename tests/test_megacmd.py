# If input_file_0.py is in the same directory or your PYTHONPATH is set up:
from datetime import datetime

from megatui.mega import data, megacmd
from megatui.mega.data import (
    MegaFileSize,
    MegaFileTypes,
    MegaNode,
    MegaPath,
    MegaSizeUnits,
)


def str_dtfmt(iso_fmt: str) -> datetime:
    """Return iso formatted string as datetime object."""
    return datetime.fromisoformat(iso_fmt)


# --- Tests for MegaItem ---
def test_meganode_human_size_calculation():
    """Test for human readable size calculations."""
    item = MegaNode(
        name="test.txt",
        path=MegaPath("/remote/test.txt"),
        bytes=2048,
        mtime=str_dtfmt("2025-01-22T14:08:10"),
        ftype=MegaFileTypes.FILE,
        version=1,
        handle="handle",
    )
    assert item.bytes == 2048
    assert item.size == (2.0, MegaSizeUnits.KB)

    assert item.is_file
    assert not item.is_dir
    assert str(item.path) == "/remote/test.txt"
    assert item.handle == "handle123"
    assert item.version == 1


def test_meganode_node_creation_directory():
    item = data.MegaNode(
        name="folder",
        path=MegaPath("/folder"),
        bytes=0,
        mtime=str_dtfmt("2025-03-04T10:02:02"),
        ftype=MegaFileTypes.DIRECTORY,
        version=0,
        handle="handle",
    )
    assert item.size == (0.0, MegaSizeUnits.B)
    assert item.is_dir
    assert not item.is_file


def test_meganode_node_creation_file():
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
