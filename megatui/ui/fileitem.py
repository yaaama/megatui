# FileItem
#

from typing import override

from rich.console import Console
from rich.text import Text
from textual.widgets import ListItem, ListView, Static, Label
from textual.app import RenderResult, ComposeResult
from textual.message import Message
from textual import work # Import work decorator
from textual.worker import Worker, WorkerState # Import worker types
from typing import Literal


from megatui.mega.megacmd import MegaItem
class FileItem(Static):
    item: MegaItem
    DEFAULT_CSS = """

    FileItem {
        width: 100%;
        height: 1;
    }

    .fileitem--icon {

        /* e.g., color: cyan; */
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
        self.item = item
        self.add_class(f"--{self.item.ftype.name.lower()}") # Adds '--directory' or '--file'

    # @override
    # def compose(self) -> ComposeResult:
    #     """Return a Rich Text object."""
    #     # --- Get Data ---
    #     if (self.item.is_file == True):
    #         fsize_float, fsize_unit_enum = self.item.get_size()
    #         fsize_str = f"{fsize_float:.1f} {fsize_unit_enum.get_unit_str()}"  # Format size like "12.3 KB"
    #     else:
    #         fsize_str = " "
    #
    #     ftype_str = self.item.ftype_str()  # "f" or "d"
    #     fname_str = self.item.name
    #     fmtime_str = self.item.mtime  # Assuming this is already a string
    #
    #     # --- Choose Icon/Style based on type ---
    #     # --- Choose Icon ---
    #     icon = "📁" if self.item.is_dir() else "📄"
    #
    #     # --- Construct Rich Text ---
    #     # Text.assemble allows combining styled parts easily.
    #     # It's efficient for creating styled text lines.
    #     # (icon, ftype_style) - Apply style to the icon
    #     # f" {fname_str}" - Add filename with a space (default style)
    #     # (" " * (40 - len(fname_str))), # Basic padding (adjust width 40 as needed)
    #     # (f" {fmtime_str}", "yellow"), # Add time, styled yellow
    #     # (f" {fsize_str.rjust(10)}", "dim") # Add size, right-aligned in 10 chars, dim style
    #
    #     # Alternative using Text.append for clarity:
    #     text : Text = Text()
    #     text.assemble(
    #         (f"{icon}", "fileitem--icon"),
    #         (" ", ""), # Spacer
    #         (f"{fname_str}", "fileitem--name"),
    #         (" " * (self.size.width - len(icon) - 1 - len(fname_str) - 18 - 10 - 2)), # Dynamic padding (adjust if needed)
    #         (f" {fmtime_str}", "fileitem--time"),
    #         (f" {fsize_str}", "fileitem--size"),
    #     )
    #
    #
    #     # Truncate the entire line if it's too long (should ideally not happen with fixed widths)
    #     # Textual handles overflow at the Static widget level if width is constrained.
    #     # We still truncate the name part if it's excessively long.
    #     # max_name_width = max(10, self.size.width - 2 - 18 - 10 - 4) # Estimate max name width
    #     text.truncate(self.size.width, overflow="ellipsis", pad=True)
    #
    #     # Pad ensures background covers the full width on highlight/hover
    #     # text.pad_right(self.size.width - text.cell_len) # Alternative padding
    #     text.plain = text.plain.ljust(self.size.width) # Ensure padding
#
    #     yield Label(text)


    @override
    def render(self) -> Text:
        """Return a Rich Text object representing the file item."""
        # --- Get Data ---
        icon = "📁" if self.item.is_dir() else "📄"
        fname_str = self.item.name
        fmtime_str = self.item.mtime

        if self.item.is_file() == True:
            fsize_float, fsize_unit_enum = self.item.get_size()
            # Right-align size within a fixed width (e.g., 10 characters)
            fsize_str = f"{fsize_float:.1f} {fsize_unit_enum.get_unit_str()}".rjust(10)
        else:
            fsize_str = " " * 10 # Pad directory size column

        # --- Construct Rich Text ---
        # Use Text.assemble for combining styled parts.
        # Let Textual handle the overall width and truncation.
        # Use spaces for separation; layout can be refined with CSS grid/flex later if needed.
        text = Text.assemble(
            (f"{icon} ", "default"), # Or some other basic style like "bold"
            (f"{fname_str:<40}", "default"),
            (" ", ""),
            # Use theme variables directly if defined in your app's theme CSS
            (f" {fmtime_str:^18}"),
            (" ", ""),
            (f" {fsize_str}"),
        )

        # Let the Static widget handle truncation based on its available width
        text.truncate(self.size.width, overflow="ellipsis")
        text.pad_right(self.size.width - text.cell_len) # Pad to fill width for background highlighting

        return text






    # END
