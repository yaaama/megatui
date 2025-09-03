from typing import override

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import HelpPanel, KeyPanel


class HelpScreen(ModalScreen[None]):
    DEFAULT_CSS = """
        HelpPanel {
                # split: right;
                width: 33%;
                min-width: 30;
                max-width: 60;
                # border-left: vkey $foreground 30%;
                padding: 0 1;
                height: 80%;
                # padding: 1;
                layout: vertical;
                # height: 100%;

                #widget-help {
                height: auto;
                max-height: 50%;
                width: 1fr;
                padding: 0;
                margin: 0;
                padding: 1 0;
                margin-top: 1;
                display: none;
                background: $panel;

                MarkdownBlock {
                        padding-left: 2;
                        padding-right: 2;
                }
                }

                &.-show-help #widget-help {
                display: block;
                }

                KeyPanel#keys-help {
                width: 1fr;
                height: 1fr;
                min-width: initial;
                split: initial;
                border-left: none;
                padding: 0;
                }
        }
        """

    def __init__(self, keys):
        super().__init__()
        self._keys = keys
        self.screen._bindings = keys

    @override
    def compose(self) -> ComposeResult:
        yield KeyPanel()
