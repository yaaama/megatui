import asyncio
from pathlib import Path, PurePath
from typing import override

# import mega.megacmd as megacmd
from megatui.mega.megacmd import (  # Import login check function; Changed import path
    MegaItem,
    mega_get,
)
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import var
from textual.widgets import Footer, Header, Label
from megatui.ui.file_action import RenamePopup
from megatui.ui.file_tree import FileTreeScreen
from megatui.ui.fileitem import FileItem
from megatui.ui.fileview import FileList


class MegaAppTUI(App[str]):
    TITLE = "MegaTUI"
    SUB_TITLE = "MEGA Cloud Storage Manager"
    ENABLE_COMMAND_PALETTE = True
    SCREENS = {"filetree": FileTreeScreen}
    status_message: var[str] = var("Logged in.")
    current_mega_path: var[str] = var("/")

    CSS_PATH = "ui/style.tcss"

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

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""

        with Vertical():
            yield Header()
            with Horizontal(id="status-bar"):
                yield Label(f"Path: {self.current_mega_path}", id="status-path")
                yield Label(self.status_message, id="status-message")

            with Horizontal(id="main-container"):
                yield FileList(id="file-list")
                # yield Static("Preview", id="preview-pane") # Placeholder for preview

        # Why does the footer create so many event messages?
        yield Footer(disabled=True)

    async def on_mount(self) -> None:
        """Called when the app is mounted. Perform initial load."""
        self.log.info("MegaAppTUI mounted. Starting initial load.")
        # Get the FileList widget and load the root directory
        file_list = self.query_one(FileList)
        # Start loading the root directory
        await file_list.load_directory(self.current_mega_path)

    # --- Action Handlers ---
    async def action_refresh(self) -> None:
        """Reloads the current directory."""
        file_list = self.query_one(FileList)
        self.status_message = f"Refreshing '{file_list.curr_path}'..."
        await file_list.load_directory(file_list.curr_path)

    def action_rename_file(self) -> None:
        self.log.info("Renaming file")

        file_list = self.query_one(FileList)
        file = file_list.query_one(FileItem)

        if not file:
            self.log.error("No highlighted file to rename.")
            return

        self.push_screen(RenamePopup(file.mega_item.name))

    """
    Downloading files
    TODO: Can download multiple files using selection
    TODO: Check for existing files on system and handle them
    TODO: Display download status
    TODO: Ask for download path
    """

    async def download_files(self, files: list[MegaItem]) -> None:
        """Downloads files."""
        if not files:
            self.log.warning("Did not receive any files to download: '{files}'")
            return

        for file in files:
            home = Path.home()
            await mega_get(
                target_path=str(home),
                remote_path=str(file.get_full_path()),
                is_dir=file.is_dir(),
            )

    async def action_download(self) -> None:

        file_list = self.query_one(FileList)

        if file_list.highlighted_child is None:
            # Nothing selected
            return

        selected_item_data: MegaItem = file_list.highlighted_child.query_one(
            FileItem
        ).mega_item

        download_items = [selected_item_data]

        self.app.log.info(
            f"action_download: Downloading file '{selected_item_data.name}'"
        )
        self.status_message = f"Downloading '{selected_item_data.name}'"
        await self.download_files(download_items)

    async def action_navigate_in(self) -> None:
        """Navigates into the selected directory."""
        file_list = self.query_one(FileList)

        if file_list.highlighted_child is None:
            # Nothing selected
            return

        # Get the custom FileItem widget from the highlighted ListItem
        list_item = file_list.highlighted_child
        # Assume the first child of ListItem is our FileItem widget
        file_item_widget = list_item.query_one(FileItem)
        selected_item_data = file_item_widget.mega_item  # Get the MegaItem data

        current_path: str = file_list.curr_path
        dir_name: str = selected_item_data.name

        # Log values for debugging
        self.app.log.info(
            f"action_navigate_in: Current Path='{current_path}', Selected Dir='{dir_name}'"
        )

        if current_path == "/":
            new_path = f"/{dir_name}"
        else:
            # Ensure current_path doesn't end with '/' before joining
            clean_current_path = current_path.rstrip("/")
            new_path = f"{clean_current_path}/{dir_name}"

        # Log the constructed path
        self.app.log.info(f"action_navigate_in: Constructed new_path='{new_path}'")

        self.status_message = f"Entering '{new_path}'..."
        await file_list.load_directory(new_path)  # Pass the correct path
        self.current_mega_path = new_path

    async def action_navigate_out(self) -> None:
        """Navigates to the parent directory."""

        file_list = self.query_one(FileList)
        self.log.info(f"Navigating out of directory {self.current_mega_path}")
        current_path = PurePath(self.current_mega_path)

        # Avoid going above root "/"
        if str(current_path) == "/":
            self.status_message = "Already at root."
            return

        parent_path = str(current_path.parent)
        # Ensure root path is represented as "/" not "."
        if parent_path == ".":
            parent_path = "/"

        self.status_message = f"Entering '{parent_path}'..."
        await file_list.load_directory(parent_path)
        self.current_mega_path = parent_path

    def action_toggle_darkmode(self) -> None:
        """Toggles darkmode."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    def clear_status_message(self) -> None:
        self.status_message = ""

    # --- Watchers ---
    # Watch reactive variables and update UI elements accordingly
    def watch_status_message(self, new_message: str) -> None:
        """Update the status bar message label."""

        # Use query to find the label and update it
        try:
            status_label = self.query_one("#status-message", Label)
            status_label.update(new_message)
            status_label.set_timer(delay=6, callback=self.clear_status_message)
        except Exception:
            # Do nothing
            pass

    # --- Message Handlers ---
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update status bar when path changes."""
        path_label = self.query_one("#status-path", Label)
        path_label.update(f"Path: {message.new_path}")
        self.status_message = f"Loaded '{message.new_path}'"
        self.query_one(FileList).action_cursor_down()
        self.current_mega_path = message.new_path

    def on_file_list_load_error(self, message: FileList.LoadError) -> None:
        """Handle errors during directory load."""
        self.status_message = f"Error loading: {message.error}"
        # Log the detailed error
        self.log.error(f"Error loading directory: {message.error}")
        # Maybe show a dialog or keep the status message updated

    def on_file_list_empty_directory(self, message: FileList.EmptyDirectory) -> None:
        self.status_message = "Empty directory."


    def action_cursor_up(self) -> None:
        """Move the cursor up in the file list."""
        self.query_one(FileList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the cursor down in the file list."""
        self.query_one(FileList).action_cursor_down()
