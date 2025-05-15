# FileItem
#

from typing import override

from megatui.mega.megacmd import MegaItem
from rich.text import Text
from textual.widgets import Static, ListItem


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
        """

        # Store the MegaItem item
        self.mega_item = item

        # Name
        self._fname_str: Text = Text(
            self.mega_item.name, overflow="ellipsis", no_wrap=True, end=""
        )
        self._fname_str.align(align="left", width=self.NAME_WIDTH)

        # Modification time
        self._mtime_str = f"{self.mega_item.mtime:<{self.MTIME_WIDTH}}"

        # Icon & size of file
        self._icon_str: str = "📄"
        # Size field empty if directory
        if self.mega_item.is_file():
            fsize_float, fsize_unit_enum = self.mega_item.get_size()
            fsize_base = f"{fsize_float:.2f} {fsize_unit_enum.get_unit_str()}"
        else:
            self._icon_str = "📁"
            fsize_base = ""

        self._fsize_str = f"{fsize_base:<{self.SIZE_WIDTH}}"

        super().__init__(markup=False)

        self.add_class(
            f"--{self.mega_item.ftype.name.lower()}"
        )  # Adds '--directory' or '--file'

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
