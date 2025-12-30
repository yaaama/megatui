from typing import TYPE_CHECKING, override

from textual import events, getters
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class ConfirmationScreen(ModalScreen[bool]):
    if TYPE_CHECKING:
        from megatui.app import MegaTUI

        app = getters.app(MegaTUI)

    def __init__(self, title: str, prompt: str, extra_info: str | None = None):
        super().__init__()
        self.prompt_title = Content.from_rich_text(title)
        self.prompt = Content.from_rich_text(prompt)
        self.border_title = Content.from_rich_text(title)

        if extra_info:
            self.extra_info = Content.from_rich_text(extra_info)

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
                yield Label(self.extra_info, id="confirmation-extra-info")
            yield Label(
                "Press [b]'Y|y'[/] to confirm deletion,\nanything else to cancel.",
                id="confirmation-instructions",
            )
