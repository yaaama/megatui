from typing import ClassVar, LiteralString, override

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import var
from textual.widgets import Label


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
        """Create the child widgets."""
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
        status_msg_label.update(f"[b]{new_status_msg}[/b]")

    def clear_status_msg(self) -> None:
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update()

    def signal_empty_dir(self) -> None:
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update("[b][red]Empty directory[/b][/red]")

    def signal_error(self, err_msg: str):
        status_msg_label = self.query_one(f"#{self.STATUS_MSG_ID}", Label)
        status_msg_label.update(f"[b][red][reverse]{err_msg}[/][/][/]")
