# FileItem
#

from typing import override

from mega.megacmd import MegaItem
from rich.text import Text
from textual.widgets import Static


class FileItem(Static):
    mega_item: MegaItem

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
        name: str | None = None,
        id: str | None = None,
        disabled: bool = False,
    ) -> None:
        """
        Initialise the FileItem.

        Args:
            item (MegaItem): The file/directory data object.
            name (str | None): Optional name for querying.
            id (str | None): Optional CSS ID.
            disabled (bool): Whether the widget is disabled.
        """

        super().__init__(name=name, id=id, disabled=disabled)
        # Store the MegaItem item
        self.mega_item = item
        self.add_class(
            f"--{self.mega_item.ftype.name.lower()}"
        )  # Adds '--directory' or '--file'

    @override
    def render(self) -> Text:
        """Return a Rich Text object representing the file item."""
        # --- Get Data ---
        icon = "📁" if self.mega_item.is_dir() else "📄"
        fname_str : Text = Text(self.mega_item.name)
        fname_str.truncate(30, overflow="ellipsis")
        fname_str.align("left", 30)
        fmtime_str = self.mega_item.mtime

        if self.mega_item.is_file() == True:
            fsize_float, fsize_unit_enum = self.mega_item.get_size()
            # Right-align size within a fixed width (e.g., 10 characters)
            fsize_str = f"{fsize_float:.1f} {fsize_unit_enum.get_unit_str()}".rjust(10)
        else:
            fsize_str = " " * 10  # Pad directory size column

        text = Text.assemble(
            (f"{icon} ", "default"),
            (fname_str),
            (" ", ""),
            (f" {fmtime_str:^18}"),
            (" ", ""),
            (f" {fsize_str}"),
        )

        text.truncate(self.size.width, overflow="ellipsis")
        text.pad_right(
            self.size.width - text.cell_len
        )  # Pad to fill width for background highlighting

        return text

    # END
