# File tree
from pathlib import Path
from typing import ClassVar, override

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label, Static, Tree


class UploadFilesModal(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="escape,q", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="file_select", show=True),
    ]

    @override
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Select file to upload", id="uploadfiles-heading")
            yield LocalSystemFileTree(
                id="filetree",
                starting_path="/home/aayush/downloads",
            )


class LocalSystemFileTree(DirectoryTree):
    BINDINGS = [
        Binding(
            "ctrl+h",
            "cursor_parent",
            "Cursor to parent",
            show=False,
        ),
        Binding(
            "ctrl+l",
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

    COMPONENT_CLASSES = {
        "node-selected",
    }

    # @on(Tree.NodeSelected)
    # def on_node_selected(self, message: Tree.NodeSelected):
    #     label = Text(message.node.label.__str__(), style="italic red")
    #     message.node.set_label(label)

    def __init__(self, starting_path: str, **kwargs):
        super().__init__(starting_path)
        self.auto_expand = False
