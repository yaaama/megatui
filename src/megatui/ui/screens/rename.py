# Rename popup
from typing import ClassVar, TypedDict, override

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.validation import Regex
from textual.widgets import Input, Label
from megatui.mega.megacmd import MegaItem


class RenameDialog(ModalScreen[tuple[str, MegaItem]]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="submit_rename", show=True),
    ]

    def __init__(
        self,
        popup_prompt: str,
        emoji_markup_prepended: str,
        node: MegaItem,
        initial_input: str | None = None,
    ) -> None:
        """Initialise the rename dialog.

        Args:
            popup_prompt: The prompt for the input.
            emoji_prepended: Emoji to prepend the prompt.
            item_info: A dictionary containing 'name', 'handle', and 'path' for the item.
            initial_input: The initial value for the input box.
        """
        super().__init__()
        self._emoji = emoji_markup_prepended
        """ Emoji to prepend the prompt. """
        self._prompt = popup_prompt
        """ Label to display above input box. """
        self._initial = initial_input
        """ The initial value to use for the input."""

        txt = f"{self._emoji} {self._prompt}"
        self.prompt: Text = Text.from_markup(txt)
        """ Calculated prompt text. """

        self.node = node
        """ Information about the node being renamed. """

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
    def action_submit_rename(self) -> tuple[str, MegaItem] | None:
        if value := self.query_one(Input).value.strip():
            self.dismiss(result=(value, self.node))

    def action_close_window(self) -> None:
        self.app.pop_screen()
