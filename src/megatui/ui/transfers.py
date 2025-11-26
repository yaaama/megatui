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
        super().__init__(
            id=widget_id, classes=classes, cursor_type="row", show_row_labels=True
        )

    @override
    def on_mount(self):
        # Add the columns with their headers.
        self.add_columns("Source", "Destination", "Progress", "State")

    MAX_FILEPATH_LEN: Final[int] = 20
    """Maximum length of a file path.
    Anything above this length will be truncated.
    """

    def _generate_transfer_item_row(self, item: MegaTransferItem):
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

        return (source_p, dest_p, item.progress.strip(), state)

    def add_transfer_item(self, item: MegaTransferItem):
        base_icon = "[yellow]...[/]"
        match item.type:
            case MegaTransferType.DOWNLOAD:
                icon = "[blue]▼[/]"
            case MegaTransferType.UPLOAD:
                icon = "[green]▲[/]"
            case _:
                icon = base_icon

        row = self._generate_transfer_item_row(item)

        self.add_row(*row, height=1, label=icon)

    def action_mark_transfer(self):
        """Mark an item in the list.
        Marked items can then be operated on.
        """
        pass

    def action_cancel_transfer(self):
        """Cancel a transfer."""
        pass

    def action_pause_transfer(self):
        """Pause a transfer."""
        pass

    def action_resume_transfer(self):
        """Resume a transfer from a paused state."""
        pass

    def action_toggle_pause_transfer(self):
        """Toggle the pause status of a transfer."""
        pass

    def action_clear_finished_transfers(self):
        """Clear all transfers that have finished from the table."""
        pass

    def action_show_uploads(self):
        """Only show uploads in the table."""
        pass

    def action_show_downloads(self):
        """Only show downloads in the table."""
        pass

    def action_sort_by_size(self):
        """Sort transfers by their size."""
        pass

    def action_sort_by_tag(self):
        """Sort transfers by their tag."""
        pass

    def action_sort_by_completion(self):
        """Sort transfers by completion."""
        pass


class TransfersSidePanel(Vertical):
    """Toggleable panel containing transfer information in a `TransferTable`."""

    transfer_list: Reactive[deque[MegaTransferItem] | None] = reactive(None)

    def __init__(self, widget_id: str) -> None:
        super().__init__(id=widget_id)

    @override
    def compose(self) -> ComposeResult:
        self.border_title = "Transfers"
        # Default message we toggle on and off
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

        # Add each transfer as a new row to the table
        for item in new_list:
            table.add_transfer_item(item)
