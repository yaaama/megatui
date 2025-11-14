"""FileList widget.
Contains actions and is the main way to interact with the application.
"""

# UI Components Related to Files
import asyncio
import os
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Final,
    LiteralString,
    assert_type,
    cast,
    override,
)

from rich.style import Style
from rich.text import Text
from textual import getters, on, work
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets._data_table import ColumnKey, RowDoesNotExist
from textual.worker import Worker

from megatui.mega.data import (
    MEGA_CURR_DIR,
    MEGA_ROOT_PATH,
    MegaNode,
    MegaPath,
    MegaSizeUnits,
)
from megatui.mega.megacmd import (
    MegaItems,
    mega_cd,
    mega_get,
    mega_ls,
    mega_mediainfo,
    mega_mv,
    mega_pwd,
)
from megatui.messages import (
    DeleteNodesRequest,
    MakeRemoteDirectory,
    RefreshRequest,
    RefreshType,
    RenameNodeRequest,
    StatusUpdate,
)
from megatui.ui.file_tree import UploadFilesModal
from megatui.ui.preview import PreviewMediaInfoModal
from megatui.ui.screens.confirmation import ConfirmationScreen
from megatui.ui.screens.mkdir import MkdirDialog
from megatui.ui.screens.rename import RenameDialog

if TYPE_CHECKING:
    from megatui.app import MegaTUI


@dataclass
class ColumnFormat:
    """A data class to hold the formatting for a column."""

    label: str
    """Column label displayed in the UI."""
    width: int
    """Width of column. """


class ColumnFormatting(Enum):
    """An enumeration for the column formatting using a `dataclass`."""

    SEL = ColumnFormat(label="", width=2)
    ICON = ColumnFormat(label="", width=4)
    NAME = ColumnFormat(label="Name", width=40)
    MODIFIED = ColumnFormat(label="Modified", width=10)
    SIZE = ColumnFormat(label="Size", width=8)

    @property
    def label(self) -> str:
        """Returns the label for the column."""
        return self.value.label

    @property
    def width(self) -> int:
        """Returns the width of the column."""
        return self.value.width


