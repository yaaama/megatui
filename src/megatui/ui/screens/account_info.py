"""Account information screen."""

from typing import override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Header, Label

from megatui.mega.megacmd import MegaDiskFree


# TODO Finish this
class AccountInformationScreen(ModalScreen[None]):
    """Screen to display cloud storage account information."""

    BINDINGS = (
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
    )

    def __init__(
        self, df_data: MegaDiskFree, pwd: str, whoami: str, mount: str, speedlimits: str
    ):
        super().__init__()

        self._df_data: MegaDiskFree = df_data
        self._pwd: str = pwd
        self._whoami: str = whoami
        self._mount: str = mount
        self._speedlimits: str = speedlimits

    @override
    def compose(self) -> ComposeResult:
        with Vertical() as vs:
            vs.can_focus = False
            yield Header(show_clock=False, id="account-info-header")
            yield Label("This is a helpful screen of information.")
        pass
