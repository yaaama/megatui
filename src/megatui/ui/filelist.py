"""
FileList module. Contains actions and is the main way to interact with the
application.
"""
# UI Components Related to Files

from pathlib import Path, PurePath
from typing import Annotated, Any, ClassVar, LiteralString, override

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
from megatui.ui.screens.mkdir import MkdirDialog
from megatui.ui.screens.rename import NodeInfoDict, RenameDialog

DL_PATH = Annotated[Path, "Default download path."]


class FileList(DataTable[Any], inherit_bindings=False):
    """A DataTable widget to display files and their information."""

    # * Constants ###################################################################

    FILE_ICON_MARKUP: ClassVar[LiteralString] = ":page_facing_up:"
    """ Markup used for file icon. """

    DIR_ICON_MARKUP: ClassVar[LiteralString] = ":file_folder:"
    """ Markup used for directory icon. """

    SELECTION_INDICATOR: ClassVar[LiteralString] = "*"
    """ Character to indicate a file has been selected. """

    # * UI Elements ###########################################################

    DEFAULT_CSS = """ """

    border_subtitle: str
    """ Border subtitle. """

    curr_path: str
    """ Current path we are in. """

    _loading_path: str
    """ Path we are currently loading. """

    COLUMNS: ClassVar[list[LiteralString]] = ["icon", "name", "modified", "size"]
    DEFAULT_COLUMN_WIDTHS = (2, 50, 12, 8)

    # * State #################################################################

    _row_data_map: dict[str, MegaItem]
    """ Row and associated MegaItem mapping for current directory. """

    _selected_items: dict[str, MegaItem]
    """ Dict to store selected MegaItem(s), indexed by their """

    # * Bindings ###############################################################
    _FILE_ACTION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="r", action="refresh", description="Refresh", show=True),
        Binding(key="R", action="rename_file", description="Rename a file", show=True),
        Binding(key="plus", action="mkdir", description="mkdir", show=True),
        Binding(
            key="space",
            action="toggle_file_selection",
            description="Select file",
            show=True,
        ),
        Binding(
            key="u",
            action="unselect_all_files",
            description="Unselect all items",
            show=True,
        ),
        Binding("f3", "download", "download file", key_display="f3"),
        Binding("f4", "move_files", "move files", key_display="f4"),
    ]
    """ Binds that deal with files. """

    _NAVIGATION_BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l"),
        Binding("h,backspace", "navigate_out", "Parent Dir", key_display="h"),
    ]
    """ Binds related to navigation. """

    BINDINGS: ClassVar[list[BindingType]] = _NAVIGATION_BINDINGS + _FILE_ACTION_BINDINGS

    # * Initialisation #########################################################

    def __init__(self):
        # Initialise the DataTable widget
        super().__init__()
        self.id = "file_list"
        self.cursor_type = "row"
        self.show_cursor = True
        self.show_header = True
        self.header_height = 2
        self.zebra_stripes = False
        self.show_row_labels = True
        # self.cursor_foreground_priority = ("renderable",)
        # self.cursor_background_priority = ("renderable",)
        # self.cell_padding = 0

        # Extra UI Elements

        # TODO: Think of something useful to add here
        # self.border_title = "MEGA"
        self.border_subtitle = "Initializing view..."
        self.curr_path = "/"
        self._loading_path = self.curr_path
        self._row_data_map = {}
        self._selected_items = {}
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

    # * Actions #########################################################

    # ** Navigation ############################################################
    async def action_navigate_in(self) -> None:
        """Navigate into a directory."""
        selected_item_data = self.highlighted_item
        # Fail: Selected item is None.
        if not selected_item_data:
            self.log.info("Nothing to navigate into.")
            return

        # Fail: Is a regular file
        if selected_item_data.is_file():  # Check if it's a directory
            self.log.debug("Cannot enter into a file.")
            return

        to_enter = selected_item_data.full_path
        path_str: str = str(to_enter)

        # self.post_message(StatusUpdate(f"Loading '{to_enter}'...", timeout=2))
        await self.load_directory(path_str)
        await m.mega_cd(target_path=path_str)

    async def action_navigate_out(self) -> None:
        """Navigate to parent directory."""
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
        await m.mega_cd(target_path=str(parent_path))

    # ** File Actions ######################################################
    async def action_refresh(self, quiet: bool = False) -> None:
        """Refreshes the current working directory."""
        if not quiet:
            self.post_message(
                StatusUpdate(f"Refreshing '{self.curr_path}'...", timeout=0)
            )

        await self.load_directory(self.curr_path)

    # *** Selection #######################################################
    def _get_row_megaitem(self, rowkey: RowKey | str) -> MegaItem | None:
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
            self.log.error(
                f"Could not find data for row key '{key}'. State is inconsistent."
            )
            return None

    def action_toggle_file_selection(self) -> None:
        """Toggles the selection state of the currently hovered-over item (row)."""
        row_key = self._get_curr_row_key()

        # Exit if there is a nonexistent rowkey or rowkey.value
        if not row_key or not row_key.value:
            self.log.info("No current row key to select/deselect.")
            return

        megaitem = self._get_row_megaitem(row_key)

        # Exit if there is no megaitem
        if not megaitem:
            return

        item_handle = megaitem.handle

        # Unselect already selected items
        if item_handle in self._selected_items:
            del self._selected_items[item_handle]
            new_label = Text(" ")
            log_message = f"Deselected row: {row_key.value}"

        else:
            # Action: SELECT
            self._selected_items[item_handle] = megaitem
            new_label = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
            log_message = f"Selected row: {row_key.value}"

        self.log.info(log_message)
        self.rows[row_key].label = new_label

        self.refresh()
        self._update_count += 1
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    def action_unselect_all_files(self) -> None:
        """Unselect all selected items (if there are any)."""
        if len(self._selected_items) == 0:
            self.log.debug("No items selected for us to unselect.")
            return

        self._selected_items.clear()

        self.refresh()
        self._update_count += 1

        self.post_message(self.ToggledSelection(0))

    @work(
        exclusive=True,
        group="megacmd",
        name="file_rename",
        description="Renaming file.",
    )
    async def action_rename_file(self) -> None:
        """Rename a file by showing a dialog to prompt for the new name.

        TODO: Make this open a file editor when multiple files are selected.
        """
        self.log.info("Renaming file.")

        selected_item = self.highlighted_item

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

        await self.app.push_screen(
            RenameDialog(
                popup_prompt=f"Rename {selected_item.name}",
                node_info=node_info,
                emoji_markup_prepended=(
                    ":page_facing_up:" if selected_item.is_file() else ":file_folder:"
                ),
                initial_input=selected_item.name,
            ),
            callback=self._on_rename_dialog_closed,
        )

    async def _on_rename_dialog_closed(
        self, result: tuple[str, NodeInfoDict] | None
    ) -> None:
        """Callback executed after the RenameDialog closes.

        Handles the actual file renaming logic.
        """
        if not result or not result[0] or not result[1]:
            self.log.info("File rename operation was cancelled or failed.")
            return

        new_name, node_info = result
        self.log.info(f"Renaming file `{node_info['name']}` to `{new_name}`")

        file_path: str = node_info["path"]

        await m.node_rename(file_path, new_name)
        await self.action_refresh()

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
        self._update_count += 1
        self.post_message(self.ToggledSelection(len(self._selected_items)))

    @work(
        exclusive=True,
        group="megacmd",
        name="mkdir",
        description="Make directory.",
    )
    async def action_mkdir(self) -> None:
        """Make a directory."""

        async def make_directory(name: str | None) -> None:
            # If no name return
            if not name:
                return

            # FIXME Should use set comprehension
            filenames: set[str] = set()

            for item in self._row_data_map.values():
                filenames.add(item.name)

            # If name is duplicate
            if name in filenames:
                self.log.info(f"File already exists with the name '{name}'.")
                self.post_message(
                    StatusUpdate(message=f"File '{name}' already exists!")
                )
                return

            success = await m.mega_mkdir(name=name, path=None)
            if not success:
                self.post_message(
                    StatusUpdate(
                        message=f"Could not create directory '{name}' for some reason."
                    )
                )
                return

            await self.action_refresh()

        await self.app.push_screen(
            MkdirDialog(
                popup_prompt=f"Make New Directory(s) at: '{self.curr_path}'",
                emoji_markup_prepended=":open_file_folder:",
                initial_input=None,
            ),
            callback=make_directory,
        )

    async def download_files(self, files: list[MegaItem]) -> None:
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
                is_dir=file.is_dir(),
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
        dl_items = self.selected_items

        await self.download_files(dl_items)

    async def action_cancel_download(self):
        pass

    async def action_pause_download(self):
        pass

    async def action_view_transfer_list(self):
        pass

    async def move_files(self, files: list[MegaItem], new_path: str) -> None:
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
        cwd = self.curr_path

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
        if node.is_dir():
            icon_markup = self.DIR_ICON_MARKUP
            size_str = ""
        else:
            icon_markup = self.FILE_ICON_MARKUP
            size_str = f"{node.size:.1f} {node.size_unit.unit_str()}"

        cell_icon = Content.from_rich_text(Text.from_markup(icon_markup))
        cell_name = Content.from_rich_text(
            Text(text=node.name, overflow="ellipsis", no_wrap=True)
        )
        cell_mtime = Content.from_rich_text(Text(text=str(node.mtime), style="italic"))
        cell_size = Content(text=size_str)

        return (cell_icon, cell_name, cell_mtime, cell_size)

    def _update_list_on_success(self, path: str, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.log.debug(f"Updating UI for path: {path}")
        self.curr_path = path

        self.clear(columns=False)

        # Use a dictionary comprehension
        self._row_data_map = {item.handle: item for item in fetched_items}

        height: int = 1
        selection_label = Text(f"{self.SELECTION_INDICATOR}", style="bold italic red")
        found_selected_items: bool = False

        # Go through each item and create new row for them
        for node in fetched_items:
            # Prepare data for each cell in the row

            row_cells = self._prepare_row_contents(node)

            # Pass data as individual arguments for each column
            rowkey = self.add_row(
                *row_cells,
                # Unique key to reference the node
                key=node.handle,
                # Height of each row
                height=height,
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
            fetched_items = []

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

        assert row_key.value, (
            "We should definitely have a 'value' attribute for our rowkey."
        )

        return self._row_data_map.get(row_key.value)

    @property
    def selected_or_highlighted_items(self) -> MegaItems:
        """Returns items that are selected.
        Default to returning highlighted item if is nothing selected.
        """
        # If we have selected items return those
        if len(self._selected_items.keys()) > 0:
            return list(self._selected_items.values())

        # When we don't have any items selected
        highlighted = self.highlighted_item

        # When nothing is highlighted
        if not highlighted:
            self.log.error(
                "Could not default to highlighted item, returning empty list."
            )
            return []

        return [highlighted]

    @property
    def selected_items(self) -> MegaItems:
        """Return MegaItem(s) that are currently selected."""
        # Get selected items
        return list(self._selected_items.values())

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
