from collections import deque
from typing import Any, Final, override

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import Reactive, reactive
from textual.widgets import DataTable, Static

from megatui.mega.data import MegaTransferItem, MegaTransferType


class TransferTable(DataTable[Any], inherit_bindings=False):
    """Table to store and display ongoing transfers."""

    def __init__(self, widget_id: str | None, classes: str | None):
        super().__init__(id=widget_id, classes=classes)

    @override
    def on_mount(self):
        # Add the columns with their headers.
        self.add_columns("Source", "Destination", "Progress", "State")


class TransfersSidePanel(Vertical):
    """Toggleable panel containing transfer information in a `TransferTable`."""

    MAX_FILEPATH_LEN: Final[int] = 20
    """Maximum length of a file path.
    Anything above this length will be truncated.
    """

    transfer_list: Reactive[deque[MegaTransferItem] | None] = reactive(None)

    def __init__(self, widget_id: str) -> None:
        super().__init__(id=widget_id)

    @override
    def compose(self) -> ComposeResult:
        self.border_title = "Transfers"
        yield Static(
            "[i]There are no transfers to show.[/i]", id="no-transfers-message"
        )

        # Starts off hidden
        table = TransferTable(widget_id="transfer-table", classes="-hidden")
        yield table

    def watch_transfer_list(
        self,
        old_list: deque[MegaTransferItem] | None,  # pyright: ignore[reportUnusedParameter]
        new_list: deque[MegaTransferItem] | None,
    ) -> None:
        # Find the Static widget we created in compose()
        table: TransferTable = self.query_one("#transfer-table", TransferTable)
        message = self.query_one("#no-transfers-message")

        table.clear()

        if not new_list:
            self.border_title = "Transfers [0]"
            # Show the message and hide the table
            message.remove_class("-hidden")
            table.add_class("-hidden")
            return

        self.border_title = f"Transfers [{len(new_list)}]"
        # Hide the message and show the table
        message.add_class("-hidden")
        table.remove_class("-hidden")

        base_icon = "[yellow]...[/]"
        # Add each transfer as a new row to the table
        for item in new_list:
            # Use Rich markup for styling within cells
            match item.type:
                case MegaTransferType.DOWNLOAD:
                    icon = "[blue]▼[/]"
                case MegaTransferType.UPLOAD:
                    icon = "[green]▲[/]"
                case _:
                    icon = base_icon

            state_color = "green" if (item.state.name == "ACTIVE") else "grey"

            state = f"[{state_color}]{item.state.name}[/]"

            if len(item.source_path) >= self.MAX_FILEPATH_LEN:
                chars_to_keep = self.MAX_FILEPATH_LEN - 1
                source_p = "…" + item.source_path[-chars_to_keep:]
            else:
                source_p = item.source_path

            if len(item.destination_path) >= self.MAX_FILEPATH_LEN:
                chars_to_keep = self.MAX_FILEPATH_LEN - 1
                dest_p = "…" + item.destination_path[-chars_to_keep:]
            else:
                dest_p = item.destination_path

            table.add_row(
                dest_p, source_p, item.progress.strip(), state, height=1, label=icon
            )
