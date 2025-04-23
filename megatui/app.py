from typing import override

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, ListView
from textual.reactive import var

from .mega import megacmd as megacmd

# Import from sibling module widgets
from .ui.widgets import FilesListView, FilesListItem


class MegaAppTUI(App[None]):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh List", key_display="r"),
        Binding("j", "cursor_down", "Cursor Down", key_display="j"),
        Binding("k", "cursor_up", "Cursor Up", key_display="k"),
        Binding("l", "navigate_in", "Enter Dir", key_display="l / Enter"),
        Binding("h", "navigate_out", "Parent Dir", key_display="h / Backspace"),
        Binding("enter", "navigate_in", "Enter Dir", show=False),  # Map Enter
        Binding("backspace", "navigate_out", "Parent Dir", show=False),  # Map Backspace
        # Add other bindings
    ]

    CSS = """
    Vertical {
        grid-size: 2;
    }
    Horizontal {
        grid-size: 2; /* Make two columns */
    }
    #file-list {
        width: 1fr;
        border-right: ascii $accent; /* Separator */
    }
    #preview-pane {
        width: 0.5fr;
        padding: 0 1;
    }
    #status-bar {
        height: 1;
        dock: bottom; /* Place above footer */
        background: $accent-darken-2;
    }
    """
    # CSS should be added as a file
    # CSS_PATH = "app.css"

    current_path: var[str] = var("/")  # Track current path at the app level
    selected_item_info: var[str] = var("")  # Reactive var for status bar

    @override
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal():  # Arrange list and preview side-by-side
                yield FilesListView(id="file-list", initial_index=0)
                # TODO Make this ls into their directories
                # yield Static(
                #     "Select an item...", id="preview-pane", expand=True, markup=False
                # )

        yield Static(id="status-bar", markup=False)  # Add a status bar
        yield Footer()

    # --- Message Handlers ---
    def on_file_list_view_highlighted(self, message: ListView.Highlighted) -> None:
        """Called when the highlighted item in any ListView changes."""
        # Check if the message is from our specific file list
        if message.list_view.id != "file-list":
            return

        self.query_one("#status-bar", Static)
        list_item = message.item  # The highlighted ListItem

        if not (isinstance(list_item, FilesListItem)):
            return

        item = list_item.item

        # Update status bar
        self.selected_item_info = f"{item.name} ({item.ftype})"

        # TODO: Add async worker to fetch *actual* file content for preview

    def watch_selected_item_info(self, new_info: str) -> None:
        """Update status bar when reactive var changes."""
        self.query_one("#status-bar", Static).update(f"Selected: {new_info}")

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        # Initial load is handled by FileListView's on_mount
        pass

    # Update status or header when path changes
    def on_file_list_view_path_changed(
        self, message: FilesListView.PathChanged
    ) -> None:
        self.current_path = message.new_path
        # Example: Update subtitle - adapt as needed
        self.query_one(Header).tall = False  # Keep header standard height
        self.sub_title = f"Path: {self.current_path}"

    def on_file_list_view_load_error(self, message: FilesListView.LoadError) -> None:
        """Handles load error (e.g., show status message)."""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(f"[bold red]Error loading list: {message.error}")
        self.app.notify(
            "Failed to load directory contents.", title="Error", severity="error"
        )

    def action_refresh(self) -> None:
        """Called to refresh the file list."""
        list_view = self.query_one(FilesListView)
        list_view.load_directory(self.current_path)  # Reload current directory

    # --- Action methods ---
    def action_cursor_down(self) -> None:
        self.query_one(FilesListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(FilesListView).action_cursor_up()

    def action_navigate_in(self) -> None:
        self.query_one(FilesListView).action_navigate_in()

    def action_navigate_out(self) -> None:
        self.query_one(FilesListView).action_navigate_out()
