from collections import deque
from typing import TYPE_CHECKING, Any, ClassVar, Final, override

from textual import getters, log
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.reactive import Reactive, reactive
from textual.widgets import DataTable, Static
from textual.widgets._data_table import RowDoesNotExist, RowKey

from megatui.mega.data import (
    MegaTransferItem,
    MegaTransferOperationType,
    MegaTransferType,
)
from megatui.messages import TransferOperationRequest
from megatui.utils import truncate_str_lhs


class TransferTable(DataTable[Any], inherit_bindings=False):
    """Table to store and display ongoing transfers."""

    if TYPE_CHECKING:
        from megatui.app import MegaTUI

        app = getters.app(MegaTUI)

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            key="j",
            action="cursor_down",
            description="Move Cursor Down",
        ),
        Binding(
            key="k",
            action="cursor_up",
            description="Move Cursor Up",
        ),
        Binding(key="p", action="pause_transfer"),
        Binding(key="r", action="resume_transfer"),
        Binding(key="c", action="cancel_transfer"),
    ]

    MAX_FILEPATH_LEN: Final[int] = 30
    """Maximum length of a file path.
    Anything above this length will be truncated.
    """

    _transfers: dict[RowKey, MegaTransferItem]
    """Map between rowkey and transfer item."""

    def __init__(self, widget_id: str | None, classes: str | None):
        super().__init__(
            id=widget_id,
            classes=classes,
            cursor_type="row",
            show_row_labels=True,
            cell_padding=2,
            zebra_stripes=True,
        )

        self._transfers = {}

    @override
    def on_mount(self):
        # Add the columns with their headers.
        self.add_column(label="[b]Source[/]")
        self.add_column(label="[b]Destination[/]")
        self.add_column("Progress", width=None)
        self.add_column("State", width=None)

    def _get_transfer_at_rowkey(self, row_key: str) -> MegaTransferItem:
        """Return the MegaNode for a given row key string."""
        try:
            return self._transfers[RowKey(row_key)]
        except KeyError as e:
            log.error(
                f"Could not find data for row key '{row_key}'. State is inconsistent."
            )
            raise e

    def _get_curr_row_key(self) -> str | None:
        """Return RowKey for the Row that the cursor is currently on."""
        # No rows in the current view
        if not self._transfers:
            return None

        try:
            # DataTable's coordinate system is (row, column)
            # self.cursor_coordinate.row gives the visual row index
            # We need the key of that row
            row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)

            log.debug("Row key: '%s'", row_key.value)
            return row_key.value

        except RowDoesNotExist:
            log.error("Could not return any row.")
            return None

    def _get_transfer_at_cursor(self) -> MegaTransferItem | None:
        """Returns MegaItem under the current cursor.

        Returns:
        MegaItem if there is one, else None.
        """
        row_key = self._get_curr_row_key()

        # Exit if there is a nonexistent rowkey or rowkey.value
        if not row_key:
            log.info("No current item at cursor detected.")
            return None

        return self._get_transfer_at_rowkey(row_key)

    def action_pause_transfer(self):
        curr_item = self._get_transfer_at_cursor()

        if not curr_item:
            log.info("No current item detected.")
            return

        self.app.post_message(
            TransferOperationRequest(MegaTransferOperationType.PAUSE, curr_item.tag)
        )

    def action_resume_transfer(self):
        curr_item = self._get_transfer_at_cursor()

        if not curr_item:
            return

        self.app.post_message(
            TransferOperationRequest(MegaTransferOperationType.RESUME, curr_item.tag)
        )

    def action_cancel_transfer(self):
        curr_item = self._get_transfer_at_cursor()

        if not curr_item:
            return

        self.app.post_message(
            TransferOperationRequest(MegaTransferOperationType.CANCEL, curr_item.tag)
        )

    def _generate_transfer_item_row(self, item: MegaTransferItem):
        state_color = "green" if (item.state.name == "ACTIVE") else "grey"

        state = f"[{state_color}]{item.state.name}[/]"

        source_p = truncate_str_lhs(item.source_path, self.MAX_FILEPATH_LEN)

        dest_p = truncate_str_lhs(item.destination_path, self.MAX_FILEPATH_LEN)

        # Normalise progress string
        item_progress = " ".join(item.progress.split())

        return (
            source_p,
            dest_p,
            item_progress,
            state,
        )

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

        key = self.add_row(*row, height=1, label=icon, key=str(item.tag))

        self._transfers[key] = item

    def action_mark_transfer(self):
        """Mark an item in the list.
        Marked items can then be operated on.
        """
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
