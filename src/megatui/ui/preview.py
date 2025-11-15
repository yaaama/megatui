from typing import TYPE_CHECKING, ClassVar, override

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

    COMPONENT_CLASSES: ClassVar[set[str]] = {
        "mediainfo--fname",
        "mediainfo--resolution",
        "mediainfo--playtime",
    }

    if TYPE_CHECKING:
        from megatui.app import MegaTUI

        app = getters.app(MegaTUI)

    BINDINGS = [
        Binding(key="escape", action="app.pop_screen", show=False, priority=True),
        Binding(key="q", action="app.pop_screen", show=False, priority=True),
    ]

    def __init__(self, media_info: MegaMediaInfo | tuple[MegaMediaInfo]):
        if isinstance(media_info, tuple):
            self.media_info = media_info[0]
        else:
            self.media_info = media_info
        super().__init__()

    def on_mount(self):
        container = self.query_one("#media-info-panel")
        container.border_title = "Media Info"

    def on_key(self, key: Key):
        name = key.name
        if name in {"escape", "q", "i"}:
            key.stop()
            self.app.pop_screen()
        else:
            # Handle what is done with other keys
            pass

    def _fname_text(self):
        path_segments = self.media_info.path.split("/")
        segment_count = len(path_segments)

        name_segment = f"[red]{path_segments[segment_count - 1]}[/red]"

        if segment_count < 3:
            return f"[red]/[/red][dim][yellow]{name_segment}[/yellow][/dim]"

        parent_segment = (
            f"[orange][dim]{path_segments[segment_count - 2]}[/orange][/dim]"
        )

        text = f"/{parent_segment}/{name_segment}"
        return text

    def _resolution_text(self):
        pass

    @override
    def compose(self):
        fname_label = f"[b]Media Title:[/b][i] {self._fname_text()}[/i]"

        with Vertical(id="media-info-panel"):
            yield Static(content=fname_label, id="title", markup=True)
            yield Static(content=f"[b]FPS:[/b][i] '{self.media_info.fps}'[/]", id="fps")
            yield Static(
                content=f"[b]Resolution:[/b][i] '{self.media_info.resolution}'[/]",
                id="resolution",
            )
            yield Static(
                content=f"[b]Playtime:[/b][i] '{self.media_info.playtime}'[/]",
                id="playtime",
            )
