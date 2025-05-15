# File tree
from pathlib import Path
from typing import override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Static


class FileTreeScreen(ModalScreen[None]):
    @override
    def compose(self) -> ComposeResult:
        yield LocalSystemFileTree()


class LocalSystemFileTree(Static):
    BINDINGS = [
        Binding(
            "shift+left",
            "cursor_parent",
            "Cursor to parent",
            show=False,
        ),
        Binding(
            "shift+right",
            "cursor_parent_next_sibling",
            "Cursor to next ancestor",
            show=False,
        ),
        Binding(
            "shift+up",
            "cursor_previous_sibling",
            "Cursor to previous sibling",
            show=False,
        ),
        Binding(
            "shift+down",
            "cursor_next_sibling",
            "Cursor to next sibling",
            show=False,
        ),
        Binding("space", "select_cursor", "Select", show=False),
        Binding("tab", "toggle_node", "Toggle", show=False),
        Binding(
            "shift+tab",
            "toggle_expand_all",
            "Expand or collapse all",
            show=False,
        ),
        Binding("k", "cursor_up", "Cursor Up", show=False),
        Binding("j", "cursor_down", "Cursor Down", show=False),
    ]

    @override
    def compose(self) -> ComposeResult:
        home: Path = Path().home()
        yield DirectoryTree(path=home)
