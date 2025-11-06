import asyncio
import logging
import sys
from functools import cached_property
from typing import ClassVar, override

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.logging import TextualHandler
from textual.widgets import Footer, Header, Label

from megatui.mega import megacmd as m
from megatui.mega.data import MegaPath
from megatui.messages import (
    MakeRemoteDirectory,
    RefreshRequest,
    RenameNodeRequest,
    StatusUpdate,
    UploadRequest,
)
from megatui.ui.filelist import FileList
from megatui.ui.screens.help import HelpScreen
from megatui.ui.top_status_bar import TopStatusBar
from megatui.ui.transfers import TransfersSidePanel

logging.basicConfig(level="NOTSET", handlers=[TextualHandler()])


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

    BINDING_GROUP_TITLE = "Main Application"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            key="ctrl+c", action="quit", description="quit", show=False, priority=True
        ),
        Binding(key="q", action="quit", description="quit", show=False),
        Binding(key="f4", action="view_transfer_list"),
        Binding(
            "f2",
            action="toggle_darkmode",
            description="darkmode",
            key_display="f2",
            show=False,
            priority=True,
        ),
        Binding(
            key="f1",
            key_display="f1",
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

    def __init__(self):
        super().__init__()
        self.theme = "gruvbox"
        self.capture_mouse(None)

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """Compose the basic UI for the application."""
        # Disable mouse events

        # Our file list
        file_list = FileList()
        # Top status bar
        top_status_bar = TopStatusBar()

        footer = Footer(show_command_palette=True)
        footer.compact = True

        transfer_panel = TransfersSidePanel(widget_id="transfer-sidepanel")
        transfer_panel.toggle_class("-hidden")

        with Vertical(id="main"):
            yield Header()
            yield top_status_bar
            yield file_list
            # Placeholder for preview
            # yield Static("Preview", id="preview-pane")

            # Selected files count
            yield Label("", id="label-selected-count", expand=True)
            yield transfer_panel

            # Why does the footer create so many event messages?
            # yield footer

    async def on_mount(self) -> None:
        """Called when the app is mounted.
        Performs initial load and some initialisation.
        """
        self.log.info("MegaAppTUI mounted. Starting initial load.")

        await self.filelist.load_directory()

    # """
    # Actions #############################################################
    # """

    def action_toggle_darkmode(self) -> None:
        """Toggle darkmode for the application."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    def action_show_help_screen(self) -> None:
        """Show bindings help screen."""
        # Prevent opening a new help window when one is already there
        self.app: MegaTUI
        if self.app.screen.name == "help":
            self.pop_screen()
            return

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

    @work(exclusive=True, description="Fetching transfer list")
    async def update_transfers(self) -> None:
        """A worker method to fetch transfers and update the UI."""
        transfers = await m.mega_transfers()
        panel = self.query_one(TransfersSidePanel)
        panel.transfer_list = transfers

    async def action_view_transfer_list(self):
        panel = self.query_one(TransfersSidePanel)

        if not panel.has_class("-hidden"):
            self.update_transfers()

        panel.toggle_class("-hidden")

    #
    # # Message Handlers ###########################################################
    #

    @work(name="mkdir", group="megacmd")
    async def on_make_remote_directory(self, event: MakeRemoteDirectory) -> None:
        # If no path return
        if not event.dir_path:
            return

        success = await m.mega_mkdir(name=event.dir_path.str, path=None)
        if not success:
            self.post_message(
                StatusUpdate(
                    message=f"Could not create directory '{event.dir_path.str}' for some reason."
                )
            )

        await self.filelist.action_refresh()

    @work(name="rename")
    async def on_rename_node_request(self, msg: RenameNodeRequest):
        self.log.info(f"Renaming node `{msg.node.name}` to `{msg.new_name}`")
        await m.mega_node_rename(msg.node.path, msg.new_name)
        await self.filelist.action_refresh()

    @work(name="upload")
    async def on_upload_request(self, msg: UploadRequest):
        """Handle upload requests."""
        self.log.info("Uploading file(s)")

        files = list(msg.files)
        destination = msg.destination if msg.destination else MegaPath()
        filenames = ", ".join(str(files))
        self.log.debug(f"Destination: `{destination}`\nFiles:\n`{filenames}`")

        await m.mega_put(local_paths=tuple(files), target_path=destination, queue=True)
        # TODO We should request a refresh when the upload is completed, not
        # when it has been initiated.
        self.filelist.post_message(RefreshRequest())

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

        selection_label.update(
            Content.from_text(f"[r][b]{message.count}[/] file(s) selected[/]")
        )
        self.log.debug(f"Selected {message.count}")
        selection_label.refresh()

    @on(FileList.PathChanged)
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update TopStatusBar when path changes."""
        status_bar: TopStatusBar = self.query_one(TopStatusBar)
        status_bar.path = str(message.path)
        status_bar.clear_status_msg()

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
            """Clear TopStatusBar of all its contents."""
            self.log.info("Clearing status message in top bar.")
            status_bar.clear_status_msg()

        # Set timer for status bar to clear its contents
        status_bar.set_timer(
            delay=message.timeout if message.timeout > 0 else 10,
            callback=clear_status_msg,
        )

    # Widget access.
    @cached_property
    def filelist(self):
        """Return FileList widget."""
        return self.query_one(FileList)

    @cached_property
    def top_status_bar(self):
        """Return TopStatusBar of UI."""
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
    async with asyncio.timeout(2.0):
        logged_in = await m.check_mega_login()

    if not logged_in:
        app.log.error("MEGA Login Check Failed.\nPlease login using 'mega-login'.")

        return

    app.log.info("MEGA Login Check: OK")

    await app.run_async(mouse=False)


if __name__ == "__main__":
    try:
        asyncio.run(run_app())
    finally:
        print("Bye bye!")
        sys.exit(0)
