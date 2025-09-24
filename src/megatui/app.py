import asyncio
import logging
import sys
from typing import ClassVar, override

import rich
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.logging import TextualHandler
from textual.widgets import Footer, Header, Label

from megatui.mega import megacmd as m
from megatui.messages import StatusUpdate
from megatui.ui.filelist import FileList
from megatui.ui.screens.help import HelpScreen
from megatui.ui.top_status_bar import TopStatusBar

logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
)


class MegaTUI(App[None], inherit_bindings=False):
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

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            key="ctrl+c", action="quit", description="quit", show=False, priority=True
        ),
        Binding(key="q", action="quit", description="quit", show=False),
        Binding(
            "f2",
            action="toggle_darkmode",
            description="darkmode",
            key_display="f2",
            show=False,
        ),
        Binding(
            key="ctrl+h",
            key_display="c-h",
            action="show_help_screen",
            description="help",
            system=True,
            priority=True,
        ),
        Binding(
            key="?",
            key_display="?",
            action="show_help_screen",
            description="help",
            system=True,
        ),
    ]

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """Compose the basic UI for the application."""
        # Disable mouse events
        self.capture_mouse(None)
        self.theme = "gruvbox"

        # Our file list
        file_list = FileList()
        # Top status bar
        top_status_bar = TopStatusBar()

        footer = Footer(show_command_palette=True)
        footer.compact = True

        with Vertical(id="main"):
            yield Header()
            yield top_status_bar
            yield file_list
            # Placeholder for preview
            # yield Static("Preview", id="preview-pane")

            # Selected files count
            yield Label("", id="label-selected-count")

            # Why does the footer create so many event messages?
            # yield footer

    async def on_mount(self) -> None:
        """Called when the app is mounted.
        Performs initial load and some initialisation.
        """
        self.log.info("MegaAppTUI mounted. Starting initial load.")
        # Get the FileList widget and load the root directory
        file_list = self.query_one(FileList)
        await file_list.load_directory(file_list._curr_path)  # pyright: ignore[reportPrivateUsage]

    # """
    # Actions #############################################################
    # """

    def action_toggle_darkmode(self) -> None:
        """Toggles darkmode."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    def action_show_help_screen(self) -> None:
        self.push_screen(HelpScreen(self.active_bindings))

    def action_view_info(self) -> None:
        # Call mega_df/ any other important functions to get general information
        # Functions to call:
        #   mega_df
        #   version [-l][-c]: Prints MEGAcmd versioning and extra info
        #   whoami [-l]: Prints info of the user
        #   pwd: Prints the current remote folder
        #   session
        #   masterkey pathtosave: Shows your master key.
        #   pwd: Prints the current remote folder
        #   mount Lists all the root nodes
        #   speedlimit [-u|-d|--upload-connections|--download-connections] [-h]
        # [NEWLIMIT]: Displays/modifies upload/download rate limits: either
        # speed or max connections

        # Place into rich log
        # Push 'info' screen

        pass

    #
    # # Message Handlers ###########################################################
    #

    @on(FileList.ToggledSelection)
    def on_file_list_toggled_selection(
        self, message: FileList.ToggledSelection
    ) -> None:
        """Update counter when selecting/unselecting an item."""
        selection_label = self.query_one("#label-selected-count", Label)
        if message.count == 0:
            selection_label.update(Content.empty())
            self.log.debug("Selection counter cleared.")
            return

        selection_label.update(Content.from_text(f"{message.count} files selected"))
        self.log.debug(f"Selected {message.count}")
        selection_label.refresh()

    @on(FileList.PathChanged)
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update TopStatusBar when path changes."""
        status_bar: TopStatusBar = self.query_one(TopStatusBar)
        status_bar.path = message.path
        status_bar.clear_status_msg()

    @on(FileList.EmptyDirectory)
    def on_file_list_empty_directory(self, message: FileList.EmptyDirectory):
        """Update TopStatusBar to signal to user the directory is empty."""
        _ = message  # To stop getting unused arg warning
        self.top_status_bar.signal_empty_dir()

    @on(FileList.LoadError)
    def on_file_list_load_error(self, message: FileList.LoadError):
        """Update TopStatusBar to signal that loading PATH had an error."""
        self.top_status_bar.signal_error(f"Failed to load path: {message.path}")
        # Log the detailed error
        self.log.error(f"Error loading directory: {message.error}")

    @on(StatusUpdate)
    def update_status_message(self, message: StatusUpdate):
        """Refresh UI when status bar is updated."""
        status_bar = self.top_status_bar
        status_bar.status_msg = message.message

        def clear_status_msg():
            """Clear TopStatusBar of all its contents"""
            self.log.info("Clearing status message in top bar.")
            status_bar.clear_status_msg()

        # Set timer for status bar to clear its contents
        status_bar.set_timer(
            delay=message.timeout if message.timeout > 0 else 10,
            callback=clear_status_msg,
        )

    # Widget access.
    @property
    def file_list(self):
        """Return FileList widget"""
        return self.query_one(FileList)

    @property
    def top_status_bar(self):
        """Return TopStatusBar of UI"""
        return self.query_one(TopStatusBar)


# Run the application #####################################################################
async def run_app() -> None:
    """Checks login and runs the Textual app."""

    # Start the TUI
    app = MegaTUI()
    app.animation_level = "none"
    # Check login status before starting TUI
    # print("Checking MEGA login status...")
    app.log.info("Checking MEGA login status...")
    logged_in, message = await m.check_mega_login()

    if not logged_in:
        print(f"MEGA Login Check Failed: {message}", file=sys.stderr)
        print("Please login to 'megacmd' using 'mega-login'", file=sys.stderr)
        app.log.error(f"MEGA Login Check Failed: {message}")
        app.log.error("Please login to 'megacmd' using 'mega-login'")

        return

    print(f"MEGA Login Check: OK ({message})")

    await app.run_async(mouse=False)


if __name__ == "__main__":
    asyncio.run(run_app())
