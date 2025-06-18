from pathlib import Path
from typing import ClassVar, override

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import var
from textual.widgets import Header, Label

from megatui.mega.megacmd import MegaItem, mega_get
from megatui.messages import StatusUpdate

from megatui.ui.filelist import FileList


class MegaAppTUI(App[None]):
    TITLE = "MegaTUI"
    SUB_TITLE = "MEGA Cloud Storage Manager"
    CSS_PATH = "ui/style.tcss"
    ENABLE_COMMAND_PALETTE = True

    # SCREENS = {"filetree": FileTreeScreen}

    # Causes the app to crash
    # ansi_color = True

    # Will add css class to our app depending on size of terminal
    # Up to 80 cells wide, the app has the class "-normal"
    # 80 - 119 cells wide, the app has the class "-wide"
    # 120 cells or wider, the app has the class "-very-wide"
    # HORIZONTAL_BREAKPOINTS = [(0, "-normal"), (80, "-wide"), (120, "-very-wide")]

    BINDINGS : ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("f2", "toggle_darkmode", "toggle darkmode", key_display="f2"),
    ]

    status_message: var[str] = var("Logged in.")
    current_mega_path: var[str] = var("/")

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """
        Compose the basic UI for the application.
        """
        # Disable mouse events
        self.capture_mouse(None)
        self.theme = "gruvbox"

        fileview = FileList()

        with Vertical(id="main"):
            yield Header()
            with Horizontal(id="status-bar"):
                yield Label(f"Path: {self.current_mega_path}", id="label-path")
                yield Label(self.status_message, id="label-status-msg")

            yield fileview
            # Placeholder for preview
            # yield Static("Preview", id="preview-pane")

            # Selected files count
            yield Label("", id="label-selected-count")

        # Why does the footer create so many event messages?
        # yield Footer(disabled=True)

    async def on_mount(self) -> None:
        """
        Called when the app is mounted.
        Performs initial load and some initialisation.
        """
        self.log.info("MegaAppTUI mounted. Starting initial load.")
        # Get the FileList widget and load the root directory

        file_list = self.query_one(FileList)
        # Start loading the root directory
        await file_list.load_directory(self.current_mega_path)

    """
    Actions #############################################################
    """

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
        selected_item_data: MegaItem | None = file_list.get_highlighted_megaitem()

        if selected_item_data is None:
            self.log.debug("Download failed as no file is currently highlighted.")
            return

        download_items = [selected_item_data]

        self.app.log.info(
            f"action_download: Downloading file '{selected_item_data.name}'"
        )
        self.status_message = f"Downloading '{selected_item_data.name}'"
        await self.download_files(download_items)

    def action_toggle_darkmode(self) -> None:
        """Toggles darkmode."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    """
    # Watchers ################################################################
    """

    # Watch reactive variables and update UI elements accordingly
    def watch_status_message(self, new_message: str) -> None:
        pass

    def clear_status_message(self) -> None:
        """
        Helper to clear the status message.
        """
        self.status_message = ""
        status_label: Label = self.query_one("#label-status-msg", Label)
        status_label.update()

    """
    # Message Handlers ###########################################################
    """

    @on(StatusUpdate)
    def update_status_message(self, message: StatusUpdate):
        """
        Refresh UI when status bar is updated.
        """
        self.status_message = message.message

        # Use query to find the label and update it
        try:
            status_label: Label = self.query_one("#label-status-msg", Label)
            new_txt: Text = Text.from_markup(self.status_message)
            new_txt.stylize(Style(italic=True))

            status_label.update(new_txt)
            status_label.set_timer(
                delay=message.timeout if message.timeout > 0 else 10,
                callback=self.clear_status_message,
            )

        except Exception:
            # Do nothing
            pass

    @on(FileList.ToggledSelection)
    def on_file_list_toggled_selection(
        self, message: FileList.ToggledSelection
    ) -> None:
        """Update counter when selecting/unselecting an item."""
        path_label = self.query_one("#label-selected-count", Label)
        if message.count == 0:
            path_label.update(Content.empty())
            self.log.info("Selection counter is now cleared.")
            return

        path_label.update(
            Content.from_markup(
                "[red bold] $count [/red bold] files selected.", count=message.count
            )
        )
        self.log.info("Selection counter updated.")

    @on(FileList.PathChanged)
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update status bar when path changes."""
        path_label = self.query_one("#label-path", Label)
        path_label.update(Content(f"{message.new_path}"))
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
        self.status_message = "Empty directory!"
