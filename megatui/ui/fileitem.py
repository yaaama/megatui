# FileItem
#

from typing import override

from mega.megacmd import MegaItem
from rich.text import Text
from textual.widgets import Static
from textual.app import ComposeResult


class FileItem(Static):
    # MegaItem
    mega_item: MegaItem

    NAME_WIDTH: int = 30
    MTIME_WIDTH: int = 18
    SIZE_WIDTH: int = 10

    DEFAULT_CSS = """
    FileItem {
        width: 100%;
        height: 1;
    }

    .fileitem--icon {
        /* color: cyan; */
    }
    .fileitem--name {
        /* color: white; */
    }
    .fileitem--time {
    }
    .fileitem--size {
    }

    /* Styles for the FileItem widget itself based on its class */
    FileItem.--directory {
        /* color: blue; */
    }
    FileItem.--file {
        /* color: white; */
    }

    /* Standard hover/highlight */
    FileItem:hover {
    }

    """

    def __init__(
        self,
        item: MegaItem,
    ) -> None:
        """
        Initialise the FileItem.

        Args:
            item (MegaItem): The file/directory data object.
            name (str | None): Optional name for querying.
            id (str | None): Optional CSS ID.
            disabled (bool): Whether the widget is disabled.
        """

        super().__init__()
        # Store the MegaItem item
        self.mega_item = item
        self.add_class(
            f"--{self.mega_item.ftype.name.lower()}"
        )  # Adds '--directory' or '--file'

        # Name
        self._fname_str: Text = Text(
            self.mega_item.name, overflow="ellipsis", no_wrap=True, end=""
        )
        self._fname_str.align(align="left", width=self.NAME_WIDTH)

        # Modification time
        self._mtime_str = f"{self.mega_item.mtime:<{self.MTIME_WIDTH}}"

        # Icon & size of file
        # Size field empty if directory
        if self.mega_item.is_file():
            self._icon_str: str = "📄"
            fsize_float, fsize_unit_enum = self.mega_item.get_size()
            fsize_base = f"{fsize_float:.2f} {fsize_unit_enum.get_unit_str()}"
        else:
            self._icon_str: str = "📁"
            fsize_base = ""

        self._fsize_str = f"{fsize_base:<{self.MTIME_WIDTH}}"

    @override
    def render(self) -> Text:

        line: Text = Text.assemble(
            (f"{self._icon_str} "),
            (self._fname_str),
            ("  ", ""),
            (f"{self._mtime_str}"),
            ("  ", ""),
            (f"{self._fsize_str}"),
        )
        return line

# END
