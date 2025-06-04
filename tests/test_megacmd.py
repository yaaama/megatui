# If input_file_0.py is in the same directory or your PYTHONPATH is set up:
import megatui.mega.megacmd as megacmd


# --- Tests for MegaItem ---
def test_megaitem_file_creation_size_calculation():
    item = megacmd.MegaItem(
        name="test.txt",
        parent_path="/remote",
        size=2048,
        mtime="01Jan2023 10:00:00",
        ftype=megacmd.MegaFileTypes.FILE,
        version=1,
        handle="handle123",
    )
    assert item.name == "test.txt"
    assert item.bytes == 2048
    assert item.size == 2.0
    assert item.size_unit == megacmd.MegaSizeUnits.KB
    assert item.is_file()
    assert not item.is_dir()
    assert str(item.full_path) == "/remote/test.txt"  # Or PurePath("/remote/test.txt")


def test_megaitem_directory_creation():
    item = megacmd.MegaItem(
        name="folder",
        parent_path="/",
        size=0,
        mtime="02Feb2023 11:00:00",
        ftype=megacmd.MegaFileTypes.DIRECTORY,
        version=0,
        handle="handle456",
    )
    assert item.size == 0.0
    assert item.size_unit == megacmd.MegaSizeUnits.B
    assert item.is_dir()
    assert not item.is_file()
