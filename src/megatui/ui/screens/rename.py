from __future__ import annotations

# Rename popup
from typing import TYPE_CHECKING, override

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.validation import Regex
from textual.widgets import Input, Label

from megatui.mega.megacmd import MegaNode
from megatui.messages import RenameNodeRequest

if TYPE_CHECKING:
    from megatui.app import MegaTUI


class RenameDialog(ModalScreen[tuple[str, MegaNode]]):
    app: "MegaTUI"
    BINDINGS: list[BindingType] = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="enter", action="submit_rename", show=True),
    ]

    def __init__(
        self,
        popup_prompt: str,
        emoji_markup_prepended: str,
        node: MegaNode,
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
        # Emoji to prepend the prompt.
        self._emoji = emoji_markup_prepended
        # Label to display above input box.
        self._prompt = popup_prompt
        # The initial value to use for the input.
        self._initial = initial_input
        txt = f"{self._emoji} {self._prompt}"

        # Calculated prompt text.
        self.prompt: Text = Text.from_markup(txt)

        # Information about the node being renamed.
        self.node = node

    @override
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.prompt, id="title-label")
            yield Input(
                placeholder=self._initial or "Enter new name...",
                max_length=60,
                valid_empty=False,
                id="input-box",
                validators=[Regex("^[a-zA-Z0-9_.\\s]*")],
                validate_on=["changed", "submitted"],
                compact=True,
            )

    @on(Input.Submitted, "#input-box")
    def action_submit_rename(self) -> tuple[str, MegaNode] | None:
        if value := self.query_one(Input).value.strip():
            self.app.post_message(RenameNodeRequest(self.node, value))
        self.dismiss()

    def action_close_window(self) -> None:
        self.app.pop_screen()
