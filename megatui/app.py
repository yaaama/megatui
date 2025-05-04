from pathlib import Path, PurePath
import os
from typing import override, Literal

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, ListView, Label, Log
from textual.reactive import Reactive, var
from textual import work  # Import work decorator for workers
from textual.message import Message  # Import Message base class


# import mega.megacmd as megacmd
from megatui.mega.megacmd import (  # Changed import path
    MegaItem,
    MegaCmdError,
    check_mega_login,  # Import login check function
)
from megatui.ui.fileview import FileList, FileItem


class MegaAppTUI(App[None]):

    CSS_PATH = "ui/style.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh List", key_display="r"),
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l", "navigate_in", "Enter Dir", key_display="l / Enter"),
        Binding("h", "navigate_out", "Parent Dir", key_display="h / Backspace"),
        Binding("enter", "navigate_in", "Enter Dir", show=False),  # Map Enter
        Binding("backspace", "navigate_out", "Parent Dir", show=False),  # Map Backspace
        Binding("f2", "toggle_darkmode", "toggle darkmode", key_display="f2"),
        # Add other bindings
    ]

    TITLE = "MegaTUI"
    SUB_TITLE = "MEGA Cloud Storage Manager"
    ENABLE_COMMAND_PALETTE = True
    status_message: Reactive[str] = var("Logged in.")
    show_log_pane: Reactive[bool] = var(False)
    current_mega_path: Reactive[str] = var("/")

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""

        self.log.info("MegaAppTUI mounted. Starting initial load.")
        yield Header()
        with Horizontal(id="main-container"):
            yield FileList(id="file-list")
            # yield Static("Preview", id="preview-pane") # Placeholder for preview

        with Horizontal(id="status-bar"):
            yield Label(self.status_message, id="status-message")
            yield Label(
                f"Path: {self.current_mega_path}", id="status-path"
            )  # Bind to reactive var
        yield Footer()

    # --- App Logic ---
    def on_mount(self) -> None:
        """Called when the app is mounted. Perform initial load."""
        self.log.info("MegaAppTUI mounted. Starting initial load.")
        # Get the FileList widget and load the root directory
        file_list = self.query_one(FileList)
        # Start loading the root directory
        file_list.load_directory(self.current_mega_path)

    # --- Action Handlers ---
    def action_refresh(self) -> None:
        """Reloads the current directory."""
        file_list = self.query_one(FileList)
        self.status_message = f"Refreshing '{file_list.curr_path}'..."
        _ = file_list.load_directory(file_list.curr_path)

    def action_navigate_in(self) -> None:
        """Navigates into the selected directory."""
        file_list = self.query_one(FileList)
        if file_list.highlighted_child is None:
            return  # Nothing selected

        # Get the custom FileItem widget from the highlighted ListItem
        list_item = file_list.highlighted_child
        # Assume the first child of ListItem is our FileItem widget
        file_item_widget = list_item.query_one(FileItem)
        selected_item_data = file_item_widget.item  # Get the MegaItem data

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
        _ = file_list.load_directory(new_path)  # Pass the correct path

    def action_navigate_out(self) -> None:
        """Navigates to the parent directory."""
        file_list = self.query_one(FileList)
        current_path = Path(file_list.curr_path)

        # Avoid going above root "/"
        if str(current_path) == "/":
            self.status_message = "Already at root."
            return

        parent_path = str(current_path.parent)
        # Ensure root path is represented as "/" not "."
        if parent_path == ".":
            parent_path = "/"

        self.status_message = f"Entering '{parent_path}'..."
        _ = file_list.load_directory(parent_path)

    def action_toggle_darkmode(self) -> None:
        """Toggles the visibility of the log pane."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    # --- Watchers ---
    # Watch reactive variables and update UI elements accordingly
    def watch_status_message(self, new_message: str) -> None:
        """Update the status bar message label."""
        # Use query to find the label and update it
        try:
            status_label = self.query_one("#status-message", Label)
            status_label.update(new_message)
        except Exception:
            # Do nothing
            pass

    # --- Message Handlers ---
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update status bar when path changes."""
        path_label = self.query_one("#status-path", Label)
        path_label.update(f"Path: {message.new_path}")
        self.status_message = f"Loaded '{message.new_path}'"
        self.status_message = f"Loaded '{self.query_one(FileList).curr_path}'"

    def on_file_list_load_error(self, message: FileList.LoadError) -> None:
        """Handle errors during directory load."""
        self.status_message = f"Error loading: {message.error}"
        # Log the detailed error
        self.log.error(f"Error loading directory: {message.error}")
        # Maybe show a dialog or keep the status message updated

    def action_cursor_up(self) -> None:
        """Move the cursor up in the file list."""
        self.query_one(FileList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the cursor down in the file list."""
        self.query_one(FileList).action_cursor_down()
