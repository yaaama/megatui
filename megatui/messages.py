# Global Messages
#
from textual.message import Message
from rich.text import Text


class UpdateStatusMsg(Message):
    """
    Message for a widget to update status bar.
    """

    def __init__(self, message : str) -> None:
        super().__init__()
        self.message = message
