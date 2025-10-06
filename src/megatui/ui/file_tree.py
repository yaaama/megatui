# File tree
import typing
from collections.abc import Iterable
from enum import Enum, auto
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
from textual.widgets.tree import TreeNode

from megatui.messages import UploadRequest

if typing.TYPE_CHECKING:
    from megatui.app import MegaTUI


class FilterMethod(Enum):
    NONE = auto()
    HIDDEN = auto()


class LocalSystemFileTree(DirectoryTree, inherit_bindings=False):
    app: "MegaTUI"

    BINDING_GROUP_TITLE = "Local File Explorer"
    BINDINGS = [
        Binding("h", "cursor_parent", "Cursor to parent", show=False),
        Binding("L", "cursor_parent_next_sibling", "Cursor to next ancestor", show=False),
        Binding("shift+up", "cursor_previous_sibling", "Cursor to previous sibling", show=False),
        Binding("shift+down", "cursor_next_sibling", "Cursor to next sibling", show=False),
        Binding("full_stop", "toggle_hidden", "Toggle Hidden", show=False),
        Binding("space", "select_cursor", "Select", show=False),
        Binding("tab", "toggle_node", "Toggle", show=False),
        Binding("shift+tab", "toggle_expand_all", "Expand or collapse all", show=False),
        Binding("k", "cursor_up", "Cursor Up", show=False),
        Binding("j", "cursor_down", "Cursor Down", show=False),
    ]

    COMPONENT_CLASSES = {
        "node-selected",
    }

    SELECTED_NODE_PREFIX = "[bold][red]*[/]"
    UNSELECTED_NODE_PREFIX = " "

    @override
    def action_cursor_parent_next_sibling(self) -> None:
        """Move the cursor to the parent's next sibling."""
        cursor_node = self.cursor_node
        if cursor_node is None or cursor_node.parent is None:
            return

        next = cursor_node.parent.next_sibling
        if next is None:
            return

        self.move_cursor(next, animate=False)

    def action_cursor_parent_previous_sibling(self) -> None:
        """Move cursor to parents previous sibling."""
        cursor_node = self.cursor_node
        if cursor_node is None or cursor_node.parent is None:
            return

        prev = cursor_node.parent.previous_sibling
        if prev is None:
            return

        self.move_cursor(prev, animate=False)

    @override
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filters paths based on the current filter_type."""
        match self.filter_type:
            case FilterMethod.NONE:
                return paths
            case FilterMethod.HIDDEN:
                return [path for path in paths if not path.name.startswith(".")]
        return paths

    async def _reload_and_recenter(self):
        """Reloads the tree and attempts to keep the cursor centered."""
        with self.app.batch_update():
            await self.reload()
            self.action_cursor_down()
            self.action_cursor_up()
            self.refresh()

    async def action_toggle_hidden(self):
        """Toggle visibility of hidden files in the file tree."""
        # self.anchor(True)
        if self.filter_type == FilterMethod.HIDDEN:
            self.filter_type = FilterMethod.NONE
        else:
            self.filter_type = FilterMethod.HIDDEN

        await self._reload_and_recenter()

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

    @staticmethod
    def _is_descendant(child: Path, parent: Path) -> bool:
        """Checks if a path is a descendant of another, but not the same path."""
        if child == parent:
            return False
        try:
            return child.resolve(strict=True).is_relative_to(parent.resolve(strict=True))
        except FileNotFoundError:
            return False

    def _is_node_rendered_as_selected(self, node: TreeNode[DirEntry]) -> bool:
        """Determines if a node should be visually displayed as selected."""
        if not (node and node.data and node.data.path):
            return False

        path = node.data.path.resolve()

        # If the path or any of its ancestors are explicitly deselected, it's not selected.
        if path in self._deselected_items or any(
            path.is_relative_to(p) for p in self._deselected_items
        ):
            return False

        # If the path is explicitly selected, it's selected.
        if path in self._selected_items:
            return True

        # If any ancestor is explicitly selected, it's implicitly selected.
        if any(path.is_relative_to(p) for p in self._selected_items):
            return True

        return False

    @override
    def render_label(self, node: TreeNode[DirEntry], base_style: Style, style: Style) -> Text:
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

        prefix = (
            self.SELECTED_NODE_PREFIX
            if self._is_node_rendered_as_selected(node)
            else self.UNSELECTED_NODE_PREFIX
        )

        return Text.from_markup(f"{prefix} ") + rendered_label

    def _cleanup_descendant_states(self, path: Path) -> None:
        """Removes all descendants of a path from both selection and deselection sets."""
        self._selected_items = {
            p for p in self._selected_items if not self._is_descendant(p, path)
        }
        self._deselected_items = {
            p for p in self._deselected_items if not self._is_descendant(p, path)
        }

    def _toggle_selection(self, node: TreeNode[DirEntry]) -> None:
        """Toggles the selection state of a node based on the new logic."""
        if not (node and node.data and node.data.path):
            return

        path = node.data.path.resolve()
        is_currently_selected = self._is_node_rendered_as_selected(node)

        # First, clear any more specific rules for children of the current node.
        self._cleanup_descendant_states(path)

        if is_currently_selected:
            # GOAL: Deselect the node.
            self._selected_items.discard(path)
            # If an ancestor is selected, this node becomes an explicit exception.
            is_ancestor_selected = any(path.is_relative_to(p) for p in self._selected_items)
            if is_ancestor_selected:
                self._deselected_items.add(path)
        else:
            # GOAL: Select the node.
            self._deselected_items.discard(path)
            self._selected_items.add(path)

        # Refresh the display of the node and its immediate children
        node.refresh()
        for child in node.children:
            child.refresh()

    def get_selected_items_path(self) -> Iterable[Path]:
        """
        Computes and returns the final set of selected file paths by resolving
        parent selections and child deselections.
        """
        final_paths: set[Path] = set()
        # 1. Add all files from explicitly selected items
        for path in self._selected_items:
            if path.is_file():
                final_paths.add(path)
            elif path.is_dir():
                for file_path in path.rglob("*"):
                    if file_path.is_file():
                        final_paths.add(file_path)

        # 2. Remove any files that are part of a deselected group
        if not self._deselected_items:
            return final_paths

        return {
            p
            for p in final_paths
            if not any(p.is_relative_to(deselected) for deselected in self._deselected_items)
        }

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, msg: DirectoryTree.FileSelected) -> None:
        """Handles file selection events."""
        self._toggle_selection(msg.node)

    @on(DirectoryTree.DirectorySelected)
    def on_directory_selected(self, msg: DirectoryTree.DirectorySelected) -> None:
        """Handles directory selection events."""
        self._toggle_selection(msg.node)

    def __init__(self, path: str, id: str):
        super().__init__(path=path, id=id)
        # Do not auto expand selected folders
        self.auto_expand = False
        # Keep cursor in the center
        self.center_scroll = True
        # Filter out hidden files by default
        self.filter_type = FilterMethod.HIDDEN
        # Paths that are explicitly selected.
        self._selected_items: set[Path] = set()
        # Paths that are explicitly deselected (as an exception to a selected parent).
        self._deselected_items: set[Path] = set()


class UploadFilesModal(ModalScreen[None]):
    """Modal screen for uploading local files."""

    app: "MegaTUI"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="escape,q", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="finished", show=True),
    ]

    def action_finished(self) -> None:
        filetree = self.query_one(LocalSystemFileTree)
        selected: Iterable[Path] = filetree.get_selected_items_path()

        if not selected:
            self.dismiss()
            return

        else:
            filelist = self.app.query_one("#filelist")
            filelist.post_message(UploadRequest(files=selected, destination=None))
            self.dismiss()

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="verticalcontainer"):
            yield Label("Select file to upload", id="uploadfiles-heading")
            yield LocalSystemFileTree(
                path=str(Path.home()),
                id="filetree",
            )
