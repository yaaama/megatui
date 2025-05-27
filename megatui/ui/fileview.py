# UI Components Related to Files
from typing import override

import megatui.mega.megacmd as m
from megatui.mega.megacmd import MegaCmdError, MegaItems, MegaItem, MegaSizeUnits

from textual import (
    work,
)
import asyncio
from typing import Generic, Any
from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable
from textual.worker import Worker  # Import worker types


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


    @override
    def on_mount(self) -> None:
        self.border_title = "MEGA"
        self.border_subtitle = "Initializing..."
        self._loading_path = "/"
        self.show_header = True  # Or False, depending on your preference
        self.show_cursor = True
        self.cursor_type = "row"  # Highlight the whole row


        # Add columns during initialisation
        for col_name in self.COLUMNS:
            if col_name == "Icon":
                self.add_column(label="", key=col_name.lower())
                continue

            self.add_column(label=col_name, key=col_name.lower())


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
            name_str : Text = Text(item_data.name)
            mtime_str : Text = Text(item_data.mtime)
            icon_str : Text = Text("📁" if item_data.is_dir() else "📄")
            fsize_str: Text
            if item_data.is_file():
                fsize_str = Text(
                    f"{item_data.size:.2f} {item_data.size_unit.unit_str()}"
                )
            else:
                fsize_str = Text("")

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
        self.post_message(self.LoadSuccess(path))
        self.post_message(self.PathChanged(path))  # Path *successfully* changed

    async def load_directory(self, path: str) -> None:
        """Initiates asynchronous loading using the worker."""
        self.app.log.info(
            f"FileList.load_directory: Received request for path='{path}'"
        )

        self.log.info(f"Requesting load for directory: {path}")
        self.border_title = f"MEGA: {path}"
        self.border_subtitle = f"Loading '{path}'..."
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
        if file_count == 0:
            self.post_message(self.EmptyDirectory())

    def get_selected_mega_item(self) -> MegaItem | None:
        """
        Return the MegaItem corresponding to the currently highlighted row.
        """
        if self.cursor_row < 0 or not self.rows:  # No selection or empty table
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
