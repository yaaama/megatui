# UI Components Related to Files
#
from os import abort
from typing import Literal, override

import megatui.mega.megacmd as m
from megatui.mega.megacmd import MegaCmdError, MegaItem, MegaItems
from megatui.ui.fileitem import FileItem
from rich.console import Console
from rich.text import Text
from textual import reactive, work  # Import work decorator
from textual.app import ComposeResult, RenderResult
from textual.message import Message
from textual.widgets import ListItem, ListView, Static
from textual.worker import Worker, WorkerState  # Import worker types


###########################################################################
# FileList
###########################################################################
class FileList(ListView):
    """A ListView widget to display multiple FileItems."""

    items: MegaItems = []
    curr_path: str = "/"
    new_path: str = "/"
    _loading_path: str = "/"

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

    ###################################################################
    @work(
        exclusive=True, group="megacmd", description="mega-ls : Fetching dir listings"
    )
    async def fetch_files(self, path: str) -> MegaItems | None:
        """
        Asynchronously fetches items from MEGA for the given path.
        Returns the list of items on success, or None on failure.
        Errors are handled by posting LoadError message.
        """
        self.app.log.info(f"FileList: Worker starting fetch for path: {path}")
        try:
            # Fetch and sort items
            fetched_items = await m.mega_ls(path)
            if fetched_items:  # Check if mega_ls itself returned None/empty on error
                # fetched_items.sort(
                #     key=lambda item: (item.ftype.value, item.name.lower())
                # )
                return fetched_items  # Return the result
            else:
                return None

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

    # --- Worker Completion Handler ---
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Called when the fetch_files worker state changes."""

        # Check if this event is for the worker we care about
        if event.worker.name != "fetch_files":
            return


        if event.state == WorkerState.CANCELLED :
            return

        self.app.log.debug(
            f"Worker {event.worker.name} state changed: {event.state} for path '{self._loading_path}'"
        )

        if (event.state == WorkerState.PENDING) or (event.state == WorkerState.RUNNING):
            self.border_subtitle : str = f"Loading '{self._loading_path}'"
            return




        # Get the path that this worker was started for
        completed_path = self._loading_path  # The path this worker was processing

        if completed_path == "":
            # Should not happen ideally
            self.app.log.warning("Worker finished but no _loading_path was set.")

        if event.state == WorkerState.ERROR:
            self.app.log.error(f"Worker for path '{completed_path}' failed!")
            self.border_subtitle = "Load Error!"
            return

        fetched_items: MegaItems | None = event.worker.result
        if fetched_items is not None:
            self.app.log.info(
                f"Worker success for path '{completed_path}', items: {len(fetched_items)}"
            )
            # Call the UI update method on the main thread
            self._update_list_on_success(completed_path, fetched_items)
        else:
            # Worker succeeded but returned None
            self.app.log.warning(
                f"Fetch worker for '{completed_path}' succeeded but returned 'None' result."
            )
            self.border_subtitle = "Load Error!"
            # LoadError message should have been posted by the worker

    def _update_list_on_success(self, path: str, fetched_items: MegaItems) -> None:
        """Updates state and UI after successful load. Runs on main thread."""
        self.app.log.debug(f"Updating list UI for path: {path}")
        self.items: MegaItems = fetched_items
        self.curr_path: str = path
        self.border_title: str = f"MEGA: {path}"
        self.border_subtitle = f"{len(fetched_items)} items"

        self.clear()
        for item_data in fetched_items:
            self.append(ListItem(FileItem(item=item_data)))

        # Post messages (already on main thread here)
        self.post_message(self.LoadSuccess(path))
        self.post_message(self.PathChanged(path))  # Path *successfully* changed

    def load_directory(self, path: str) -> None:
        """Initiates asynchronous loading using the worker."""
        self.app.log.info(
            f"FileList.load_directory: Received request for path='{path}'"
        )

        self.app.log.info(f"Requesting load for directory: {path}")
        self.border_title = f"MEGA: {path}"
        self.border_subtitle = f"Loading '{path}'..."
        self._loading_path = path  # Track the path we are loading
        self.clear()
        # Start the worker. Results handled by on_worker_state_changed.
        self.fetch_files(path)

    @override
    def compose(self) -> ComposeResult:
        for it in self.items:
            yield FileItem(item=it)

    # --- Initialization ---
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = "MEGA"
        self.border_subtitle = "Initializing..."
        self._loading_path = "/"
