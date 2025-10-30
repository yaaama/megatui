"""FileList widget.
Contains actions and is the main way to interact with the application.
"""

# UI Components Related to Files
import asyncio
from collections import deque
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Final,
    LiteralString,
    assert_type,
    override,
)

from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets._data_table import RowDoesNotExist, RowKey
from textual.worker import Worker

from megatui.mega.data import MEGA_ROOT_PATH, MegaPath
from megatui.mega.megacmd import (
    MegaItems,
    MegaNode,
    MegaSizeUnits,
    mega_cd,
    mega_get,
    mega_ls,
    mega_mv,
    mega_rm,
)
from megatui.messages import RefreshRequest, StatusUpdate
from megatui.ui.file_tree import UploadFilesModal
from megatui.ui.screens.confirmation import ConfirmationScreen
from megatui.ui.screens.mkdir import MkdirDialog
from megatui.ui.screens.rename import RenameDialog

if TYPE_CHECKING:
    from megatui.app import MegaTUI


DL_PATH = Annotated[Path, "Default download path."]


class FileList(DataTable[Any], inherit_bindings=False):
    """A DataTable widget to display files and their information."""

    app: "MegaTUI"

    # * UI Elements ###########################################################
    FILELIST_ROW_HEIGHT: Final = 1
    """The height for rows in the table."""

    DEFAULT_CSS = """ """

    NODE_ICONS: ClassVar[dict[str, str]] = {"directory": "📁", "file": "📄"}
    """Icons for different kind of nodes."""

    _SELECTION_STR: ClassVar[LiteralString] = "*"
    """Character to indicate a file has been selected."""
    _SELECTION_STYLE = Style(color="red", bold=True, italic=True)
    """Style for the node selection indicator."""
    SELECTED_LABEL = Text(text=_SELECTION_STR, style=_SELECTION_STYLE)
    """Label for rows that have been selected."""
    NOT_SELECTED_LABEL = Text(text=" ")
    """Label for rows that are not selected (default)."""

    _BORDER_SUBTITLE_STYLES = {
        "empty": Style(color="red", bold=True),
        "normal": Style(color="white", reverse=True),
    }
    COLUMNS: ClassVar[list[str]] = ["icon", "name", "modified", "size"]

    DEFAULT_COLUMN_WIDTHS: tuple[int, ...] = (2, 50, 12, 8)

    # * State #################################################################

    _row_data_map: dict[
        str, MegaNode
    ]  # Row and associated MegaItem mapping for current directory.

    _selected_items: dict[
        str, MegaNode
    ]  # Dict to store selected MegaItem(s), indexed by their handles.

    _curr_path: MegaPath  # Current path we are in.

    _loading_path: MegaPath  # Path we are currently loading.

    _cursor_index_stack: deque[
        int
    ]  # Stores cursor index before navigating into a child folder.

    # * Bindings ###############################################################
    _FILE_ACTION_BINDINGS: ClassVar[list[BindingType]] = [
        # Select a file
        Binding(
            key="space",
            key_display="␠",
            action="toggle_file_selection",
            description="select a file",
            show=True,
        ),
        # Unselect all files
        Binding(
            key="u",
            key_display="u",
            action="unselect_all_files",
            description="unselect all",
            show=True,
        ),
        Binding(
            key="v",
            key_display="v",
            action="select_all_files",
            description="select all",
            show=True,
        ),
        # Refresh current directory
        Binding(
            key="r",
            key_display="r",
            action="refresh",
            description="refresh dir",
            show=True,
        ),
        # Rename a node/file
        Binding(
            key="R",
            key_display="R",
            action="rename_node",
            description="rename a node",
            show=True,
        ),
        # Make directory
        Binding(
            key="plus",
            key_display="+",
            action="mkdir",
            description="make new directory",
            show=True,
        ),
        # Open local filesystem
        Binding(key="o", key_display="o", action="upload_file", description="upload"),
        # Delete files
        Binding(key="D", key_display="D", action="delete_files", description="delete"),
        # Download files
        Binding(key="f3", key_display="f3", action="download", description="download"),
        # Move files
        Binding("M", key_display="M", action="move_files", description="move"),
    ]
    """ Binds that deal with files. """

    _NAVIGATION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Cursor Down", key_display="j", show=False),
        Binding("k", "cursor_up", "Cursor Up", key_display="k", show=False),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l", show=False),
        Binding(
            "h,backspace", "navigate_out", "Parent Dir", key_display="h", show=False
        ),
    ]
    """ Binds related to navigation. """

    BINDINGS: ClassVar[list[BindingType]] = _NAVIGATION_BINDINGS + _FILE_ACTION_BINDINGS

    # * Initialisation #########################################################

    def __init__(self):
        super().__init__(
            id="filelist",
            show_header=True,
            cursor_type="row",
            header_height=2,
            zebra_stripes=False,
            show_row_labels=True,
            cursor_foreground_priority="renderable",
        )

        # Extra UI Elements

        # TODO: Think of something useful to add here
        # self.border_title = "MEGA"
        self.border_subtitle = "Initializing view..."
        self._curr_path = MEGA_ROOT_PATH
        self._loading_path = self._curr_path
        self._row_data_map = {}
        self._selected_items = {}
        self._cursor_index_stack = deque()

    @override
    def on_mount(self) -> None:
        # Initialise the columns displayed Column and their respective formatting
        column_formatting = {
            "icon": {"label": " ", "width": 4},
            "name": {"label": "Name", "width": 50},
            "modified": {"label": "Modified", "width": 20},
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

    # * Actions #########################################################

    async def delete_files(self, files: MegaItems):
        self.log.info("Deleting files")

        tasks: list[asyncio.Task[None]] = []
        for item in files:
            if item.is_dir:
                tasks.append(
                    asyncio.create_task(mega_rm(fpath=item.path, flags=("-r", "-f")))
                )
            else:
                tasks.append(asyncio.create_task(mega_rm(fpath=item.path, flags=None)))

        await asyncio.gather(*tasks)

    @work(
        exclusive=True,
        description="Delete files. Displays a popup screen for confirmation.",
    )
    async def action_delete_files(self) -> None:
        self.log.info("Deleting files")
        # Selected files
        selected = self.selected_or_highlighted_items

        filenames = [str(item.path) for item in selected]
        filenames_str = ", ".join(filenames)

        deletion_conf_scr = ConfirmationScreen(
            title="Confirm Deletion",
            prompt=f"Delete {len(selected)} files?",
            extra_info=filenames_str,
        )

        conf_result = await self.app.push_screen(
            deletion_conf_scr, wait_for_dismiss=True
        )

        # If we get False
        if not conf_result:
            return

        await self.delete_files(selected)

        with self.app.batch_update():
            self.action_unselect_all_files()
            deleted_count = len(selected)
            cursor_index = self.cursor_row - deleted_count
            await self.action_refresh(quiet=True)
            self.move_cursor(row=cursor_index)

        self.app.notify(
            message=f"Deleted [bold][red]{len(filenames)}[/red][/bold] file(s).",
            title="Deletion",
        )

    async def action_upload_file(self) -> None:
        """Toggle upload file screen."""
        await self.app.push_screen(UploadFilesModal())

    # ** Navigation ############################################################

    async def action_navigate_in(self) -> None:
        """Navigate into directory under cursor."""
        selected_item_data = self.highlighted_item

        # Selected item is None.
        if not selected_item_data:
            self.log.debug("Nothing to navigate into...")
            return

        # Is a regular file
        if selected_item_data.is_file:  # Check if it's a directory
            self.log.debug("Cannot enter into a file.")
            return

        # Folder to enter
        to_enter = selected_item_data.path
        # Add cursor index to our cursor position stack
        self._cursor_index_stack.append(self.cursor_row)

        await self.load_directory(to_enter)
        await mega_cd(target_path=to_enter)

    async def action_navigate_out(self) -> None:
        """Navigate to parent directory."""
        self.log.debug(f"Navigating out of directory {self._curr_path}")
        curr_path: str = self._curr_path.str

        # Avoid going above root "/"
        if curr_path == "/":
            # self.post_message(
            #     StatusUpdate("Cannot navigate out any further, you're already at '/'")
            # )
            return

        parent_path: MegaPath = self._curr_path.parent
        curs_index = (
            self._cursor_index_stack.pop() if len(self._cursor_index_stack) > 0 else 0
        )

        # Useful to stop the flickering
        with self.app.batch_update():
            await self.load_directory(parent_path)
            await mega_cd(target_path=parent_path)
            self.move_cursor(row=curs_index)

    # ** File Actions ######################################################
    @on(RefreshRequest)
    async def on_refresh_request(self, event: RefreshRequest) -> None:
        """Handles refresh requests sent to FileList."""
        event.stop()
        await self.action_refresh(quiet=True)

    async def _refresh_curr_dir(self) -> None:
        """Refresh current directory view.
        Maintains the cursor point.
        """
        with self.app.batch_update():
            curs_index = self.cursor_row
            await self.load_directory(self._curr_path)
            curs_index = min(curs_index, self.row_count - 1)
            self.move_cursor(row=curs_index)

    async def action_refresh(self, quiet: bool = False) -> None:
        """Refreshes current working directory."""
        if not quiet:
            self.post_message(
                StatusUpdate(f"Refreshing '{self._curr_path}'...", timeout=2)
            )

        await self._refresh_curr_dir()

    # *** Selection #######################################################
    def _get_megaitem_at_row(self, rowkey: RowKey | str) -> MegaNode:
        """Return MegaItem for row index (rowkey).

        Args:
            rowkey: The rowkey (index) to return MegaItem for.

        Returns:
            MegaItem if item exists at RowKey, or None if none.
        """
        if not rowkey:
            raise ValueError("Passed in an empty rowkey!")

        key: str
        # If its a RowKey type, grab the value (str)
        if isinstance(rowkey, RowKey):
            if not rowkey.value:
                raise AttributeError("Value for RowKey not found!")

            key = rowkey.value
        else:
            key = rowkey

        try:
            # Get the MegaItem
            row_item: MegaNode = self._row_data_map[key]
            return row_item
        except KeyError as e:
            self.log.error(
                f"Could not find data for row key '{key}'. State is inconsistent."
            )
            raise e

    def _get_megaitem_at_cursor(self) -> MegaNode | None:
        """Returns MegaItem under the current cursor.

        Returns:
        MegaItem if there is one, else None.
        """
        row_key = self._get_curr_row_key()

        # Exit if there is a nonexistent rowkey or rowkey.value
        if not row_key or not row_key.value:
            return None

        return self._get_megaitem_at_row(row_key)

    def _toggle_selected_item_row_label(self, rowkey: str):
        """Toggle selection state of row in current directory, and update its label.

        Args:
        """
        if not rowkey:
            raise ValueError("Passed in empty rowkey.")

        item: MegaNode = self._row_data_map[rowkey]
        item_handle = item.handle

        # If item is already selected, deselect
        if item.handle in self._selected_items:
            self._selected_items[item_handle] = item
            self.rows[RowKey(item_handle)].label = self.SELECTED_LABEL
        # If item is not selected, select it
        else:
            del self._selected_items[item_handle]
            self.rows[RowKey(item_handle)].label = self.NOT_SELECTED_LABEL

    def action_select_all_files(self) -> None:
        """Toggle selection of all files in current directory.

        This works like a classic 'invert-all' action, where selected items are
        then deselected and non-selected files are then toggled.
        """
        if not self._row_data_map:
            # No files in current view
            return

        for key in self.rows:
            self._toggle_selected_item_row_label(key.value or "")
        self._update_count += 1
        self.refresh()
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    def action_toggle_file_selection(self) -> None:
        """Toggles selection state of row under cursor."""
        megaitem = self._get_megaitem_at_cursor()

        # Exit if there is no megaitem
        if not megaitem:
            self.log.info("No item to toggle selection.")
            return

        # There IS a row associated with a Megaitem
        item_handle = megaitem.handle

        # Debugging purposes
        row_key = self._get_curr_row_key()
        if not row_key:
            raise RuntimeError("Row key does not exist for this row!")

        # Unselect already selected items
        if item_handle in self._selected_items:
            del self._selected_items[item_handle]
            new_label = self.NOT_SELECTED_LABEL
            self.log.debug(f"Deselected row: {row_key.value}")

        else:
            # Action: SELECT
            self._selected_items[item_handle] = megaitem
            new_label = self.SELECTED_LABEL
            self.log.debug(f"Selected row: {row_key.value}")

        self.rows[row_key].label = new_label
        self.refresh_row(self.cursor_row)
        self._update_count += 1
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    def action_unselect_all_files(self) -> None:
        """Unselect all selected items (if there are any)."""
        if len(self._selected_items) == 0:
            self.log.debug("No items selected for us to unselect.")
            return

        for key in self._selected_items:
            # Check if selected item is within the curr list of rows
            if key in self.rows:
                # Remove selection labels from currently displayed row labels
                self.rows[RowKey(key)].label = self.NOT_SELECTED_LABEL

        self._selected_items.clear()

        self.refresh()
        self._update_count += 1

        self.app.post_message(self.ToggledSelection(0))

    def action_select_item(self) -> None:
        """Toggles the selection state of the currently hovered-over item (row).
        Selected rows are MEANT to be visually highlighted.
        """
        row_key = self._get_curr_row_key()

        if not row_key or not row_key.value:
            self.log.info("No current row key to select/deselect.")
            return

        # Get the MegaItem
        row_item: MegaNode = self._row_data_map[row_key.value]
        # Get handle
        item_handle = row_item.handle

        # Unselect already selected items
        if item_handle in self._selected_items:
            del self._selected_items[item_handle]
            new_label = self.NOT_SELECTED_LABEL
            log_message = f"Deselected row: {row_key.value}"

        else:
            # Action: SELECT
            self._selected_items[item_handle] = row_item
            new_label = self.SELECTED_LABEL
            log_message = f"Selected row: {row_key.value}"

        self.log.info(log_message)
        self.rows[row_key].label = new_label

        self.refresh()
        # Need this hack to refresh the UI
        self._update_count += 1
        self.app.post_message(self.ToggledSelection(len(self._selected_items)))

    # ** Rename node ######################################################

    @work
    async def action_rename_node(self) -> None:
        """Rename a file by showing a dialog to prompt for the new name.

        TODO: Make this open a file editor when multiple files are selected.
        """
        self.log.info("Renaming file.")

        selected_item = self.highlighted_item

        if not selected_item:
            self.log.error("No highlighted file to rename.")
            return

        node_path = str(selected_item.path)

        assert node_path != "/", "Cannot rename the root directory."

        await self.app.push_screen(
            RenameDialog(
                popup_prompt=f"Rename {selected_item.name}",
                node=selected_item,
                emoji_markup_prepended=(
                    ":page_facing_up:" if selected_item.is_file else ":file_folder:"
                ),
                initial_input=selected_item.name,
            ),
            wait_for_dismiss=True,
        )

    async def action_mkdir(self) -> None:
        """Make a directory."""
        await self.app.push_screen(
            MkdirDialog(
                popup_prompt=f"Make New Directory '{self._curr_path}'",
                emoji_markup_prepended=":open_file_folder:",
                curr_path=self._curr_path,
                initial_input=None,
            )
        )

    async def _download_files(self, files: MegaItems) -> None:
        """Helper method to download files.

        TODO: Check for existing files on system and handle them
        """
        if not files:
            self.log.warning("Did not receive any files to download!")
            return

        dl_len = len(files)
        for i, file in enumerate(files):
            self.post_message(
                StatusUpdate(message=f"Downloading ({i + 1}/{dl_len}) '{file.name}'")
            )
            await mega_get(target_path=str(DL_PATH), remote_path=str(file.path))
            rendered_emoji = Text.from_markup(text=":ballot_box_with_check:")
            title = Text.from_markup(f"[b]{rendered_emoji} download complete![/]")
            self.notify(
                f"'{file.name}' finished downloading ", title=f"{title}", markup=True
            )

    async def action_download(self) -> None:
        """Download the currently highlighted file or a selection of files.

        TODO: Ask for download path
        TODO: Display download status
        TODO: Ask for confirmation with large files
        """
        dl_items = self.selected_items

        await self._download_files(dl_items)

    async def action_cancel_download(self):
        pass

    async def action_pause_download(self):
        pass

    async def action_view_transfer_list(self):
        pass

    async def _move_files(self, files: MegaItems, new_path: MegaPath) -> None:
        """Helper function to move MegaItems to a new path."""
        if not files:
            self.log.warning("No files received to move.")
            return

        tasks: list[asyncio.Task[None]] = []
        for f in files:
            self.log.info(
                f"Queueing move for `{f.name}` from `{f.path}` to: `{new_path}`"
            )
            task = asyncio.create_task(mega_mv(file_path=f.path, target_path=new_path))
            tasks.append(task)

        # The function will wait here until all move operations are complete.
        await asyncio.gather(*tasks)
        self.log.info("All file move operations completed.")

    async def action_move_files(self):
        """Move selected files to current directory."""
        files = self.selected_items
        cwd = self._curr_path

        self.log.info(f"Moving files to {cwd}")
        await self._move_files(files, cwd)
        with self.app.batch_update():
            self.action_unselect_all_files()
            await self.action_refresh(True)

    # A helper to prepare all displayable contents of a row
    def _prepare_row_contents(self, node: MegaNode) -> tuple[Content, ...]:
        """Takes a MegaItem and returns a tuple of Content objects for a table
        row.
        """
        if node.is_dir:
            icon = self.NODE_ICONS["directory"]
            size_str = "-"
        else:
            icon = self.NODE_ICONS["file"]

            if not node.size:
                raise ValueError("Non directory node has no size information.")

            assert_type(node.size[1], MegaSizeUnits)
            size_str = f"{node.size[0]:.1f} {node.size[1].unit_str()}"

        cell_icon = Content(icon)
        cell_name = Content.from_rich_text(
            Text(text=node.name, overflow="ellipsis", no_wrap=True)
        )
        # NOTE: We can display time in different formats from here for the UI
        cell_mtime = Content.styled(text=str(node.mtime), style="italic")
        cell_size = Content(text=size_str)

        return (cell_icon, cell_name, cell_mtime, cell_size)

    def _update_list_on_success(self, path: MegaPath, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.log.debug(f"Updating UI for path: {path}")
        self._curr_path = path

        self.clear(columns=False)

        # Use a dictionary comprehension
        self._row_data_map = {item.handle: item for item in fetched_items}

        found_selected_items = False

        row_generator = (
            (node, self._prepare_row_contents(node)) for node in fetched_items
        )

        # Go through each item and create new row for them
        for node, row_cells in row_generator:
            # Pass data as individual arguments for each column

            rowkey = self.add_row(
                *row_cells,
                # Unique key to reference the node
                key=node.handle,
                # Height of each row
                height=self.FILELIST_ROW_HEIGHT,
                # Selection label should be empty
                label=self.NOT_SELECTED_LABEL,
            )
            if node.handle in self._selected_items:
                self.rows[rowkey].label = self.SELECTED_LABEL
                found_selected_items = True

        if found_selected_items:
            self.refresh()
            self._update_count += 1

        item_count = len(fetched_items)
        if item_count:
            self.styles.border_subtitle_style = self._BORDER_SUBTITLE_STYLES["normal"]
        else:
            self.styles.border_subtitle_style = self._BORDER_SUBTITLE_STYLES["empty"]

        self.border_subtitle = f"{len(fetched_items)} items"

    @work(
        exclusive=True,
        group="megacmd",
        name="fetch_files",
        description="mega-ls - Fetching dir listings",
    )
    async def fetch_files(self, path: MegaPath) -> MegaItems | None:
        """Asynchronously fetches items from MEGA for the given path.
        Returns the list of items on success, or None on failure.
        Errors are handled by posting LoadError message.
        """
        self.log.debug(f"Begun fetching nodes for path: {path}")
        # Fetch and sort items
        fetched_items: MegaItems = await mega_ls(path)

        if not fetched_items:
            self.log.debug(f"No items found in '{path}'")
            return None

        # Return the result
        return fetched_items

    async def load_directory(self, path: MegaPath | None = MEGA_ROOT_PATH) -> None:
        """Initiates asynchronous loading using the worker."""
        if not path:
            path = MEGA_ROOT_PATH

        self.log.info(f"Requesting load for directory: {path}")
        self._loading_path = path  # Track the path we are loading

        # Start the worker. Results handled by on_worker_state_changed.
        worker_obj: Worker[MegaItems | None] = self.fetch_files(path)

        fetched_items = await worker_obj.wait()

        # Cancelled
        if worker_obj.is_cancelled:
            self.log.debug(
                f"Worker to fetch files for path '{self._loading_path}' was cancelled."
            )
            return

        # Failed
        if not fetched_items:
            # Worker succeeded but returned None (folder is probably empty)
            self.log.warning(
                f"Fetch worker for '{self._loading_path}' succeeded but returned 'None' result."
            )
            fetched_items = ()

        # Success
        # Get number of files
        file_count = len(fetched_items)

        self.log.debug(
            f"Worker success for path '{self._loading_path}', item count: {file_count}"
        )
        # Update FileList

        with self.app.batch_update():
            self._update_list_on_success(self._loading_path, fetched_items)

        # We have successfully loaded the path
        self.post_message(self.PathChanged(path))

    def _get_curr_row_key(self) -> RowKey | None:
        """Return RowKey for the Row that the cursor is currently on."""
        if self.cursor_row < 0 or not self.rows:  # No selection or empty table
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

    @property
    def highlighted_item(self) -> MegaNode | None:
        """Return the MegaItem corresponding to the currently highlighted row."""
        row_key = self._get_curr_row_key()

        if not row_key:
            # We are in an empty directory!
            return None

        if not row_key.value:
            raise RuntimeError(
                "We should definitely have a 'value' attribute for our rowkey."
            )

        return self._row_data_map.get(row_key.value)

    @property
    def selected_or_highlighted_items(self) -> MegaItems:
        """Returns items that are selected.
        Default to returning highlighted item if is nothing selected.
        """
        # If we have selected items return those
        if self.selected_items:
            return self.selected_items

        # When nothing is highlighted
        if not self.highlighted_item:
            self.log.error(
                "Could not default to highlighted item, returning empty list."
            )
            return ()

        return (self.highlighted_item,)

    @property
    def selected_items(self) -> MegaItems:
        """Return MegaItem(s) that are currently selected."""
        # Get selected items
        return tuple(self._selected_items.values())

    # * Messages ################################################################
    class ToggledSelection(Message):
        """Message sent after item is selected by user."""

        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    class PathChanged(Message):
        """Message for when the path has changed.
        'PathChanged.path': The path changed into.
        """

        def __init__(self, path: MegaPath) -> None:
            super().__init__()
            self.path = path

    class LoadSuccess(Message):
        """Message sent when items are loaded successfully.
        'LoadSuccess.path': Newly loaded path.
        """

        def __init__(self, path: MegaPath) -> None:
            super().__init__()
            self.path = path

    class LoadError(Message):
        """Message sent when loading items fails.
        'LoadError.path': Path that failed to load.
        'LoadError.error': An error message.
        """

        def __init__(self, path: MegaPath, error: str) -> None:
            super().__init__()
            self.path = path
            self.error = error  # Include the error

    class EmptyDirectory(Message):
        """Message to signal the entered directory is empty."""

        def __init__(self) -> None:
            super().__init__()
