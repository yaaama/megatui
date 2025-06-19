from pathlib import Path
from typing import ClassVar, LiteralString, override

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


class TopStatusBar(Horizontal):
    PATH_LABEL_ID: ClassVar[LiteralString] = "top-status-bar-path"
    STATUS_MSG_ID: ClassVar[LiteralString] = "top-status-bar-msg"

    path: var[str] = var("")
    status_msg: var[str] = var("")

    DEFAULT_CSS = f"""
    TopStatusBar {{
        height: 1;
        background: $panel;
    }}
    #{PATH_LABEL_ID} {{
        content-align: left middle;
        width: 1fr;
        margin: 0 1;

    }}
    #{STATUS_MSG_ID} {{
        content-align: right middle;
        min-width: 20%;
        width: auto;
        margin: 0 1;
    }}
    """

    @override
    def compose(self) -> ComposeResult:
        """Create the child widgets"""
        # Yield the labels. Their content will be set by the watch methods
        # immediately after this, and then every time the reactive var changes.
        yield Label(id=self.PATH_LABEL_ID)
        yield Label(id=self.STATUS_MSG_ID)

    def watch_path(self, new_path: str) -> None:
        """Called when self.path is modified."""
        path_label = self.query_one(f"#{self.PATH_LABEL_ID}", Label)
        path_label.update(f"[b]Path:[/] [i]'{new_path}'[/]")

    def watch_status_msg(self, new_status_msg: str) -> None:
        """Called when self.status_msg is modified."""
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update(f"[reverse][b]{new_status_msg}[/b][/reverse]")
        status_msg_label.visible = True

    def hide_status_msg_label(self) -> None:
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.visible = False

    def signal_empty_dir(self) -> None:
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update("[b][red]Empty directory![/b][/red]")

    def signal_error(self, err_msg: str):
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update(f"[b][red][reverse]{err_msg}[/][/][/]")


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

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("f2", "toggle_darkmode", "toggle darkmode", key_display="f2"),
        Binding("f3", "download", "download file"),
    ]

    DL_PATH = Path.home() / "megadl"

    # --- UI Composition ---
    @override
    def compose(self) -> ComposeResult:
        """
        Compose the basic UI for the application.
        """
        # Disable mouse events
        self.capture_mouse(None)
        self.theme = "gruvbox"

        file_list = FileList()
        top_status_bar = TopStatusBar()

        with Vertical(id="main"):
            yield Header()
            yield top_status_bar
            yield file_list
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
        await file_list.load_directory(file_list.curr_path)

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

        dl_len = len(files)
        for i, file in enumerate(files):
            self.post_message(
                StatusUpdate(message=f"Downloading ({i + 1}/{dl_len}) '{file.name}'")
            )
            await mega_get(
                target_path=str(self.DL_PATH),
                remote_path=str(file.full_path),
                is_dir=file.is_dir(),
            )
            rendered_emoji = Text.from_markup(text=":ballot_box_with_check:")
            title = Text.from_markup(f"[b]{rendered_emoji} download complete![/]")
            self.notify(
                f"'{file.name}' finished downloading ", title=f"{title}", markup=True
            )

    async def action_download(self) -> None:
        """
        Download the currently highlighted file or a selection of files.

        TODO: Can download multiple files using selection
        TODO: Ask for download path
        TODO: Display download status
        """
        file_list = self.query_one(FileList)
        dl_items = file_list.selected_items()

        # If dl_items is empty
        if len(dl_items) == 0:
            # Default to downloading the currently highlighted item
            highlighted = file_list.get_highlighted_megaitem()
            if not highlighted:
                self.log.error("Could not default to highlighted item. Cancelling.")
                return

            # Append highlighted item to the list
            dl_items.append(highlighted)

        self.app.log.info(f"action_download: Downloading files: '{rc.print(dl_items)}'")
        await self.download_files(dl_items)

    def action_toggle_darkmode(self) -> None:
        """Toggles darkmode."""
        self.log.info("Toggling darkmode.")
        self.action_toggle_dark()

    """
    # Watchers ################################################################
    """

    """
    # Message Handlers ###########################################################
    """

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
        status_bar = self.query_one(TopStatusBar)
        status_bar.path = message.path

    @on(FileList.EmptyDirectory)
    def on_file_list_empty_directory(self, message: FileList.EmptyDirectory):
        self.top_status_bar().signal_empty_dir()

    @on(FileList.LoadError)
    def on_file_list_load_error(self, message: FileList.LoadError):
        self.top_status_bar().signal_error(f"Failed to load path: {message.path}")
        # Log the detailed error
        self.log.error(f"Error loading directory: {message.error}")

    @on(StatusUpdate)
    def update_status_message(self, message: StatusUpdate):
        """
        Refresh UI when status bar is updated.
        """
        status_bar = self.query_one(TopStatusBar)
        status_bar.status_msg = message.message

        def clear_status_msg():
            self.log.info("Clearing status message in top bar.")
            status_bar.hide_status_msg_label()

        status_bar.set_timer(
            delay=message.timeout if message.timeout > 0 else 10,
            callback=clear_status_msg,
        )

    """ Widget access. """

    def top_status_bar(self):
        return self.query_one(TopStatusBar)
