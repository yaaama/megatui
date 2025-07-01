"""Account information screen."""

from typing import override

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Header, Label, RichLog


# TODO Finish this
class AccountInformationScreen(ModalScreen[None]):
    """Screen to display cloud storage account information."""

    @override
    def compose(self) -> ComposeResult:
        with Vertical() as vs:
            vs.can_focus = False
            yield Header(show_clock=False, id="account-info-header")
            yield Label("This is a helpful screen of information.")

        pass
