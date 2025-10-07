"""FileList widget.
Contains actions and is the main way to interact with the application.
"""
# UI Components Related to Files

from collections import deque
from pathlib import Path, PurePath
from typing import (
    Annotated,
    Any,
    ClassVar,
    LiteralString,
    override,
)

from rich.text import Text
from textual import work
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets._data_table import RowDoesNotExist, RowKey
from textual.worker import Worker  # Import worker types

import megatui.mega.megacmd as m
from megatui.mega.megacmd import MegaCmdError, MegaItem, MegaItems
from megatui.messages import StatusUpdate, UploadRequest
from megatui.ui.file_tree import UploadFilesModal
from megatui.ui.screens.mkdir import MkdirDialog
from megatui.ui.screens.rename import RenameDialog

DL_PATH = Annotated[Path, "Default download path."]


class FileList(DataTable[Any], inherit_bindings=False):  # pyright: ignore[reportExplicitAny]
    """A DataTable widget to display files and their information."""

    # * UI Elements ###########################################################

    DEFAULT_CSS = """ """

    FILE_ICON_MARKUP: ClassVar[LiteralString] = ":page_facing_up:"
    """ Markup used for file icon. """

    DIR_ICON_MARKUP: ClassVar[LiteralString] = ":file_folder:"
    """ Markup used for directory icon. """

    SELECTION_INDICATOR: ClassVar[LiteralString] = "*"
    """ Character to indicate a file has been selected. """

    BORDER_SUBTITLE = ""
    """ Border subtitle. """

    COLUMNS: ClassVar[list[LiteralString]] = ["icon", "name", "modified", "size"]
    DEFAULT_COLUMN_WIDTHS: tuple[int, ...] = (2, 50, 12, 8)

    # * State #################################################################

    _row_data_map: dict[str, MegaItem]
    """ Row and associated MegaItem mapping for current directory. """

    _selected_items: dict[str, MegaItem]
    """ Dict to store selected MegaItem(s), indexed by their handles. """

    _curr_path: str
    """ Current path we are in. """

    _loading_path: str
    """ Path we are currently loading. """

    _path_history: deque[int]
    """ Stores cursor index before navigating into a child folder. """

    # * Bindings ###############################################################
    _FILE_ACTION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            key="r",
            key_display="r",
            action="refresh",
            description="refresh current directory",
            show=True,
        ),
        Binding(
            key="R",
            key_display="R",
            action="rename_node",
            description="rename a node",
            show=True,
        ),
        Binding(
            key="plus",
            key_display="+",
            action="mkdir",
            description="make new directory",
            show=True,
        ),
        Binding(
            key="space",
            key_display="␠",
            action="toggle_file_selection",
            description="select a file",
            show=True,
        ),
        Binding(
            key="u",
            key_display="u",
            action="unselect_all_files",
            description="unselect all",
            show=True,
        ),
        Binding(key="o", key_display="o", action="upload_file", description="upload"),
        Binding(key="D", key_display="D", action="delete_files", description="delete"),
        Binding(key="f3", key_display="f3", action="download", description="download"),
        Binding(
            "f4",
            key_display="f4",
            action="move_files",
            description="move",
        ),
    ]
    """ Binds that deal with files. """

    _NAVIGATION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Cursor Down", key_display="j", show=False),
        Binding("k", "cursor_up", "Cursor Up", key_display="k", show=False),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l", show=False),
        Binding("h,backspace", "navigate_out", "Parent Dir", key_display="h", show=False),
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
        self._curr_path = "/"
        self._loading_path = self._curr_path
        self._row_data_map = {}
        self._selected_items = {}
        self._path_history = deque()

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

    # * Actions #########################################################

    async def action_delete_files(self) -> None:
        self.log.info("Deleting files")
        # Selected files
        selected = self.selected_or_highlighted_items

        for item in selected:
            if item.is_dir:
                await m.mega_rm(file=item.path, flags=("-r", "-f"))
            await m.mega_rm(file=item.path, flags=None)

        with self.app.batch_update():
            self.action_unselect_all_files()
            deleted_count = len(selected)
            cursor_index = self.cursor_row - deleted_count
            await self.action_refresh(quiet=True)
            self.move_cursor(row=cursor_index)

        filenames = [str(item.full_path) for item in selected]
        ", ".join(filenames)

        self.notify(
            message=f"Deleted [bold][red]{len(filenames)}[/red][/bold] file(s).",
            title="Deletion",
        )

    @work(name="upload")
    async def on_upload_request(self, msg: UploadRequest):
        self.log.info("Uploading file(s)")

        files = [str(path) for path in msg.files]
        destination = str(msg.destination) if msg.destination else self._curr_path

        filenames = ", ".join(files)
        self.log.debug(f"Destination: `{destination}`\nFiles:\n`{filenames}`")

        await m.mega_put(local_path=tuple(files), target_path=destination, queue=True)

    async def action_upload_file(self) -> None:
        """Toggle upload file screen."""
        await self.app.push_screen(UploadFilesModal())

    # ** Navigation ############################################################

    async def action_navigate_in(self) -> None:
        """Navigate into directory under cursor."""
        selected_item_data = self.highlighted_item
        # Fail: Selected item is None.
        if not selected_item_data:
            self.log.info("Nothing to navigate into.")
            return

        # Fail: Is a regular file
        if selected_item_data.is_file:  # Check if it's a directory
            self.log.debug("Cannot enter into a file.")
            return

        # Folder to enter
        to_enter = selected_item_data.full_path
        # Add cursor index to our cursor position stack
        self._path_history.append(self.cursor_row)
        path_str: str = str(to_enter)

        # self.post_message(StatusUpdate(f"Loading '{to_enter}'...", timeout=2))
        await self.load_directory(path_str)
        await m.mega_cd(target_path=path_str)

    async def action_navigate_out(self) -> None:
        """Navigate to parent directory."""
        self.log.info(f"Navigating out of directory {self._curr_path}")
        curr_path: str = self._curr_path

        # Avoid going above root "/"
        if curr_path == "/":
            self.post_message(
                StatusUpdate("Cannot navigate out any further, you're already at '/'")
            )
            return

        parent_path: PurePath = PurePath(curr_path).parent
        curs_index = self._path_history.pop()

        # Useful to stop the flickering
        with self.app.batch_update():
            await self.load_directory(str(parent_path))
            await m.mega_cd(target_path=str(parent_path))
            self.move_cursor(row=curs_index)

    # ** File Actions ######################################################
    async def action_refresh(self, quiet: bool = False) -> None:
        """Refreshes current working directory."""
        if not quiet:
            self.post_message(StatusUpdate(f"Refreshing '{self._curr_path}'...", timeout=2))

        with self.app.batch_update():
            # Keep point at curr index when refreshing
            curs_index = self.cursor_row
            await self.load_directory(self._curr_path)
            curs_index = min(curs_index, self.row_count - 1)
            self.move_cursor(row=curs_index)

    # *** Selection #######################################################
    def _get_row_megaitem(self, rowkey: RowKey | str) -> MegaItem | None:
        """Return MegaItem for row index (rowkey).

        Args:
            rowkey: The rowkey (index) to return MegaItem for.

        Returns:
            MegaItem if item exists at RowKey, or None if none.
        """
        assert rowkey, "Passed in an empty rowkey!"

        key: str
        # If its a RowKey type, grab the value (str)
        if isinstance(rowkey, RowKey):
            assert rowkey.value
            key = rowkey.value
        else:
            key = rowkey

        try:
            # Get the MegaItem
            row_item: MegaItem = self._row_data_map[key]
            return row_item
        except KeyError:
            self.log.error(f"Could not find data for row key '{key}'. State is inconsistent.")
            return None

    def _get_curr_row_megaitem(self) -> MegaItem | None:
        """Returns MegaItem under the current cursor.

        Returns:
        MegaItem if there is one, else None.
        """
        row_key = self._get_curr_row_key()

        # Exit if there is a nonexistent rowkey or rowkey.value
        if not row_key or not row_key.value:
            return None

        return self._get_row_megaitem(row_key)

    def action_toggle_file_selection(self) -> None:
        """Toggles selection state of row under cursor."""
        megaitem = self._get_curr_row_megaitem()

        # Exit if there is no megaitem
        if not megaitem:
            self.log.info("No item to toggle selection.")
            return

        item_handle = megaitem.handle

        # Debugging purposes
        row_key = self._get_curr_row_key()
        assert row_key

        # Unselect already selected items
        if item_handle in self._selected_items:
            del self._selected_items[item_handle]
            new_label = Text("")
            self.log.debug(f"Deselected row: {row_key.value}")

        else:
            # Action: SELECT
            self._selected_items[item_handle] = megaitem
            new_label = Text(f"{self.SELECTION_INDICATOR} ", style="bold red")
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

        new_label = Text("")
        for key in self._selected_items:
            # Check if selected item is within the curr list of rows
            if key in self.rows:
                self.rows[RowKey(key)].label = new_label
            else:
                pass

        self._selected_items.clear()

        self.refresh()
        self._update_count += 1

        self.post_message(self.ToggledSelection(0))

    def action_select_item(self) -> None:
        """Toggles the selection state of the currently hovered-over item (row).
        Selected rows are MEANT to be visually highlighted.
        """
        row_key = self._get_curr_row_key()

        if not row_key or not row_key.value:
            self.log.info("No current row key to select/deselect.")
            return

        try:
            # Get the MegaItem
            row_item: MegaItem = self._row_data_map[row_key.value]
            # Get handle
            item_handle = row_item.handle
        except KeyError:
            self.log.error(
                f"Could not find data for row key '{row_key.value}'. State is inconsistent."
            )
            return

        # Unselect already selected items
        if item_handle in self._selected_items:
            del self._selected_items[item_handle]
            new_label = Text(" ")
            log_message = f"Deselected row: {row_key.value}"

        else:
            # Action: SELECT
            self._selected_items[item_handle] = row_item
            new_label = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
            log_message = f"Selected row: {row_key.value}"

        self.log.info(log_message)
        self.rows[row_key].label = new_label

        self.refresh()
        # Need this hack to refresh the UI
        self._update_count += 1
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    # ** Rename node ######################################################

    @work(
        group="megacmd",
        name="rename_file",
        description="Renames a file/directory.",
    )
    async def action_rename_node(self) -> None:
        """Rename a file by showing a dialog to prompt for the new name.

        TODO: Make this open a file editor when multiple files are selected.
        """
        self.log.info("Renaming file.")

        selected_item: MegaItem | None = self.highlighted_item

        if not selected_item:
            self.log.error("No highlighted file to rename.")
            return

        node_path: str = selected_item.path

        assert node_path != "/", "Cannot rename the root directory."

        async def _on_rename_dialog_closed(result: tuple[str, MegaItem] | None) -> None:
            """Callback executed after the RenameDialog closes.

            Handles the actual file renaming logic.
            """
            # We have not got a result
            if not result:
                return

            new_name, node = result
            if not new_name or not node:
                self.log.debug("File rename operation was cancelled or failed.")
                return

            self.log.info(f"Renaming node `{node.name}` to `{new_name}`")

            await m.node_rename(node.path, new_name)

        await self.app.push_screen(
            RenameDialog(
                popup_prompt=f"Rename {selected_item.name}",
                node=selected_item,
                emoji_markup_prepended=(
                    ":page_facing_up:" if selected_item.is_file else ":file_folder:"
                ),
                initial_input=selected_item.name,
            ),
            callback=_on_rename_dialog_closed,
            wait_for_dismiss=True,
        )

    @work(
        group="megacmd",
        name="make_dir",
        description="Make a new directory.",
    )
    async def action_mkdir(self) -> None:
        """Make a directory."""

        async def make_directory(name: str | None) -> None:
            # If no name return
            if not name:
                return

            # TODO Should use set comprehension
            filenames: set[str] = set()

            for item in self._row_data_map.values():
                filenames.add(item.name)

            # If name is duplicate
            if name in filenames:
                self.log.info(f"File already exists with the name '{name}'.")
                self.post_message(StatusUpdate(message=f"File '{name}' already exists!"))
                return

            success = await m.mega_mkdir(name=name, path=None)
            if not success:
                self.post_message(
                    StatusUpdate(message=f"Could not create directory '{name}' for some reason.")
                )
                return

            await self.action_refresh()

        await self.app.push_screen(
            MkdirDialog(
                popup_prompt=f"Make New Directory(s) '{self._curr_path}'",
                emoji_markup_prepended=":open_file_folder:",
                initial_input=None,
            ),
            callback=make_directory,
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
            await m.mega_get(
                target_path=str(DL_PATH),
                remote_path=str(file.full_path),
                is_dir=file.is_dir,
            )
            rendered_emoji = Text.from_markup(text=":ballot_box_with_check:")
            title = Text.from_markup(f"[b]{rendered_emoji} download complete![/]")
            self.notify(f"'{file.name}' finished downloading ", title=f"{title}", markup=True)

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

    async def move_files(self, files: MegaItems, new_path: str) -> None:
        """Helper function to move MegaItems to a new path."""
        if not files:
            self.log.warning("No files received to move.")
            return

        for f in files:
            self.log.info(f"Moving `{f.name}` from `{f.path}`  to: `{new_path}`")
            await m.mega_mv(file_path=f.path, target_path=new_path)

    async def action_move_files(self):
        """Move selected files to current directory."""
        files = self.selected_items
        cwd = self._curr_path

        self.log.info(f"Moving files to {cwd}")
        await self.move_files(files, cwd)
        self.action_unselect_all_files()
        await self.action_refresh(True)

    async def action_delete_file(self):
        pass

    async def action_upload_files(self):
        pass

    # A helper to prepare all displayable contents of a row
    def _prepare_row_contents(self, node: MegaItem) -> tuple[Content, ...]:
        """Takes a MegaItem and returns a tuple of Content objects for a table
        row.
        """
        if node.is_dir:
            icon_markup = self.DIR_ICON_MARKUP
            size_str = ""
        else:
            icon_markup = self.FILE_ICON_MARKUP
            size_str = f"{node.size:.1f} {node.size_unit.unit_str()}"

        cell_icon = Content.from_rich_text(Text.from_markup(icon_markup))
        cell_name = Content.from_rich_text(
            Text(text=node.name, overflow="ellipsis", no_wrap=True)
        )
        # NOTE: We can display time in different formats from here for the UI
        cell_mtime = Content.from_rich_text(Text(text=str(node.mtime), style="italic"))
        cell_size = Content(text=size_str)

        return (cell_icon, cell_name, cell_mtime, cell_size)

    def _update_list_on_success(self, path: str, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.log.debug(f"Updating UI for path: {path}")
        self._curr_path = path

        self.clear(columns=False)

        # Use a dictionary comprehension
        self._row_data_map = {item.handle: item for item in fetched_items}

        height: int = 1
        selection_label = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
        found_selected_items: bool = False

        row_generator = ((node, self._prepare_row_contents(node)) for node in fetched_items)

        # Go through each item and create new row for them
        for node, row_cells in row_generator:
            # Pass data as individual arguments for each column
            rowkey = self.add_row(
                *row_cells,
                # Unique key to reference the node
                key=node.handle,
                # Height of each row
                height=height,
                # Selection label should be empty
                label=" ",
            )
            if node.handle in self._selected_items:
                self.rows[rowkey].label = selection_label
                found_selected_items = True

        if found_selected_items:
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
        """Asynchronously fetches items from MEGA for the given path.
        Returns the list of items on success, or None on failure.
        Errors are handled by posting LoadError message.
        """
        self.log.info(f"FileList: Worker starting fetch for path: {path}")
        try:
            # Fetch and sort items
            fetched_items: MegaItems = await m.mega_ls(path)
            # Return the result or empty list
            return fetched_items or ()

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
        file_count: int = len(fetched_items)

        self.log.debug(f"Worker success for path '{self._loading_path}', items: {file_count}")
        # Update FileList

        with self.app.batch_update():
            self._update_list_on_success(self._loading_path, fetched_items)

        # We have successfully loaded the path
        # self.post_message(self.LoadSuccess(path))
        # Path *successfully* changed
        self.post_message(self.PathChanged(path))

        # If the count is 0 send a status update
        if file_count == 0:
            self.post_message(self.EmptyDirectory())

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
        except Exception as e:
            # Catch potential errors if cursor is out of sync
            self.log.error(f"Error getting current row. {e}")
            return None

    def get_column_widths(self):
        """Get optimal widths for table columns.
        Returns a tuple of widths.
        """
        pass

    @property
    def highlighted_item(self) -> MegaItem | None:
        """Return the MegaItem corresponding to the currently highlighted row."""
        row_key = self._get_curr_row_key()

        if not row_key:
            # We are in an empty directory!
            return None

        assert row_key.value, "We should definitely have a 'value' attribute for our rowkey."

        return self._row_data_map.get(row_key.value)

    @property
    def selected_or_highlighted_items(self) -> MegaItems:
        """Returns items that are selected.
        Default to returning highlighted item if is nothing selected.
        """
        # If we have selected items return those
        if len(self._selected_items.keys()) > 0:
            return tuple(self._selected_items.values())

        # When we don't have any items selected
        highlighted = self.highlighted_item

        # When nothing is highlighted
        if not highlighted:
            self.log.error("Could not default to highlighted item, returning empty list.")
            return ()

        return (highlighted,)

    @property
    def selected_items(self) -> MegaItems:
        """Return MegaItem(s) that are currently selected."""
        # Get selected items
        return tuple(self._selected_items.values())

    # * Messages ################################################################
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
