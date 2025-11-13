"""messages.py
Messages that are used throughout the application.
"""

from collections.abc import Iterable
from enum import Enum, auto
from pathlib import Path

from textual.message import Message

from megatui.mega.data import MegaNode, MegaPath
from megatui.mega.megacmd import MegaItems

NOTIF_TYPES: set[str] = {
    "info",
    "err",
    "warn",
    "op",
    "done",
}  # Different kinds of notifications.


class StatusUpdate(Message):
    """Message for a widget to update status bar."""

    def __init__(self, message: str, timeout: int = 10) -> None:
        super().__init__()
        self.message = message
        self.timeout = timeout


class UploadRequest(Message):
    def __init__(self, files: Iterable[Path], destination: MegaPath | None) -> None:
        super().__init__()
        self.files: Iterable[Path] = files
        self.destination: MegaPath | None = destination


class RefreshType(Enum):
    """Defines the context for a refresh request."""

    DEFAULT = auto()  # A standard, user-initiated refresh (e.g., pressing 'r')
    AFTER_DELETION = auto()  # Refresh after one or more items were deleted
    AFTER_CREATION = auto()  # Refresh after a new item (file/dir) was created


class RefreshRequest(Message):
    """Requests that the file list be refreshed."""

    def __init__(
        self,
        type: RefreshType = RefreshType.DEFAULT,
        cursor_row_before_refresh: int | None = None,
    ) -> None:
        super().__init__()
        self.type = type
        self.cursor_row_before_refresh = cursor_row_before_refresh


class RenameNodeRequest(Message):
    def __init__(self, node: MegaNode, new_name: str):
        super().__init__()
        self.node = node
        self.new_name = new_name


class MakeRemoteDirectory(Message):
    def __init__(self, dir_path: MegaPath):
        super().__init__()
        self.dir_path = dir_path


class DeleteNodesRequest(Message):
    def __init__(self, nodes: MegaItems):
        super().__init__()
        self.nodes = nodes


class Notification(Message):
    """Send a notification to the user."""

    def __init__(
        self,
        notif_type: str | None,
        message: str,
        markup: bool = False,
        timeout: int | None = None,
    ):
        super().__init__()
        # Assign notification kind, defaults to "info" if bad value
        if notif_type in NOTIF_TYPES:
            self.notif_type = notif_type
            self.markup = True
        else:
            self.notif_type = "info"
            self.markup = False

        self.message = message
        self.markup = markup
        self.timeout = timeout
