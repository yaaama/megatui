from pathlib import PurePath
from typing import override

from textual.app import ComposeResult
from textual.reactive import var
from textual.widgets import Label, ListItem, ListView, Placeholder, Static
from textual.message import Message
# from textual.containers import Widget .

import megatui.mega.megacmd as m


class CloudInfoBar(Placeholder):
    pass


# class FileItem(Static):
#
#     @override
#     def compose(self) -> ComposeResult:
#         with

class FilesListItem(ListItem):
    """
    A ListItem specialized to display a MegaItem.
    """

    def __init__(self, item: m.MegaItem) -> None:
        super().__init__()
        self.item: m.MegaItem = item

        # Use different display for dirs vs files
        prefix = "[d] " if item.ftype == m.FILE_TYPE.DIRECTORY else "[f] "
        size_segment: str
        if item.size:
            size_in_mb = round(item.size / 1024 / 1024, ndigits=2)
            size_segment = f"{size_in_mb}"
        else:
            size_segment = ""

        # TODO Make it prettier
        self.display_label: Label = Label(
            f"{prefix}{item.name}  {item.mtime}  {size_segment}", markup=False
        )

    @override
    def compose(self) -> ComposeResult:
        yield self.display_label


class FilesListView(ListView):
    """A ListView for displaying MegaItems."""

    items: var[m.MegaItems] = var([])
    current_path: var[str] = var("/")

    # --- Messages ---
    class PathChanged(Message):
        """Message sent when the path changes (after successful load)."""

        def __init__(self, new_path: str) -> None:
            super().__init__()
            self.new_path: str = new_path

    class LoadSuccess(Message):
        """Message sent when items are loaded successfully."""

        pass

    class LoadError(Message):
        """Message sent when loading items fails."""

        def __init__(self, error: Exception) -> None:
            super().__init__()
            self.error: Exception = error

    # --- Watcher ---
    def watch_items(
        self, old_items: m.MegaItems, new_items: m.MegaItems
    ) -> None:
        """Update the list view when items change."""
        _ = self.clear()
        for item in new_items:
            _ = self.append(FilesListItem(item))

    # --- Lifecycle ---
    def on_mount(self) -> None:
        """Initially load the root directory."""
        self.load_directory(self.current_path)

    # --- Load Logic ---
    def load_directory(self, path: str) -> None:
        """
        Load directory contents asynchronously. Stores highlight target name.

        Args:
            path: The directory path to load.
            highlight_item_name: Name of the item to highlight after successful load.
        """
        self.app.log.error(
            f"--- load_directory called for path: {path}. Triggering worker... ---"
        )
        _ = self.app.run_worker(self._fetch_items(path), exclusive=True)

    async def _fetch_items(self, path: str) -> None:
        self.app.log.error(
            f"--- _fetch_items STARTING for path: {path} ---"
        )  # Log start
        self.disabled = True
        try:
            self.app.log.error(f"Calling mega_ls for path: {path}")  # Log before call
            fetched_items = await m.mega_ls(path)
            self.app.log.error(
                f"mega_ls completed for path: {path}. Found {len(fetched_items)} items."
            )  # Log after call

            # ... sorting logic could go here if needed ...

            self.items = fetched_items
            self.app.log.error(
                f"Assigned items for path: {path}. Posting LoadSuccess..."
            )  # Log before post

            # *** The messages that trigger handlers ***
            self.post_message(self.LoadSuccess())
            self.post_message(self.PathChanged(path))

            self.app.log.error(f"Posted messages for path: {path}.")  # Log after post

        except m.MegaCmdError as e:
            # Log the specific MegaCmdError
            self.app.log.error(
                f"MegaCmdError loading path '{path}': {e} (RC: {e.return_code}, Stderr: {e.stderr})"
            )
            self.items = []  # Clear items on error
            self.post_message(self.LoadError(e))  # Post error message

        except Exception as e:
            # Log any other unexpected errors during fetch/processing
            self.app.log.error(
                f"Unexpected error loading path '{path}': {e}"
            )  # Use log.exception to include traceback
            self.items = []  # Clear items on error
            self.post_message(self.LoadError(e))  # Post error message

        finally:
            self.disabled = False
            self.app.log.error(f"--- _fetch_items FINALLY block for path: {path} ---")

    def on_load_error(self, message: LoadError) -> None:
        """Handles load error (e.g., show status message)."""
        # We should display the error
        self.app.log(f"File list load failed: {message.error}")

    # --- Action Methods (Navigate) ---
    def action_navigate_in(self) -> None:
        """Navigate into the selected directory."""

        # Check valid dir
        if self.index is None or len(self.children) <= self.index:
            return

        # Check for whether we are selecting a FilesListItem
        selected_list_item = self.children[self.index]
        if not isinstance(selected_list_item, FilesListItem):
            return

        item = selected_list_item.item
        if item.ftype != m.FILE_TYPE.DIRECTORY:
            return

        # Change paths
        new_path = str(PurePath(self.current_path) / item.name)
        # No specific highlight needed when going IN
        self.load_directory(new_path)

    def action_navigate_out(self) -> None:
        """Navigate to the parent directory."""
        if self.current_path == "/":
            return

        parent_path = str(PurePath(self.current_path).parent)

        # Load parent, pass the name of the directory we just came from
        self.load_directory(parent_path)
