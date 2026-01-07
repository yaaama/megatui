"""App-level code for 'megatui'."""

import asyncio
import logging
import sys
from typing import ClassVar, override

from textual import getters, log, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.logging import TextualHandler
from textual.widgets import Footer, Header, Label

from megatui.mega import megacmd as m
from megatui.mega.data import MegaPath
from megatui.messages import (
    DeleteNodesRequest,
    DownloadNodesRequest,
    MakeRemoteDirectory,
    MoveNodesRequest,
    RefreshRequest,
    RefreshType,
    RenameNodeRequest,
    StatusUpdate,
    TransferOperationRequest,
    UploadRequest,
)
from megatui.ui.filelist import FileList
from megatui.ui.screens.help import HelpScreen
from megatui.ui.top_status_bar import TopStatusBar
from megatui.ui.transfers import TransfersSidePanel

logging.basicConfig(level="NOTSET", handlers=[TextualHandler()])


class MegaTUI(App[None], inherit_bindings=False):
    """Subclass of a textual 'App' class."""

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
            key="ctrl+c",
            action="quit",
            description="quit",
            show=False,
            priority=True,
            system=True,
        ),
        Binding(key="q", action="quit", description="quit", show=False),
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
        Binding(
            key="f2",
            action="toggle_darkmode",
            description="toggle darkmode",
            key_display="f2",
            show=False,
            priority=True,
        ),
        Binding(key="t", action="view_transfer_list", description="Display Transfers"),
    ]

    filelist = getters.query_one("#filelist", expect_type=FileList)

    top_status_bar = getters.query_one("#top-status-bar", TopStatusBar)

    def __init__(self):
        """Initialise MegaTUI."""
        super().__init__()

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """Compose the basic UI for the application."""
        # Disable mouse events
        self.theme = "gruvbox"
        self.capture_mouse(None)

        # Our file list
        file_list = FileList(id="filelist")
        # Top status bar
        top_status_bar = TopStatusBar("top-status-bar")

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

        Performs initial load of cloud directory.
        """
        log.info("MegaAppTUI mounted. Starting initial load.")

        await self.filelist.load_directory()

    # """
    # Actions #############################################################
    # """

    def action_toggle_darkmode(self) -> None:
        """Toggle darkmode for the application."""
        log.info("Toggling darkmode.")
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

        unhiding = False

        with self.app.batch_update():
            if panel.has_class("-hidden"):
                log("Updating transfers list")
                self.update_transfers()
                unhiding = True

            panel.toggle_class("-hidden")
            if unhiding:
                # Focus the window if displaying
                await self.action_focus("transfer-table")
            else:
                # Focus back to main screen
                self.action_focus_previous()

    async def on_transfer_operation_request(self, event: TransferOperationRequest):
        await m.transfer_item_set_state(event.items, event.operation)
        self.update_transfers()

    #
    # # Message Handlers ###########################################################
    #

    @on(MakeRemoteDirectory)
    @work(name="mkdir", group="megacmd")
    async def on_make_remote_directory(self, event: MakeRemoteDirectory) -> None:
        """Handler for a `MakeRemoteDirectory` message."""
        # If no path return
        if not event.dir_path:
            return

        try:
            await m.mega_mkdir(name=event.dir_path.str, path=None)
            self.filelist.post_message(RefreshRequest(RefreshType.AFTER_CREATION))
        except ValueError as e:
            self.post_message(
                StatusUpdate(
                    message=f"Could not create directory '{event.dir_path.str}'\n{e!s}."
                )
            )

    @on(RenameNodeRequest)
    @work(name="rename")
    async def on_rename_node_request(self, msg: RenameNodeRequest):
        log.info(f"Renaming node `{msg.node.name}` to `{msg.new_name}`")

        try:
            await m.mega_node_rename(msg.node.path, msg.new_name)
            self.post_message(RefreshRequest(RefreshType.DEFAULT))
        except ValueError as e:
            self.post_message(StatusUpdate(message=f"{e!s}"))

    @on(UploadRequest)
    @work(name="upload")
    async def on_upload_request(self, msg: UploadRequest):
        """Handle upload requests."""
        log.info("Uploading file(s)")

        files = list(msg.files)
        destination = msg.destination if msg.destination else MegaPath()
        filenames = ", ".join(str(files))
        log.debug(f"Destination: `{destination}`\nFiles:\n`{filenames}`")

        await m.mega_put(
            local_paths=tuple(files), target_folder_path=destination, queue=True
        )
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
            log.debug("Selection counter cleared.")
            return

        selection_label.update(
            Content.from_text(f"[r] [b]{message.count}[/b] file(s) selected [/r]")
        )
        log.debug(f"Selected {message.count}")

    @on(FileList.PathChanged)
    def on_file_list_path_changed(self, message: FileList.PathChanged) -> None:
        """Update TopStatusBar when path changes."""
        status_bar: TopStatusBar = self.query_one(TopStatusBar)
        status_bar.path = str(message.path)
        status_bar.clear_status_msg()

    @on(StatusUpdate)
    def update_status_message(self, message: StatusUpdate):
        """Refresh UI when status bar is updated."""
        self.notify(message=f"{message.message}")

        status_bar = self.top_status_bar
        status_bar.status_msg = message.message

        def clear_status_msg():
            """Clear TopStatusBar of all its contents."""
            log.info("Clearing status message in top bar.")
            status_bar.clear_status_msg()

        # Set timer for status bar to clear its contents
        status_bar.set_timer(
            delay=message.timeout if message.timeout > 0 else 10,
            callback=clear_status_msg,
        )

    @on(DeleteNodesRequest)
    async def on_delete_nodes_request(self, event: DeleteNodesRequest):
        """Helper function to call megacmd and delete files specified by arg `files`."""
        log.info("Deleting files")

        cursor_pos = self.filelist.cursor_row

        nodes = event.nodes
        node_count = len(nodes)
        tasks: list[asyncio.Task[None]] = []
        for item in nodes:
            if item.is_dir:
                tasks.append(
                    asyncio.create_task(m.mega_rm(fpath=item.path, flags=("-r", "-f")))
                )
            else:
                tasks.append(
                    asyncio.create_task(m.mega_rm(fpath=item.path, flags=None))
                )

        await asyncio.gather(*tasks)
        log.debug(
            "Deletion success for nodes: '%s'",
            ", ".join(item.path.str for item in nodes),
        )

        self.filelist.post_message(
            RefreshRequest(RefreshType.AFTER_DELETION, cursor_pos)
        )

        self.notify(
            message=f"[bold][red]{node_count}[/red][/bold] nodes(s) deleted!",
            title="Deletion",
        )

    @on(MoveNodesRequest)
    async def on_move_nodes_request(self, event: MoveNodesRequest) -> None:
        """Move nodes to new path on request."""
        files = event.nodes
        path = event.path
        if not files:
            log.warning("No files received to move.")
            return

        tasks: list[asyncio.Task[None]] = []
        for f in files:
            log.debug(f"Queueing move for `{f.name}` from `{f.path}` to: `{path}`")
            task = asyncio.create_task(m.mega_mv(file_path=f.path, target_path=path))
            tasks.append(task)

        # The function will wait here until all move operations are complete.
        await asyncio.gather(*tasks)

        self.filelist.post_message(
            RefreshRequest(RefreshType.AFTER_MV, self.filelist.cursor_row)
        )
        log.info("All file move operations completed.")

    @on(DownloadNodesRequest)
    async def on_download_nodes_request(self, event: DownloadNodesRequest) -> None:
        """Helper method to download files.

        TODO: Check for existing files on system and handle them
        """
        files = event.nodes
        download_path = self.filelist.download_path
        if not files:
            log.warning("Did not receive any files to download!")
            return

        tasks: list[asyncio.Task[None]] = []
        dl_len = 0
        for file in files:
            log.debug(
                f"Queueing download for `{file.name}` from `{file.path}` to: `{download_path}`"
            )
            task = asyncio.create_task(
                m.mega_get(target_path=str(download_path), remote_path=str(file.path))
            )
            tasks.append(task)
            dl_len += 1

        await asyncio.gather(*tasks)

        self.notify(
            message=f"Queued [red][i][b]{dl_len}[/red][/i][/b] files for download.",
            title="Downloading",
            markup=True,
        )

        self.filelist.post_message(
            RefreshRequest(RefreshType.AFTER_DOWNLOAD, reload=False)
        )


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
