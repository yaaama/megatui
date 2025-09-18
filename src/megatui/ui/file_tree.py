# File tree
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from string import Template
from typing import ClassVar, override

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label
from textual.widgets._directory_tree import DirEntry
from textual.widgets._tree import TOGGLE_STYLE, Tree
from textual.widgets.tree import TreeNode


class LocalSystemFileTree(DirectoryTree, inherit_bindings=False):
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
    SELECTED_NODE_PREFIX = "[bold][red]*[/]"

    def filter_hidden_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Returns paths that are NOT hidden."""
        return [path for path in paths if not path.name.startswith(".")]

    @override
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        match self.filter_type:
            case self.FilterMethod.NONE:
                return paths
            case self.FilterMethod.HIDDEN:
                return self.filter_hidden_paths(paths)
        return paths

    async def _recenter_cursor(self):
        """Recenter cursor."""
        with self.app.batch_update():
            await self.reload()
            self.action_cursor_down()
            self.action_cursor_up()
        self.refresh()

    async def action_toggle_hidden(self):
        """Toggle visibility of hidden files in the file tree."""
        # self.anchor(True)
        if self.filter_type == self.FilterMethod.HIDDEN:
            self.filter_type = self.FilterMethod.NONE
        else:
            self.filter_type = self.FilterMethod.HIDDEN

        await self._recenter_cursor()

    def _selection_status_node_label(self, node: TreeNode[DirEntry], selected: bool):
        """Helper function to produce node label with 'selected' status."""
        # When selected
        template = Template("$sel$label")
        kwds: dict[str, str] = {}
        if selected:
            kwds["sel"] = self.SELECTED_NODE_PREFIX
        else:
            kwds["sel"] = ""

        kwds["label"] = str(node.label)

        return Text.from_markup(template.substitute(kwds))

    def _set_node_selection_state(self, node: TreeNode[DirEntry], select: bool) -> None:
        """Applies a specific selection state (select=True or select=False) to a single node."""
        if not (node and node.data and node.data.path):
            return

        resolved = node.data.path.resolve()
        if select:
            self._selected_items.add(resolved)
        else:
            self._selected_items.discard(resolved)

        # Update the visual representation of the node
        node.refresh()

    def _is_descendant(self, child: Path, parent: Path) -> bool:
        """Checks if 'child' is the same as or a subpath of 'parent'."""
        try:
            parent_resolved = parent.resolve(strict=True)
            child_resolved = child.resolve(strict=True)

        except FileNotFoundError:
            return False  # Path must exist to be a descendant

        return child_resolved.is_relative_to(parent_resolved)

    def _is_node_or_ancestor_selected(self, node: TreeNode[DirEntry]) -> bool:
        """Checks if the node's path or any of its ancestors are in the selection set."""
        if not (node and node.data and node.data.path):
            return False

        node_path = node.data.path
        for selected_path in self._selected_items:
            if self._is_descendant(node_path, selected_path):
                return True
        return False

    @override
    def render_label(
        self, node: TreeNode[DirEntry], base_style: Style, style: Style
    ) -> Text:
        """Render a label for the given node.

        Args:
            node: A tree node.
            base_style: The base style of the widget.
            style: The additional style for the label.

        Returns:
            A Rich Text object containing the label.
        """
        rendered_label = super().render_label(node, base_style, style)

        if not (node and node.data and node.data.path):
            return rendered_label

        path = node.data.path.resolve()

        if self._is_node_or_ancestor_selected(node):
            # If it is, prepend our selection marker.
            # selection_marker = Text.from_markup(f"[bold][red]*[/]")
            return Text.from_markup(f"{self.SELECTED_NODE_PREFIX} ") + rendered_label
        else:
            # If not selected, return the original label unmodified.
            return Text("  ") + rendered_label

    def _toggle_node_selection(self, node: TreeNode[DirEntry]) -> None:
        if not (node and node.data and node.data.path):
            self.log.error("Toggling selection on a non-existent node.")
            return

        # The new state is the opposite of the current state.
        is_currently_selected = node.data.path.resolve() in self._selected_items
        self._set_node_selection_state(node, not is_currently_selected)

    def _apply_selection_recursively(
        self, node: TreeNode[DirEntry], select: bool
    ) -> None:
        """Recursively applies a selection state to a node and all its descendants."""
        # Apply the state to the current node
        self._set_node_selection_state(node, select)

        for child in node.children:
            self._apply_selection_recursively(child, select)

    def _toggle_dir_node_selection(self, node: TreeNode[DirEntry]):
        assert node and node.data and node.data.path
        # Determine the new state based on the top-level directory's current state.
        # If the main directory is not currently in the selection, the new state is to select.
        new_selection_state = node.data.path not in self._selected_items

        # Kick off the recursive process to apply this new state everywhere.
        self._apply_selection_recursively(node, new_selection_state)

    def get_selected_items_path(self) -> Iterable[Path]:
        return self._selected_items

    @on(DirectoryTree.FileSelected)
    def file_selected(self, msg: DirectoryTree.FileSelected):
        self._toggle_node_selection(msg.node)

    @on(DirectoryTree.DirectorySelected)
    def directory_selected(self, msg: DirectoryTree.DirectorySelected):
        self._toggle_dir_node_selection(msg.node)

    def __init__(self, path: str, id: str):
        super().__init__(path=path, id=id)
        self.auto_expand = False


class UploadFilesModal(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="escape,q", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="upload_selected", show=True),
    ]

    def action_upload_selected(self) -> None:
        filetree = self.query_one(LocalSystemFileTree)
        selected: Iterable[Path] = filetree.get_selected_items_path()

        # Prepare notification for upload
        file_names = [item.name for item in selected]
        flattened = ", ".join(file_names)

        self.notify(message=f"{flattened}", title="Uploading Files")
        pass

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="verticalcontainer"):
            yield Label("Select file to upload", id="uploadfiles-heading")
            yield LocalSystemFileTree(
                path="/home/aayush/",
                id="filetree",
            )
