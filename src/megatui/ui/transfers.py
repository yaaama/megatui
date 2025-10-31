from collections import deque
import string
from textwrap import wrap
import textwrap
from typing import Any, override

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import Reactive, reactive
from textual.widget import Widget
from textual.widgets import DataTable, Log, RichLog, Static

from megatui.mega.megacmd import MegaTransferItem, MegaTransferType


class TransfersSidePanel(Vertical):
    DEFAULT_CSS = """
    """

    transfer_list: Reactive[deque[MegaTransferItem] | None] = reactive(None)

    def __init__(self, **kwargs) -> None:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        super().__init__(id="transfer-sidepanel")  # pyright: ignore[reportUnknownArgumentType]

    @override
    def compose(self) -> ComposeResult:
        self.border_title = "Transfers"
        yield Static(
            "[i]There are no transfers to show.[/i]", id="no-transfers-message"
        )

        # Starts off hidden
        yield DataTable(id="transfer-table", classes="-hidden")

    def on_mount(self) -> None:
        table: DataTable[Any] = self.query_one(DataTable)  # pyright: ignore[reportUndefinedVariable]
        # Add the columns with their headers.
        table.add_columns("Source", "Destination", "Progress", "State")

    def watch_transfer_list(
        self,
        old_list: deque[MegaTransferItem] | None,
        new_list: deque[MegaTransferItem] | None,
    ) -> None:
        # Find the Static widget we created in compose()
        table = self.query_one(DataTable)
        message = self.query_one("#no-transfers-message")

        table.clear()

        if not new_list:
            self.border_title = "Transfers [0]"
            # Show the message and hide the table
            message.remove_class("-hidden")
            table.add_class("-hidden")

        else:
            self.border_title = f"Transfers [{len(new_list)}]"
            # Hide the message and show the table
            message.add_class("-hidden")
            table.remove_class("-hidden")

            # Add each transfer as a new row to the table
            for item in new_list:
                # Use Rich markup for styling within cells

                if item.type == MegaTransferType.DOWNLOAD:
                    icon = "[blue]▼[/]"

                elif item.type == MegaTransferType.UPLOAD:
                    icon = "[green]▲[/]"
                else:
                    icon = "[yellow]...[/]"

                state_color = "green" if item.state == "ACTIVE" else "grey"

                state = f"[{state_color}]{item.state.name}[/]"

                if len(item.source_path) >= 20:
                    chars_to_keep = 20 - 1
                    source_p = "…" + item.source_path[-chars_to_keep:]
                else:
                    source_p = item.source_path

                if len(item.destination_path) >= 20:
                    chars_to_keep = 20 - 1
                    dest_p = "…" + item.destination_path[-chars_to_keep:]
                else:
                    dest_p = item.destination_path

                table.add_row(
                    dest_p, source_p, item.progress.strip(), state, height=1, label=icon
                )

    def _generate_rich_table(self):
        pass
