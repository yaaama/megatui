from typing import override

from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label


class ConfirmationScreen(ModalScreen[bool]):
    DEFAULT_CSS = """ """

    def __init__(self, title: str, prompt: str, extra_info: str | None = None):
        super().__init__()
        self.prompt_title = title
        self.prompt = prompt
        self.border_title = title

        if extra_info:
            self.extra_info = extra_info

    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        match event.key.lower():
            case "y":
                event.stop()
                self.dismiss(True)
            case "ctl-c":
                self.dismiss(False)
            case _:
                event.stop()
                self.dismiss(False)

    @override
    def compose(self) -> ComposeResult:
        container = Vertical(id="vert-container")
        container.border_title = self.prompt_title

        with container:
            self.border_title = self.prompt_title
            yield Label(self.prompt, id="confirmation-prompt", expand=True)
            if self.extra_info:
                yield Label(self.extra_info, id="confirmation-extra-info", expand=True)
            with Center():
                yield Label(
                    "Press [b]'Y|y'[/] to confirm deletion, anything else to cancel.",
                    id="confirmation-instructions",
                    expand=True,
                )