class FileList(DataTable[Any], inherit_bindings=False):
    """A DataTable widget to display files and their information."""

    if TYPE_CHECKING:
        app = getters.app(MegaTUI)

    # * UI Elements ###########################################################
    _FILELIST_ROW_HEIGHT: Final = 1
    """The height for rows in the table."""

    DEFAULT_CSS = """ """

    NODE_ICONS: ClassVar[dict[str, str]] = {"directory": "📁", "file": "📄"}
    """Icons for different kind of nodes."""

    COLUMN_INDEX_MAP = {member: i for i, member in enumerate(ColumnFormatting)}
    """Maps ColumnFormatting member to their index."""

    # Selection column key in our table
    SELECT_COLUMN_KEY = ColumnKey(ColumnFormatting.SEL.name)

    _SELECTION_STR: ClassVar[LiteralString] = "*"
    """Character to indicate a file has been selected."""
    _SELECTION_STYLE = Style(color="red", bold=True, italic=True)
    """Style for the node selection indicator."""
    SELECTED_LABEL = Content.from_text(
        Text(text=_SELECTION_STR, style=_SELECTION_STYLE)
    )
    """Label for rows that have been selected."""
    NOT_SELECTED_LABEL = Content.from_text(Text(text=" "))
    """Label for rows that are not selected (default)."""

    _BORDER_SUBTITLE_STYLES = {
        "empty": Style(color="white", bold=True, reverse=True),
        "normal": Style(color="white", bold=True, reverse=True),
    }

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
            description="Select A Node",
        ),
        # Unselect all files
        Binding(
            key="U",
            action="unselect_all_files",
            description="Unselect ALL Nodes (Global)",
        ),
        Binding(
            key="v",
            action="select_all_files",
            description="Select All Nodes in Directory",
        ),
        # Refresh current directory
        Binding(
            key="r",
            action="refresh",
            description="Refresh Current Directory",
        ),
        # Rename a node/file
        Binding(
            key="R",
            action="rename_node",
            description="Rename Node",
        ),
        # Make directory
        Binding(
            key="plus",
            action="mkdir",
            description="Create A New Directory",
        ),
        # Open local filesystem
        Binding(
            key="o",
            action="upload_file",
            description="Upload A File",
        ),
        Binding(
            key="i",
            action="view_mediainfo",
            description="View Media Info for Node",
        ),
        # Delete files
        Binding(
            key="D",
            action="delete_files",
            description="Delete Node",
        ),
        # Download files
        Binding(
            key="S",
            action="download",
            description="Download Node",
        ),
        # Move files
        Binding(
            key="M",
            action="move_files",
            description="Move Node to Current Directory",
        ),
    ]
    """ Binds that deal with files. """

    _NAVIGATION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            key="j",
            action="cursor_down",
            description="Move Cursor Down",
        ),
        Binding(
            key="k",
            action="cursor_up",
            description="Move Cursor Up",
        ),
        Binding(
            key="l,enter",
            action="navigate_in",
            description="Enter Directory",
        ),
        Binding(
            key="h,backspace",
            action="navigate_out",
            description="Go Up to Parent Directory",
        ),
        Binding(
            key="g",
            action="go_top",
            description="Jump to First Node",
        ),
        Binding(
            key="G",
            action="go_bottom",
            description="Jump to Last Node",
        ),
    ]
    """ Binds related to navigation. """

    BINDINGS: ClassVar[list[BindingType]] = _NAVIGATION_BINDINGS + _FILE_ACTION_BINDINGS

    _xdg_download_dir = os.getenv("XDG_DOWNLOAD_DIR")
    if _xdg_download_dir:
        download_path = Path(_xdg_download_dir, "mega_downloads")
    else:
        download_path = "downloadsmega_downloads"

    # * Initialisation #########################################################

    def __init__(self):
        super().__init__(
            id="filelist",
            show_header=True,
            cursor_type="row",
            header_height=2,
            zebra_stripes=False,
            show_row_labels=False,
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
        self.log.info("Adding columns to FileList")
        # Add columns with specified widths
        for column in ColumnFormatting:
            self.add_column(
                label=column.label,
                width=column.width,
                key=column.name,
            )

        self.log.debug(
            "Successfully added columns: '%s'",
            ", ".join(ColumnFormatting._member_names_),
        )

    # * Actions #########################################################

    def action_go_top(self):
        """Move cursor to the top most row."""
        self.action_scroll_top()

    def action_go_bottom(self):
        """Move cursor to the bottom most row."""
        self.action_scroll_bottom()

    async def action_view_mediainfo(self):
        """View media information for node under cursor."""
        highlighted = self._get_megaitem_at_cursor()

        if not highlighted:
            return

        mediainfo = await mega_mediainfo(nodes=highlighted)

        if not mediainfo:
            self.log.error(
                "Received invalid mediainfo for node '%s'", str(highlighted.path)
            )
            return

        self.app.push_screen(PreviewMediaInfoModal(media_info=mediainfo))

    @work(
        exclusive=True,
        description="Delete files. Displays a popup screen for confirmation.",
    )
    async def action_delete_files(self) -> None:
        """Delete files in the cloud, with confirmation prompt."""
        self.log.info("Deleting files")
        # Selected files
        selected = self.selected_or_highlighted_items
        if not selected:
            self.log.info("Cannot delete empty item.")
            return

        filenames = [str(item.path) for item in selected]
        filenames_str = ", ".join(filenames)
        file_count = len(selected)

        conf_result = await self.app.push_screen(
            ConfirmationScreen(
                title="Confirm Deletion",
                prompt=f"Delete '{file_count}' file(s)?",
                extra_info=filenames_str,
            ),
            wait_for_dismiss=True,
        )

        # If we get False
        if not conf_result:
            self.log.debug("Deletion cancelled: Confirmation prompt returned false.")
            return

        self.log.debug("Confirmed deletion.")
        self.app.post_message(DeleteNodesRequest(selected))

    async def action_upload_file(self) -> None:
        """Toggle upload file screen."""
        await self.app.push_screen(UploadFilesModal())

    # ** Navigation ############################################################

    async def action_navigate_in(self) -> None:
        """Navigate into directory under cursor."""
        selected_item_data = self.node_under_cursor

        # Selected item is None
        if not selected_item_data:
            return

        # Check if it's a regular file
        if selected_item_data.is_file:
            self.log.debug("Cannot enter into a FILE.")
            return

        # Folder to enter
        to_enter = selected_item_data.path
        # Add cursor index to our cursor position stack
        self._cursor_index_stack.append(self.cursor_row)

        await self.load_directory(to_enter)
        await mega_cd(target_path=to_enter)

    async def action_navigate_out(self) -> None:
        """Navigate to parent directory."""
        curr_path: str = self._curr_path.str

        # Avoid going above root "/"
        if curr_path == "/":
            return

        self.log.debug(f"Navigating out of directory {self._curr_path}")
        parent_path = self._curr_path.parent
        curs_index = (
            self._cursor_index_stack.pop() if len(self._cursor_index_stack) > 0 else 0
        )

        with self.app.batch_update():
            await self.load_directory(parent_path)
            await mega_cd(target_path=parent_path)
            self.move_cursor(row=curs_index)

    # ** File Actions ######################################################

    async def _perform_refresh(self) -> None:
        """
        The core logic to reload the directory from the cloud and update the table.
        """
        await self.load_directory(self._curr_path)

    @on(RefreshRequest)
    async def on_refresh_request(self, event: RefreshRequest) -> None:
        """Handles refresh requests sent to FileList."""
        event.stop()

        with self.app.batch_update():
            await self._perform_refresh()

            prev_row = event.cursor_row_before_refresh

            match event.type:
                case RefreshType.AFTER_DELETION:
                    self.action_unselect_all_files()
                    # If its a deletion command then we know prev_row is int
                    prev_row = cast(int, prev_row)
                    new_row_count = self.row_count
                    # Position cursor at the same spot, or the last item
                    target_cursor_index = min(prev_row, new_row_count - 1)

                    # If target index is within bounds then move it there
                    if target_cursor_index >= 0:
                        self.move_cursor(row=target_cursor_index, animate=False)

                case RefreshType.DEFAULT | RefreshType.AFTER_CREATION:
                    if prev_row is not None:
                        target_cursor_index = min(prev_row, self.row_count - 1)

                        # If target index is within bounds then move it there
                        if target_cursor_index >= 0:
                            self.move_cursor(row=target_cursor_index, animate=False)

    async def action_refresh(self, quiet: bool = False) -> None:
        """Refreshes current working directory."""
        if not quiet:
            self.post_message(
                StatusUpdate(f"Refreshing '{self._curr_path}'...", timeout=2)
            )

        self.post_message(
            RefreshRequest(
                type=RefreshType.DEFAULT, cursor_row_before_refresh=self.cursor_row
            )
        )

    # *** Selection #######################################################

    def _get_megaitem_at_row(self, row_key: str) -> MegaNode:
        """Return the MegaNode for a given row key string."""
        try:
            return self._row_data_map[row_key]
        except KeyError as e:
            self.log.error(
                f"Could not find data for row key '{row_key}'. State is inconsistent."
            )
            raise e

    def _get_curr_row_key(self) -> str | None:
        """Return RowKey for the Row that the cursor is currently on."""
        # No rows in the current view
        if not self.rows:
            return None

        try:
            # DataTable's coordinate system is (row, column)
            # self.cursor_coordinate.row gives the visual row index
            # We need the key of that row
            row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)

            return row_key.value

        except RowDoesNotExist:
            self.log.error("Could not return any row.")
            return None

    def _get_megaitem_at_cursor(self) -> MegaNode | None:
        """Returns MegaItem under the current cursor.

        Returns:
        MegaItem if there is one, else None.
        """
        row_key = self._get_curr_row_key()

        # Exit if there is a nonexistent rowkey or rowkey.value
        if not row_key:
            return None

        return self._get_megaitem_at_row(row_key)

    def _update_row_selection_indicator(self, row_key: str, selection_state: bool):
        """Helper function to update selection indicator cell for a row."""
        self.update_cell(
            row_key,
            self.SELECT_COLUMN_KEY,
            self.SELECTED_LABEL if selection_state else self.NOT_SELECTED_LABEL,
        )

    def _update_all_row_labels(self) -> None:
        """Updates all visible row labels in current view to their selection state."""
        # All selected items globally
        all_selected_keys = set(self._selected_items.keys())
        # All items in current view (directory)
        all_in_view_keys = set(self._row_data_map.keys())

        all_in_view_selected = all_selected_keys.intersection(all_in_view_keys)
        all_in_view_not_selected = all_in_view_keys.difference(all_in_view_selected)

        for key in all_in_view_selected:
            self._update_row_selection_indicator(key, True)

        for key in all_in_view_not_selected:
            self._update_row_selection_indicator(key, False)

        # Refresh the selection column to ensure all changes are visible
        self.refresh_column(self.COLUMN_INDEX_MAP[ColumnFormatting.SEL])

    def action_toggle_file_selection(self) -> None:
        """Toggles selection state of row under cursor."""
        # Get current row key
        row_key = self._get_curr_row_key()

        if not row_key:
            self.log.debug("Cannot toggle selection, cursor is not on a row.")
            return

        is_selected = row_key in self._selected_items

        if is_selected:
            del self._selected_items[row_key]

        # If it is not selected (more likely)
        else:
            # Add node to selected items dictionary
            self._selected_items[row_key] = self._row_data_map[row_key]

        # Add selection indicator to row
        self._update_row_selection_indicator(row_key, not is_selected)

        # Send message that selection has been toggled
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    def action_unselect_all_files(self) -> None:
        """Unselect all selected items GLOBALLY."""
        # If empty set, then return
        if not self._selected_items:
            return

        self._selected_items.clear()

        with self.app.batch_update():
            self._update_all_row_labels()
            self.app.post_message(self.ToggledSelection(0))

    def action_select_all_files(self) -> None:
        """Toggle selection of all files in current directory.

        This works like a classic 'invert-all' action, where selected items are
        then deselected and non-selected files are then toggled.
        """
        if not self._row_data_map:
            # No files in current view
            return

        # The symmetric difference gives us:
        # (selected_keys - in_view_keys) combined with (in_view_keys - selected_keys)
        final_keys = set(self._selected_items.keys()).symmetric_difference(
            set(self._row_data_map.keys())
        )

        # 2. Build the new dictionary from the final set of keys.
        self._selected_items = {  # pyright: ignore[reportAttributeAccessIssue]
            key: self._selected_items.get(key) or self._row_data_map[key]
            for key in final_keys
        }

        # Batch update so it doesn't cause visual artifacts
        with self.app.batch_update():
            self._update_all_row_labels()
            self.post_message(self.ToggledSelection(len(self._selected_items)))

    @work
    async def action_rename_node(self) -> None:
        """Rename a file by showing a dialog to prompt for the new name.

        TODO: Make this open a file editor when multiple files are selected.
        """
        selected_item = self.node_under_cursor

        if not selected_item:
            return

        node_path = str(selected_item.path)

        if node_path == "/":
            return

        results = await self.app.push_screen(
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

        if (not results[0]) or (not results[1]):
            return

        self.app.post_message(RenameNodeRequest(results[0], results[1]))

    @work
    async def action_mkdir(self) -> None:
        """Make a directory."""
        results = await self.app.push_screen(
            MkdirDialog(
                popup_prompt=f"Make New Directory '{self._curr_path}'",
                emoji_markup_prepended=":open_file_folder:",
                curr_path=self._curr_path,
                initial_input=None,
            ),
            wait_for_dismiss=True,
        )

        if not results:
            return

        self.app.post_message(MakeRemoteDirectory(results))

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
            await mega_get(
                target_path=str(self.download_path), remote_path=str(file.path)
            )
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
        dl_items = self.selected_or_highlighted_items or ()

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
            size_str = f"{node.size[0]:.2f} {node.size[1].unit_str()}"

        if node.handle in self._selected_items:
            _sel_content = self.SELECTED_LABEL
        else:
            _sel_content = self.NOT_SELECTED_LABEL

        cell_selection = _sel_content.pad_right(ColumnFormatting.SEL.width).simplify()

        cell_icon = Content(icon).pad_right(ColumnFormatting.ICON.width).simplify()
        cell_name = (
            Content.from_rich_text(Text(text=node.name, no_wrap=True, end=""))
            .truncate(
                max_width=(ColumnFormatting.NAME.width),
                ellipsis=True,
                pad=True,
            )
            .simplify()
        )
        # NOTE: We can display time in different formats from here for the UI
        cell_mtime = (
            Content.styled(text=str(node.mtime), style="italic")
            .pad_right(ColumnFormatting.MODIFIED.width)
            .simplify()
        )
        cell_size = (
            Content(text=size_str).pad_right(ColumnFormatting.SIZE.width).simplify()
        )

        final = (cell_selection, cell_icon, cell_name, cell_mtime, cell_size)
        return final

    def _update_list_on_success(self, path: MegaPath, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.log.debug(f"Updating UI for path: {path}")
        self._curr_path = path

        self.clear(columns=False)

        # Use a dictionary comprehension
        self._row_data_map = {item.handle: item for item in fetched_items}

        row_contents_generator = (
            (node, self._prepare_row_contents(node)) for node in fetched_items
        )

        # Go through each item and create new row for them
        for node, row_cells in row_contents_generator:
            # Pass data as individual arguments for each column
            self.add_row(
                *row_cells,
                # Unique key to reference the node
                key=node.handle,
                # Height of each row
                height=self._FILELIST_ROW_HEIGHT,
            )

        item_count = len(fetched_items)
        # Adjust border subtitle styling based on number of items
        if item_count:
            self.styles.border_subtitle_style = self._BORDER_SUBTITLE_STYLES["normal"]
            self.border_subtitle = f"{item_count} items"
        else:
            self.styles.border_subtitle_style = self._BORDER_SUBTITLE_STYLES["empty"]
            self.border_subtitle = "Empty Directory."

    @work(
        exclusive=True,
        name="fetch_files",
    )
    async def _fetch_files(self, path: MegaPath) -> MegaItems | None:
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

    async def load_directory(self, path: MegaPath = MEGA_CURR_DIR) -> None:
        """Loads and updates UI with directory specified.
        If path is not specified, then it will load the contents of the current directory.
        """
        # If we are requesting to load current directory
        if path == MEGA_CURR_DIR:
            # Get the full path of the current directory
            path = await mega_pwd()

        self.log.info(f"Requesting load for directory: {path}")
        self._loading_path = path  # Track the path we are loading

        # Start the worker. Results handled by on_worker_state_changed.
        worker_obj: Worker[MegaItems | None] = self._fetch_files(path)

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

    @property
    def node_under_cursor(self) -> MegaNode | None:
        """Try return the node under the cursor."""
        row_key = self._get_curr_row_key()

        if not row_key:
            # We are in an empty directory!
            return None

        return self._row_data_map[row_key]

    @property
    def selected_or_highlighted_items(self) -> MegaItems | None:
        """Returns items that are selected.
        Default to returning highlighted item if is nothing selected.
        """
        # If we have selected items return those
        if self.selected_items:
            return self.selected_items

        # When nothing is highlighted
        if not self.node_under_cursor:
            self.log.info(
                "Could not default to highlighted item, table has no rows probably."
            )
            return None

        return (self.node_under_cursor,)

    @property
    def selected_items(self) -> MegaItems:
        """Return MegaNode(s) that are currently selected."""
        # Get selected items
        return tuple(self._selected_items.values())

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
