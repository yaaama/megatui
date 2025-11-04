from rich.text import Text
from textual.binding import Binding
from textual.containers import Center, CenterMiddle, Vertical, VerticalGroup
from textual.screen import ModalScreen, Screen
from textual.widgets import Rule, Static

from megatui.mega.data import MegaMediaInfo


class PreviewMediaInfoModal(ModalScreen[None]):
    ESCAPE_TO_MINIMIZE = True
    BORDER_TITLE = "Media Information"

    BINDINGS = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="q", action="app.pop_screen", show=False, priority=True),
    ]

    def __init__(self, media_info: MegaMediaInfo):
        self.media_info = media_info
        super().__init__()

    def on_mount(self):
        self.query_one("#media_info_panel").border_title = "Media Info"

    def compose(self):
        with Vertical(id="media_info_panel"):
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
