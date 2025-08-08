# File tree
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import ClassVar, override

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label
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
                starting_path="/home/aayush/",
                id="filetree",
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
        Binding("full_stop", "toggle_hidden", "Toggle Hidden", show=False),
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

    class FilterMethod(Enum):
        NONE = 0
        HIDDEN = 1

    filter_type = FilterMethod.HIDDEN
    _selected_items: set[Path] = set()

    def filter_hidden_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if not path.name.startswith(".")]

    @override
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        match self.filter_type:
            case self.FilterMethod.NONE:
                return paths
            case self.FilterMethod.HIDDEN:
                return self.filter_hidden_paths(paths)

        return paths

    def action_toggle_hidden(self):
        """Toggle visibility of hidden files in the file tree."""
        if self.filter_type == self.FilterMethod.HIDDEN:
            self.filter_type = self.FilterMethod.NONE
        else:
            self.filter_type = self.FilterMethod.HIDDEN

        self.reload()

    def _selection_status_node_label(self, node: TreeNode[DirEntry], selected: bool):
        """Helper function to produce node label with 'selected' status."""
        assert node
        assert node.data

        # When selected
        if selected:
            return Text.from_markup(f"[b][red]*[/] {node.data.path}[/]")

        # Else return regular name as label
        return Text(f"{node.data.path.name}")

    def _toggle_node_selection(self, node: TreeNode[DirEntry]) -> None:
        if not node:
            self.log.error("Toggling selection on a non-existent node.")
            return

        # Data stored in node
        node_data = node.data
        assert node_data, "Node has null data attribute."
        if not node_data:
            self.log.error("No data associated with node.")

        new_selection_state: bool = True
        # If not previously selected
        if node_data.path not in self._selected_items:
            self._selected_items.add(node_data.path)

        else:
            self._selected_items.remove(node_data.path)
            new_selection_state = False

        node.set_label(self._selection_status_node_label(node, new_selection_state))

    def on_directory_tree_file_selected(self, msg: DirectoryTree.DirectorySelected):
        self._toggle_node_selection(msg.node)

    def on_directory_tree_directory_selected(
        self, msg: DirectoryTree.DirectorySelected
    ):
        self._toggle_node_selection(msg.node)

    def __init__(self, starting_path: str, id: str):
        super().__init__(path=starting_path, id=id)
        self.auto_expand = False
