# Rename popup
from typing import override

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.validation import Regex
from textual.widgets import Input, Label


class RenameDialog(ModalScreen[str]):

    BINDINGS = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="submit_rename", show=True),
    ]

    def __init__(
        self, prompt: str, initial: str | None = None, emoji: str = ":page_facing_up"
    ) -> None:
        """Initialise the rename dialog.

        Args:
            prompt: The prompt for the input.
            initial: The initial value for the input.
        """
        super().__init__()
        self._emoji = emoji
        """ Emoji to prepend the prompt. """
        self._prompt = prompt
        """ Label to display above input box. """
        self._initial = initial
        """ The initial value to use for the input."""

        txt = f"{self._emoji} {self._prompt}"
        self.prompt: Text = Text.from_markup(txt)
        """ Calculated prompt text. """

    @override
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.prompt, id="label-new-file-name")
            yield Input(
                placeholder=self._initial or "Enter new name...",
                max_length=60,
                valid_empty=False,
                id="input-rename-file",
                validators=[Regex("^[a-zA-Z0-9_.\\s]*")],
                validate_on=["changed", "submitted"],
            )

    @on(Input.Submitted, "#input-rename-file")
    def action_submit_rename(self) -> str | None:
        if value := self.query_one(Input).value.strip():
            self.dismiss(result=value)

    def action_close_window(self) -> None:
        self.app.pop_screen()
