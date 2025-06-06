# UI Components Related to Files
from pathlib import PurePath
from typing import override

from rich.text import Text
from textual import work
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import DataTable
from textual.worker import Worker  # Import worker types

import megatui.mega.megacmd as m
from megatui.mega.megacmd import MegaCmdError, MegaItem, MegaItems
from megatui.messages import StatusUpdate
from megatui.ui.screens.rename import NodeInfoDict, RenameDialog


###########################################################################
# FileList
###########################################################################
class FileList(DataTable[Text]):
    """
    A DataTable widget to display multiple FileItems
    """

    """
    All MegaItems in the current directory.
    TODO: Make this into a map of directories to items => dict[Dir, items[MegaItems]]
    This can be used to cache directories.
    """

    border_subtitle: str
    """ Border subtitle. """

    curr_path: str = "/"
    """ Current path we are in. """

    _loading_path: str = "/"
    """ Path we are loading. """

    # TODO We will map items by their 'Handle'
    _row_data_map: dict[str, MegaItem] = {}

    COLUMNS = ["Icon", "Name", "Modified", "Size"]

    FILE_ACTION_BINDINGS: list[BindingType] = [
        Binding(key="r", action="refresh", description="Refresh", show=True),
        Binding(key="R", action="rename_file", description="Rename a file", show=True),
        Binding(
            key="space", action="select_node", description="Select file", show=True
        ),
    ]

    NAVIGATION_BINDINGS: list[BindingType] = [
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l"),
        Binding("h,backspace", "navigate_out", "Parent Dir", key_display="h"),
    ]

    BINDINGS = NAVIGATION_BINDINGS + FILE_ACTION_BINDINGS

    @override
    def on_mount(self) -> None:
        self.border_title = "MEGA"
        self.border_subtitle = "Initializing..."
        self._loading_path = "/"
        self.show_header = True  # Or False, depending on your preference
        self.zebra_stripes = False
        self.show_cursor = True
        self.cursor_type = "row"  # Highlight the whole row
        # self.fixed_columns = len(self.COLUMNS)

        column_definitions = {
            "Icon": {"label": "", "width": 2},
            "Name": {"label": "Name", "width": 50},
            "Modified": {
                "label": "Modified",
                "width": 20,
            },
            "Size": {"label": "Size", "width": 10},
        }

        # Add columns during initialisation with specified widths
        for col_name in self.COLUMNS:
            config = column_definitions.get(col_name)

            if config:
                self.add_column(
                    label=str(config["label"]),
                    key=col_name.lower(),
                    width=int(config["width"]),  # Apply the width here
                )
            else:
                self.add_column(label=col_name, key=col_name.lower())

    async def action_navigate_in(self) -> None:
        """
        Navigate into a directory.
        """

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

    async def action_refresh(self) -> None:
        """
        Refreshes the current working directory.
        """
        self.post_message(StatusUpdate(f"Refreshing '{self.curr_path}'...", timeout=0))
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
            if not result:
                self.log.error("Invalid result!")
                return
            if not result[0] or not result[1]:
                self.log.error("Invalid result!")
                return

            new_name: str
            node: NodeInfoDict
            new_name, node = result
            assert new_name and node, f"Empty name {new_name} or empty node: {node}."
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

    ###################################################################
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
            self.app.log.error(f"FileList: MegaCmdError loading path '{path}': {e}")
            # Post error message from the worker (thread-safe)
            self.post_message(self.LoadError(path, e))
            return None  # Indicate failure by returning None
        except Exception as e:
            self.app.log.error(f"FileList: Unexpected error loading path '{path}': {e}")
            # Post error message from the worker (thread-safe)
            self.post_message(self.LoadError(path, e))
            return None  # Indicate failure

    def _update_list_on_success(self, path: str, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.app.log.debug(f"Updating UI for path: {path}")
        self.curr_path = path

        self.clear(columns=False)
        self._row_data_map.clear()  # Clear our internal mapping

        for index, item_data in enumerate(fetched_items):
            # Prepare data for each cell in the row
            name_str: Text = Text(item_data.name, overflow="ellipsis")
            mtime_str: Text = Text(item_data.mtime)
            icon_str: Text = Text.from_markup(
                ":file_folder:" if item_data.is_dir() else ":page_facing_up:",
            )
            fsize_str: Text
            if item_data.is_file():
                fsize_str = Text(
                    f"{item_data.size:.1f} {item_data.size_unit.unit_str()} "
                )

            else:
                fsize_str = Text("")

            fsize_str.align("left", 10)
            # Add row to DataTable. The values must match the order of COLUMNS.
            # FIXME Using index as row key
            row_key = str(index)

            # Pass data as individual arguments for each column
            self.add_row(
                icon_str,
                name_str,
                mtime_str,
                fsize_str,
                key=row_key,
            )
            # Store the MegaItem
            self._row_data_map[row_key] = item_data

        self.border_subtitle = f"{len(fetched_items)} items"

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
            self.app.log.debug(f"Worker for path '{self._loading_path}' was cancelled.")
            return

        # Failed
        if fetched_items is None:
            # Worker succeeded but returned None
            self.app.log.warning(
                f"Fetch worker for '{self._loading_path}' succeeded but returned 'None' result."
            )
            self.border_subtitle = "Load Error!"
            return

        # Success
        # Get number of files
        file_count: int = len(fetched_items)

        self.app.log.debug(
            f"Worker success for path '{self._loading_path}', items: {file_count}"
        )
        # Call the UI update method on the main thread
        self._update_list_on_success(self._loading_path, fetched_items)

        # We have successfully loaded the path
        # self.post_message(self.LoadSuccess(path))
        # Path *successfully* changed
        self.post_message(self.PathChanged(path))

        # If the count is 0 send a status update
        if file_count == 0:
            self.post_message(self.EmptyDirectory())

    def get_highlighted_megaitem(self) -> MegaItem | None:
        """
        Return the MegaItem corresponding to the currently highlighted row.
        """
        if self.cursor_row < 0 or not self.rows:  # No selection or empty table
            self.log.info("No highlighted item available to return.")
            return None
        try:
            # DataTable's coordinate system is (row, column)
            # self.cursor_coordinate.row gives the visual row index
            # We need the key of that row
            row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)

            if row_key.value is None:
                return None

            return self._row_data_map.get(row_key.value)

        except Exception as e:  # Catch potential errors if cursor is out of sync
            self.log.error(f"Error getting selected mega item: {e}")
            return None

    # Messages ################################################################
    class PathChanged(Message):
        """Message for when the path has changed."""

        def __init__(self, new_path: str) -> None:
            self.new_path: str = new_path
            super().__init__()

    class LoadSuccess(Message):
        """Message sent when items are loaded successfully."""

        def __init__(self, path: str) -> None:
            self.path: str = path
            super().__init__()

    class LoadError(Message):
        """Message sent when loading items fails."""

        def __init__(self, path: str, error: Exception) -> None:
            self.path: str = path
            self.error: Exception = error  # Include the error
            super().__init__()

    class EmptyDirectory(Message):
        """Message to signal the entered directory is empty."""

        def __init__(self) -> None:
            super().__init__()
