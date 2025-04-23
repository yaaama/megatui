# UI Components Related to Files
#
#
from rich.segment import Segment
from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import var
from textual.visual import VisualType
from textual.strip import Strip
from typing import Literal, override
import textual.types
from textual.widgets import Label, ListItem, ListView, Placeholder, Static
from textual.message import Message
from typing import Any  # Import Any for **kwargs type hint

import megatui.mega.megacmd as m


class FileItem(Static):

    DEFAULT_CSS: Literal[
        """
    FileItem {
        padding: 0 1;
        height: 1;
        /* Define styles for different parts later */
        /* &.file { color: blue; } */
        /* &.directory { color: green; } */
        /* &.size { color: grey; } */
        /* &.time { color: yellow; } */
    }

    /* Add style for hover maybe? */
    /* FileItem:hover {
         background: $accent;
         color: $text;
    */
    """
    ]

    def __init__(
        self,
        item: m.MegaItem,
        name: str | None = None,
        id: str | None = None,
        disabled: bool = False,
    ) -> None:
        """
        Initialise the FileItem.

        Args:
            item (m.MegaItem): The file/directory data object.
            name (str | None): Optional name for querying.
            id (str | None): Optional CSS ID.
            disabled (bool): Whether the widget is disabled.
        """

        super().__init__(name=name, id=id, disabled=disabled)

        # Store the MegaItem data associated with this widget
        self.item: m.MegaItem = item

    @override
    def render(self) -> Text:
        """Render the file item using Rich Text."""

        # --- Get Data ---
        fsize_float, fsize_unit_enum = self.item.get_size()
        fsize_str = f"{fsize_float:.1f} {fsize_unit_enum.get_unit_str()}"  # Format size like "12.3 KB"
        ftype_str = self.item.ftype_str()  # "f" or "d"
        fname_str = self.item.name
        fmtime_str = self.item.mtime  # Assuming this is already a string

        # --- Choose Icon/Style based on type ---
        # Similar to 'ls' or file managers, use icons or distinct colors
        if self.item.is_file():
            icon = "📄"  # You can use nerd fonts for better icons if installed
            ftype_style = "italic blue"  # Rich style string
        elif self.item.is_dir():
            icon = "📁"
            ftype_style = "bold green"
        else:
            icon = "❓"
            ftype_style = "dim"

        # --- Construct Rich Text ---
        # Text.assemble allows combining styled parts easily.
        # It's efficient for creating styled text lines.
        # (icon, ftype_style) - Apply style to the icon
        # f" {fname_str}" - Add filename with a space (default style)
        # (" " * (40 - len(fname_str))), # Basic padding (adjust width 40 as needed)
        # (f" {fmtime_str}", "yellow"), # Add time, styled yellow
        # (f" {fsize_str.rjust(10)}", "dim") # Add size, right-aligned in 10 chars, dim style

        # Alternative using Text.append for clarity:
        text = Text()
        # Use f-string formatting for basic column alignment (adjust widths as needed)
        # {icon:<2} - Icon, left align, width 2
        # {fname_str:<40.40} - Filename, left align, width 40, max 40 chars shown
        # {fmtime_str:<16} - Mod time, left align, width 16
        # {fsize_str:>10} - Size, right align, width 10
        formatted_line = f"{icon:<2}{fname_str:<40.40} {fmtime_str:<16} {fsize_str:>10}"
        text.append(formatted_line)

        # Apply styles to parts if needed (though CSS is often preferred)
        # Example: Re-applying styles if not using CSS classes via span_styles
        # text.stylize(ftype_style, 0, 1) # Style the icon part

        # Tell Textual this text might contain styles defined in CSS
        # This is needed if we want to use the CSS classes like .filename, .filesize
        # Note: Applying CSS classes to *parts* of text within a single Static widget
        # using this method is complex. It's often easier to use Rich markup styles
        # like "bold green" directly, or use multiple Label widgets horizontally.
        # For simplicity let's stick to Rich styles within render().
        # If we want CSS-based sub-styling, we'd need a different approach (e.g. multiple widgets).

        # Let's refine to use the Rich styles defined earlier:
        text = Text.assemble(
            (icon, ftype_style),  # Icon with style based on type
            f" {fname_str}",  # Filename (default style)
            (f" {fmtime_str}", "yellow"),  # Modification Time
            (f" {fsize_str.rjust(10)}", "dim"),  # Size, right-aligned, dimmed
            # Add padding if needed to fill width, but usually let container handle width
        )
        text.truncate(
            self.size.width, overflow="ellipsis"
        )  # Truncate if too long for widget width
        text.plain = text.plain.ljust(
            self.size.width
        )  # Pad with spaces to prevent background issues on hover

        return text


    def on_mount(self) -> None:
        pass

    def on_select(self) -> None:
        """Handle FileItem selection."""
        pass


class FileList(ListView):
    """A ListView widget to display multiple FileItems."""

    def __init__(
        self,
        *args: ListItem,
        **kwargs,
    ) -> None:
        """
        Initialise the FileList.

        Args:
            *args: Positional arguments passed to the parent ListView/Widget.
                   Typically represents child widgets, though less common for ListView init.
            **kwargs: Keyword arguments (e.g., 'id', 'classes') passed to the parent.
        """
        super().__init__(*args, **kwargs)
        # Set the border title for the ListView
        self.border_title: str = "Files"

    def update_list(self, items: list[m.MegaItem]) -> None:
        """Clear and repopulate the list with new items."""
        # Store the current highlighted index if needed, or reset focus
        # current_highlight = self.index
        self.clear()  # Remove existing ListItem widgets
        for item_data in items:
            # Create the custom widget for the file data
            file_item_widget = FileItem(item_data)
            # Wrap the custom widget in a standard ListItem
            list_item_container = ListItem(file_item_widget)
            # Add the ListItem to the ListView
            self.append(list_item_container)
            # Could restore highlighting here if needed
