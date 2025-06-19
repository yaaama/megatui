# UI Components Related to Files
from pathlib import PurePath
from typing import Any, ClassVar, LiteralString, override

from rich.text import Text
from textual import work
from textual.binding import Binding, BindingType
from textual.color import Color
from textual.content import Content
from textual.message import Message
from textual.style import Style
from textual.widgets import DataTable
from textual.widgets._data_table import RowDoesNotExist, RowKey
from textual.worker import Worker  # Import worker types

import megatui.mega.megacmd as m
from megatui.mega.megacmd import MegaCmdError, MegaItem, MegaItems
from megatui.messages import StatusUpdate
from megatui.ui.screens.rename import NodeInfoDict, RenameDialog


###########################################################################
# FileList
###########################################################################
class FileList(DataTable[Any], inherit_bindings=False):
    """
    A DataTable widget to display multiple FileItems
    """

    """
    All MegaItems in the current directory.
    TODO: Make this into a map of directories to items => dict[Dir, items[MegaItems]]
    This can be used to cache directories.
    """

    DEFAULT_CSS = """ """

    border_subtitle: str
    """ Border subtitle. """

    curr_path: str
    """ Current path we are in. """

    _loading_path: str
    """ Path we are currently loading. """

    # TODO We will map items by their 'Handle'
    _row_data_map: dict[str, MegaItem]
    _selected_items: set[str]

    FILE_ICON_MARKUP: ClassVar[LiteralString] = ":page_facing_up:"
    """ Markup used for file icon. """
    DIR_ICON_MARKUP: ClassVar[LiteralString] = ":file_folder:"
    """ Markup used for directory icon. """
    SELECTION_INDICATOR: ClassVar[LiteralString] = "*"
    """ Character to indicate a file has been selected. """

    ## Bindings
    _FILE_ACTION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="r", action="refresh", description="Refresh", show=True),
        Binding(key="R", action="rename_file", description="Rename a file", show=True),
        Binding(
            key="space", action="select_item", description="Select file", show=True
        ),
    ]
    """ Binds that deal with files. """

    _NAVIGATION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l"),
        Binding("h,backspace", "navigate_out", "Parent Dir", key_display="h"),
    ]
    """ Binds related to navigation. """

    # Assign our binds
    BINDINGS: ClassVar[list[BindingType]] = _NAVIGATION_BINDINGS + _FILE_ACTION_BINDINGS

    COLUMNS: ClassVar[list[LiteralString]] = ["icon", "name", "modified", "size"]
    DEFAULT_COLUMN_WIDTHS = (2, 50, 12, 8)
    COMPONENT_CLASSES = {
        "filelist--cursor",
        "filelist--hover",
        "filelist--fixed",
        "filelist--fixed-cursor",
        "filelist--header",
        "filelist--header-cursor",
        "filelist--header-hover",
        "filelist--odd-row",
        "filelist--even-row",
        "filelist--icon",
    }

    def __init__(self):
        # Initialise the DataTable widget
        super().__init__()
        self.id = "file_list"
        self.cursor_type = "row"
        self.show_cursor = True
        self.show_header = True
        self.header_height = 1
        self.zebra_stripes = False
        # self.cursor_foreground_priority = ("renderable",)
        # self.cursor_background_priority = ("renderable",)
        self.show_row_labels = True

        # self.cell_padding = 0

        # Extra UI Elements

        # TODO: Think of something useful to add here
        # self.border_title = "MEGA"
        self.border_subtitle = "Initializing view..."
        self.curr_path = "/"
        self._loading_path = self.curr_path
        self._row_data_map = {}
        self._selected_items = set()
        self._selected_item_style: Style = Style(
            foreground=Color.parse("red"), bold=True, italic=True
        )

    @override
    def on_mount(self) -> None:
        # Initialise the columns displayed Column and their respective formatting
        column_formatting = {
            "icon": {"label": " ", "width": 4},
            "name": {"label": "Name", "width": 50},
            "modified": {
                "label": "Modified",
                "width": 20,
            },
            "size": {"label": "Size", "width": 8},
        }

        self.log.info("Adding columns to FileList")

        # Add columns during initialisation with specified widths
        for column_name in self.COLUMNS:
            fmt = column_formatting.get(column_name)

            # If there is a configuration for our column name
            if fmt:
                self.add_column(
                    # column header label
                    label=str(fmt["label"]),
                    # Width of column header
                    width=(int(fmt["width"]) if fmt["width"] else None),
                    key=column_name,
                )

                self.log.debug(f"Column: '{column_name}', fmt: '{fmt}'")
            else:
                self.add_column(label=column_name, key=column_name, width=None)

    """
    # Messages ################################################################
    """

    class ToggledSelection(Message):
        """Message sent after item is selected by user."""

        def __init__(self, count: int) -> None:
            self.count: int = count
            super().__init__()

    class PathChanged(Message):
        """Message for when the path has changed.
        'PathChanged.path': The path changed into.
        """

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path: str = path

    class LoadSuccess(Message):
        """Message sent when items are loaded successfully.
        'LoadSuccess.path': Newly loaded path.
        """

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path: str = path

    class LoadError(Message):
        """Message sent when loading items fails.
        'LoadError.path': Path that failed to load.
        'LoadError.error': An error message.
        """

        def __init__(self, path: str, error: Exception) -> None:
            super().__init__()
            self.path: str = path
            self.error: Exception = error  # Include the error

    class EmptyDirectory(Message):
        """Message to signal the entered directory is empty."""

        def __init__(self) -> None:
            super().__init__()

    """
    # Actions #########################################################
    """

    async def action_navigate_in(self) -> None:
        """Navigate into a directory."""

        selected_item_data = self.get_highlighted_megaitem()
        # Fail: Selected item is None.
        if selected_item_data is None:
            self.log.debug("Cannot enter directory, selected item is 'None'.")
            return

        # Fail: Is a regular file
        if selected_item_data.is_file():  # Check if it's a directory
            self.log.debug("Cannot enter into a file.")
            return

        to_enter = selected_item_data.full_path
        path_str: str = str(to_enter)

        self.post_message(StatusUpdate(f"Loading '{to_enter}'...", timeout=2))
        await self.load_directory(path_str)

    async def action_navigate_out(self) -> None:
        """
        Navigate to parent directory.
        """
        self.log.info(f"Navigating out of directory {self.curr_path}")
        curr_path: str = self.curr_path

        # Avoid going above root "/"
        if curr_path == "/":
            self.post_message(
                StatusUpdate("Cannot navigate out any further, you're already at '/'")
            )
            return

        parent_path: PurePath = PurePath(curr_path).parent

        await self.load_directory(str(parent_path))

    async def action_refresh(self, quiet: bool = False) -> None:
        """
        Refreshes the current working directory.
        """
        if not quiet:
            self.post_message(
                StatusUpdate(f"Refreshing '{self.curr_path}'...", timeout=0)
            )

        await self.load_directory(self.curr_path)

    @work(
        exclusive=True,
        group="megacmd",
        name="file_rename",
        description="Renaming file.",
    )
    async def action_rename_file(self) -> None:
        """
        Rename a file.
        Popup will be shown to prompt the user for the new name.

        TODO: Make this actually rename the file.
        """
        self.log.info("Renaming file.")

        selected_item = self.get_highlighted_megaitem()

        if not selected_item:
            self.log.error("No highlighted file to rename.")
            return

        node_path: str = selected_item.path

        assert node_path != "/", "Cannot rename the root directory."

        # Build our dict of information about file being renamed
        node_info: NodeInfoDict = {
            "name": selected_item.name,
            "path": selected_item.path,
            "handle": selected_item.handle,
        }

        async def file_rename(result: tuple[str, NodeInfoDict] | None) -> None:
            """Nested function to serve as callback."""
            if not result:
                self.log.error("Invalid result!")
                return
            if not result[0] or not result[1]:
                self.log.error("Invalid result!")
                return

            new_name: str
            node: NodeInfoDict
            new_name, node = result
            assert (
                new_name and node
            ), f"Empty name: '{new_name}' or empty node: '{node}'."
            self.log.info(f"Renaming file `{node['name']}` to `{new_name}`")
            file_path: str = node["path"]
            await m.node_rename(file_path, new_name)
            await self.action_refresh()

        await self.app.push_screen(
            RenameDialog(
                popup_prompt=f"Rename {selected_item.name}",
                node_info=node_info,
                emoji_markup_prepended=(
                    ":page_facing_up:" if selected_item.is_file() else ":file_folder:"
                ),
                initial_input=selected_item.name,
            ),
            callback=file_rename,
        )

    def action_select_item(self) -> None:
        """
        Toggles the selection state of the currently hovered-over item (row).
        Selected rows are MEANT to be visually highlighted.
        """
        current_row_key: RowKey | None = self._get_curr_row_key()

        if not current_row_key:
            self.log.info("No current row key to select/deselect.")
            return

        curr_index = self.get_row_index(current_row_key)

        assert (
            current_row_key.value
        ), "Row key value SHOULD always exist when row key is not None."

        cursor_y = self.cursor_coordinate.row
        self.log.info(
            f"Selecting row. Rowkey: '{current_row_key.value}', Row Index: '{curr_index}'"
        )
        self.log.info(f"Cursor 'y' value: '{cursor_y}'")

        # Check if selected item has been selected already before
        # Get the MegaItem
        row_item: MegaItem = self._row_data_map[current_row_key.value]
        # Get handle
        item_handle = row_item.handle
        # Boolean expression to check if already selected
        already_selected: bool = item_handle in self._selected_items

        if not already_selected:
            self._selected_items.add(item_handle)
            select_txt = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
            self.rows[current_row_key].label = select_txt
            self.log.info(f"Selected row: {current_row_key.value}")
        else:
            self.rows[current_row_key].label = Text(" ")
            # Remove item from set of selected items
            self._selected_items.remove(item_handle)
            self.log.info(f"Deselected row: {current_row_key.value}")

        self.log.info("Updated row label")

        # self.refresh_row(curr_index)
        # self.refresh_line(self.cursor_coordinate.row)
        self.refresh()
        self._update_count += 1

        self.post_message(self.ToggledSelection(len(self._selected_items)))

    ###################################################################

    def _update_list_on_success(self, path: str, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.log.debug(f"Updating UI for path: {path}")
        self.curr_path = path

        self.clear(columns=False)
        self._row_data_map.clear()  # Clear our internal mapping

        height: int = 1
        fsize_str: str
        selection_label = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
        refresh: bool = False

        # Go through each item and create new row for them
        for node in fetched_items:
            # Prepare data for each cell in the row

            if node.is_dir():
                fsize_str = ""
                _icon = self.DIR_ICON_MARKUP
            else:
                fsize_str = f"{node.size:.1f} {node.size_unit.unit_str()}"
                _icon = self.FILE_ICON_MARKUP

            cell_icon = Content.from_rich_text(Text.from_markup(f"{_icon}"))
            cell_name = Content.from_rich_text(
                Text(text=f"{node.name}", overflow="ellipsis", no_wrap=True)
            )
            # Modification time
            cell_mtime = Content.from_rich_text(
                Text(text=f"{node.mtime}", style="italic")
            )
            # Size of node
            cell_size = Content(text=f"{fsize_str}")

            # Pass data as individual arguments for each column
            rowkey = self.add_row(
                # Icon
                cell_icon,
                # Content.from_rich_text(icon_content),
                # Name of node
                # Content(text=node.name),
                cell_name,
                # Modification time
                cell_mtime,
                # Size of node
                cell_size,
                # Unique key to reference the node
                key=node.handle,
                # Height of each row
                height=height,
                label=" ",
            )
            if node.handle in self._selected_items:
                self.rows[rowkey].label = selection_label
                refresh = True

            # Store the MegaItem
            self._row_data_map[node.handle] = node

        if refresh:
            self.refresh()
            self._update_count += 1
        self.border_subtitle = f"{len(fetched_items)} items"

    @work(
        exclusive=True,
        group="megacmd",
        name="fetch_files",
        description="mega-ls - Fetching dir listings",
    )
    async def fetch_files(self, path: str) -> MegaItems | None:
        """
        Asynchronously fetches items from MEGA for the given path.
        Returns the list of items on success, or None on failure.
        Errors are handled by posting LoadError message.
        """

        self.log.info(f"FileList: Worker starting fetch for path: {path}")
        try:
            # Fetch and sort items
            fetched_items: MegaItems = await m.mega_ls(path)
            # Return the result or empty list
            return fetched_items or []

        except MegaCmdError as e:
            self.log.error(f"FileList: MegaCmdError loading path '{path}': {e}")
            # Post error message from the worker (thread-safe)
            self.post_message(self.LoadError(path, e))
            return None  # Indicate failure by returning None
        except Exception as e:
            self.log.error(f"FileList: Unexpected error loading path '{path}': {e}")
            # Post error message from the worker (thread-safe)
            self.post_message(self.LoadError(path, e))
            return None  # Indicate failure

    async def load_directory(self, path: str) -> None:
        """Initiates asynchronous loading using the worker."""
        self.log.info(f"FileList.load_directory: Received request for path='{path}'")

        self.log.info(f"Requesting load for directory: {path}")
        self._loading_path = path  # Track the path we are loading

        # Start the worker. Results handled by on_worker_state_changed.
        worker_obj: Worker[MegaItems | None]
        worker_obj = self.fetch_files(path)

        await worker_obj.wait()

        fetched_items: MegaItems | None = worker_obj.result

        if worker_obj.is_cancelled:
            self.log.debug(
                f"Worker to fetch files for path '{self._loading_path}' was cancelled."
            )
            return

        # Failed
        if fetched_items is None:
            # Worker succeeded but returned None
            self.log.warning(
                f"Fetch worker for '{self._loading_path}' succeeded but returned 'None' result."
            )
            self.border_subtitle = "Load Error!"
            return

        # Success
        # Get number of files
        file_count: int = len(fetched_items)

        self.log.debug(
            f"Worker success for path '{self._loading_path}', items: {file_count}"
        )
        # Update FileList
        self._update_list_on_success(self._loading_path, fetched_items)

        # We have successfully loaded the path
        # self.post_message(self.LoadSuccess(path))
        # Path *successfully* changed
        self.post_message(self.PathChanged(path))

        # If the count is 0 send a status update
        if file_count == 0:
            self.post_message(self.EmptyDirectory())

    def _get_curr_row_key(self) -> RowKey | None:
        if self.cursor_row < 0 or not self.rows:  # No selection or empty table
            self.log.info("No highlighted item available to return.")
            return None
        try:
            # DataTable's coordinate system is (row, column)
            # self.cursor_coordinate.row gives the visual row index
            # We need the key of that row
            row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)

            return row_key if row_key else None

        except RowDoesNotExist:
            self.log.error("Could not return any row.")
            return None
        except Exception as e:
            # Catch potential errors if cursor is out of sync
            self.log.error(f"Error getting current row. {e}")
            return None

    def get_highlighted_megaitem(self) -> MegaItem | None:
        """
        Return the MegaItem corresponding to the currently highlighted row.
        """

        row_key = self._get_curr_row_key()

        assert row_key and row_key.value, "Invalid row key!"

        return self._row_data_map.get(row_key.value)

    def get_column_widths(self):
        """Get optimal widths for table columns.

        Returns a tuple of widths.
        """
        pass

    def selected_items(self) -> MegaItems:
        """Return items that have been SELECTED."""

        if len(self._selected_items) <= 0:
            self.log.debug("No items selected for us to return.")
            return []

        selected: list[MegaItem] = []
        for e in self._selected_items:
            item = self._row_data_map[e]
            selected.append(item)

        # self.log.info(f"Selected files: {rc.print(selected)}")
        return selected if len(selected) > 0 else []
