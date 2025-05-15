# File Actions
from typing import override

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class RenamePopup(ModalScreen):
    filename: str

    def __init__(self, filename: str):
        self.filename = filename
        super().__init__()

    @override
    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Rename '{self.filename}'")
            yield Input(
                placeholder="Enter new name...",
                max_length=80,
                valid_empty=False,
                id="rename-input-box",
            )
