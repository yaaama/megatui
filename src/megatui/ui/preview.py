from typing import TYPE_CHECKING, override

from textual import getters
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from megatui.mega.data import MegaMediaInfo


class PreviewMediaInfoModal(ModalScreen[None]):
    ESCAPE_TO_MINIMIZE = True
    BORDER_TITLE = "Media Information"

    if TYPE_CHECKING:
        from megatui.app import MegaTUI

        app = getters.app(MegaTUI)

    BINDINGS = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="q", action="app.pop_screen", show=False, priority=True),
    ]

    def __init__(self, media_info: MegaMediaInfo):
        self.media_info = media_info
        super().__init__()

    def on_mount(self):
        self.query_one("#media-info-panel").border_title = "Media Info"

    def on_key(self, key: Key):
        name = key.name
        if name == "escape" or name == "q" or name == "i":
            key.stop()
            self.app.pop_screen()
        else:
            # Handle what is done with other keys
            pass

    @override
    def compose(self):
        with Vertical(id="media-info-panel"):
            yield Static(
                content=f"[b]Media Title:[/b][i] '{self.media_info.fname}'[/]",
                id="title",
            )
            yield Static(content=f"[b]FPS:[/b][i] '{self.media_info.fps}'[/]", id="fps")
            yield Static(
                content=f"[b]Resolution:[/b][i] '{self.media_info.resolution}'[/]",
                id="resolution",
            )
            yield Static(
                content=f"[b]Playtime:[/b][i] '{self.media_info.playtime}'[/]",
                id="playtime",
            )
