from pathlib import Path, PurePath
from typing import override

from textual import log, on, work, messages
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import var
from textual.widgets import Footer, Header, Label
from megatui.ui.file_action import RenamePopup
from megatui.ui.file_tree import FileTreeScreen

# from megatui.ui.fileitem import FileItem
from megatui.ui.fileview import FileList

from megatui.mega.megacmd import (
    MegaItem,
    MegaItems,
    mega_get,
)


class MegaAppTUI(App[str]):
    TITLE = "MegaTUI"
    SUB_TITLE = "MEGA Cloud Storage Manager"
    CSS_PATH = "ui/style.tcss"
    ENABLE_COMMAND_PALETTE = True
    SCREENS = {"filetree": FileTreeScreen}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh List", key_display="r"),
        Binding("R", "rename_file", "rename", key_display="R"),
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l,enter", "navigate_in", "Enter Dir", key_display="l"),
        Binding("h,backspace", "navigate_out", "Parent Dir", key_display="h"),
        Binding("f2", "toggle_darkmode", "toggle darkmode", key_display="f2"),
        Binding("f3", "download", "download", key_display="f3"),
        Binding("f", "push_screen('filetree')", "filetree"),
        # Add other bindings
    ]

    status_message: var[str] = var("Logged in.")
    current_mega_path: var[str] = var("/")

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """
        Compose the basic UI for the application.
        """

        with Vertical():
            yield Header()
            with Horizontal(id="status-bar"):
                yield Label(f"Path: {self.current_mega_path}", id="status-path")
                yield Label(self.status_message, id="status-message")

            yield FileList(id="file-list")
                # Placeholder for preview
                # yield Static("Preview", id="preview-pane")

        # Why does the footer create so many event messages?
        # yield Footer(disabled=True)

    async def on_mount(self) -> None:
        """
        Called when the app is mounted.
        Performs initial load.
        """
        self.log.info("MegaAppTUI mounted. Starting initial load.")
        # Get the FileList widget and load the root directory

        file_list = self.query_one(FileList)
        # Start loading the root directory
        await file_list.load_directory(self.current_mega_path)

    """
    Actions #############################################################
    """

    async def action_refresh(self) -> None:
        """
        Refreshes the current working directory.
        """
        file_list = self.query_one(FileList)
        self.status_message = f"Refreshing '{file_list.curr_path}'..."
        await file_list.load_directory(file_list.curr_path)

    def action_rename_file(self) -> None:
        """
        Rename a file.
        Popup will be shown to prompt the user for the new name.

        TODO: Make this actually rename the file.
        TODO: Add keybindings for the new screen.
        """
        self.log.info("Renaming file")

        file_list = self.query_one(FileList)
        selected_item = file_list.get_selected_mega_item()

        if not selected_item:
            self.log.error("No highlighted file to rename.")
            return

        self.push_screen(RenamePopup(selected_item.name))

    async def download_files(self, files: list[MegaItem]) -> None:
        """
        Helper method to download files.

        TODO: Check for existing files on system and handle them
        """
        if not files:
            self.log.warning("Did not receive any files to download!")
            return

        for file in files:
            home = Path.home()
            await mega_get(
                target_path=str(home),
                remote_path=str(file.full_path),
                is_dir=file.is_dir(),
            )

    async def action_download(self) -> None:
        """
        Download the currently highlighted file or a selection of files.

        TODO: Can download multiple files using selection
        TODO: Ask for download path
        TODO: Display download status
        """
        file_list = self.query_one(FileList)
        selected_item_data: MegaItem | None = (
            file_list.get_selected_mega_item()
        )  # NEW way to get item

        if selected_item_data is None:
            self.log.debug("Download failed as no file is currently highlighted.")
            return

        download_items = [selected_item_data]

        self.app.log.info(
            f"action_download: Downloading file '{selected_item_data.name}'"
        )
        self.status_message = f"Downloading '{selected_item_data.name}'"
        await self.download_files(download_items)

    async def action_navigate_in(self) -> None:
        file_list = self.query_one(FileList)
        selected_item_data = file_list.get_selected_mega_item()

        # Fail: Selected item is None.
        if selected_item_data is None:
            self.log.debug("Cannot enter directory, selected item is 'None'.")
            self.status_message = "Cannot navigate into this!"
            return

        # Fail: Is a regular file
        if selected_item_data.is_file():  # Check if it's a directory
            self.log.debug("Cannot enter into a file.")
            self.status_message = f"Node must be a directory to enter into it."
            return

        to_enter = selected_item_data.full_path
        path_str: str = str(to_enter)

        await file_list.load_directory(path_str)
        self.current_mega_path = path_str

    async def action_navigate_out(self) -> None:
        """
        Navigate to parent directory.
        """

        file_list = self.query_one(FileList)
        self.log.info(f"Navigating out of directory {self.current_mega_path}")
        curr_path : str = file_list.curr_path


        # Avoid going above root "/"
        if curr_path == "/":
            self.status_message = "Already at root! Cannot navigate out."
            return

        parent_path : PurePath = PurePath(curr_path).parent

        self.status_message = f"Entering '{parent_path}'..."
        await file_list.load_directory(str(parent_path))
        self.current_mega_path = str(parent_path)

    def action_toggle_darkmode(self) -> None:
        """Toggles darkmode."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    def action_cursor_up(self) -> None:
        """Move the cursor up in the file list."""
        self.query_one(FileList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the cursor down in the file list."""
        self.query_one(FileList).action_cursor_down()

    """
    # Watchers ################################################################
    """

    # Watch reactive variables and update UI elements accordingly
    def watch_status_message(self, new_message: str) -> None:
        """
        Refresh UI when status bar is updated.
        """
        # Use query to find the label and update it
        try:
            status_label = self.query_one("#status-message", Label)
            status_label.update(new_message)
            status_label.set_timer(delay=6, callback=self.clear_status_message)
        except Exception:
            # Do nothing
            pass

    def clear_status_message(self) -> None:
        """
        Helper to clear the status message.
        """
        self.status_message = ""

    """
    # Message Handlers ###########################################################
    """

    @on(FileList.PathChanged)
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update status bar when path changes."""
        path_label = self.query_one("#status-path", Label)
        path_label.update(f"Path: {message.new_path}")
        self.status_message = f"Loaded '{message.new_path}'"
        self.current_mega_path = message.new_path

    @on(FileList.LoadError)
    def on_file_list_load_error(self, message: FileList.LoadError) -> None:
        """Handle errors during directory load."""
        self.status_message = f"Error loading: {message.error}"
        # Log the detailed error
        self.log.error(f"Error loading directory: {message.error}")
        # Maybe show a dialog or keep the status message updated

    @on(FileList.EmptyDirectory)
    def on_file_list_empty_directory(self) -> None:
        self.status_message = "Empty directory."
