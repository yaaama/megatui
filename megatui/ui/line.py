from typing import override

from rich.segment import Segment
from textual.strip import Strip
from textual.widget import Widget


class FileListRow(Widget):
    COMPONENT_CLASSES = {
        "fvitem--icon",
        "fvitem--name",
        "fvitem--fsize",
        "fvitem--mtime",
        "fvitem--selected",
    }
    DEFAULT_CSS = """
    .fvitem--icon {
        color: cyan;
    }
    .fvitem--name {
        color: white;
        font-weight: bold;
    }
    .fvitem--fsize {
        color: magenta;
        text-align: right;
    }
    .fvitem--mtime {
        color: grey;
    }
    """

    selected: bool

    def __init__(
        self,
        icon: str,
        fname: str,
        fsize: str,
        mtime: str,
        handle: str,
        selected: bool = False,
    ):
        super().__init__()
        self.icon: str = icon
        self.fname: str = fname
        self.fsize: str = fsize
        self.mtime: str = mtime
        self.handle: str = handle
        self.selected = selected

    @override
    def render_line(self, y: int) -> Strip:
        cells = [
            # Segment(icon_text, style=self.get_component_rich_style("fvitem--icon")),
            Segment(self.fname, style=self.get_component_rich_style("fvitem--name")),
            Segment(self.fsize, style=self.get_component_rich_style("fvitem--fsize")),
            Segment(self.mtime, style=self.get_component_rich_style("fvitem--mtime")),
        ]

        icon_text: str

        if self.selected:
            icon_text = f"{self.icon}'*'"
            cells.insert(
                0,
                Segment(icon_text, style=self.get_component_rich_style("fvitem--icon")),
            )
        else:
            icon_text = f"{self.icon}"
            cells.insert(
                0,
                Segment(
                    f"{icon_text}", style=self.get_component_rich_style("fvitem--icon")
                ),
            )

        return Strip(cells)
