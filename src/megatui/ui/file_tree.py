# File tree
from pathlib import Path
from sre_parse import SUBPATTERN
from string import Template
from tokenize import String
from typing import ClassVar, assert_type, override

from rich.text import Text, TextType
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label, Static, Tree
from textual.widgets._directory_tree import DirEntry
from textual.widgets.tree import TreeNode


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

    _selected_items: set[Path] = set()

    def _toggle_node_selection(self, node: TreeNode[DirEntry]):
        if not node:
            return

        # Name of the node
        name = node.label

        # Data stored in node
        node_data = node.data
        if not node_data:
            self.log.error("No data associated with node.")
            return node

        fpath = node_data.path

        if fpath in self._selected_items:
            # remove
            self._selected_items.remove(fpath)
            label = Text(str(name))

        else:
            # Template for when item is selected
            label_tmpl = Template("[b][i][red]$path[/][/][/]")
            label = Text.from_markup(label_tmpl.substitute(path=name))
            self._selected_items.add(fpath)

        node.set_label(label)
        return node

    def on_directory_tree_file_selected(self, msg: DirectoryTree.DirectorySelected):
        self._toggle_node_selection(msg.node)

    def on_directory_tree_directory_selected(
        self, msg: DirectoryTree.DirectorySelected
    ):
        self._toggle_node_selection(msg.node)

    def __init__(self, starting_path: str, **kwargs):
        super().__init__(starting_path)
        self.auto_expand = False
