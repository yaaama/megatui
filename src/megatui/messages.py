"""
messages.py
Messages that are used throughout the application.
"""

from collections.abc import Iterable
from pathlib import Path, PurePath

from textual.message import Message

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
    def __init__(
        self, files: Iterable[Path], destination: PurePath | str | None
    ) -> None:
        super().__init__()
        self.files: Iterable[Path] = files
        self.destination: PurePath | str | None = destination


class Notification(Message):
    """Send a notification to the user"""

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
