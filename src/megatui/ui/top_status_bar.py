from typing import ClassVar, LiteralString, override

import textual.getters as getters
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import var
from textual.widgets import Label


class TopStatusBar(Horizontal):
    PATH_LABEL_ID: ClassVar[LiteralString] = "bar--path"
    STATUS_MSG_ID: ClassVar[LiteralString] = "bar--msg"
    PATH_STR_ID: ClassVar[LiteralString] = "bar--path-str"

    path: var[str] = var("")
    status_msg: var[str] = var("")

    path_label = getters.child_by_id("bar--path-str", Label)
    status_msg_label = getters.child_by_id("bar--msg", Label)

    DEFAULT_CSS = """ """

    @override
    def compose(self) -> ComposeResult:
        """Create the child widgets."""
        # Yield the labels. Their content will be set by the watch methods
        # immediately after this, and then every time the reactive var changes.

        yield Label(content="[b]Path:[/]", id=self.PATH_LABEL_ID, markup=True)
        yield Label(content="", id=self.PATH_STR_ID, expand=True)
        yield Label(id=self.STATUS_MSG_ID)

    def watch_path(self, new_path: str) -> None:
        """Called when self.path is modified."""
        self.path_label.update(f"'{new_path}'")

    def watch_status_msg(self, new_status_msg: str) -> None:
        """Called when self.status_msg is modified."""
        self.status_msg_label.update(f"[b]{new_status_msg}[/b]")

    def clear_status_msg(self) -> None:
        """Clear status message from top bar."""
        self.status_msg_label.update()

    def signal_empty_dir(self) -> None:
        """Signal to the user that the directory is empty."""
        self.status_msg_label.update("[b][red]Empty directory[/b][/red]")

    def signal_error(self, err_msg: str):
        """Signal an error to the user."""
        self.status_msg_label.update(f"[b][red][reverse]{err_msg}[/][/][/]")
