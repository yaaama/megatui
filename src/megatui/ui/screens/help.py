from typing import TYPE_CHECKING, ClassVar, override

from rich.table import Table
from textual.app import ComposeResult
from textual.binding import ActiveBinding, Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets._key_panel import BindingsTable

if TYPE_CHECKING:
    from megatui.app import MegaTUI


class MegaTUIBindingsTable(BindingsTable):
    """A widget to display bindings."""

    COMPONENT_CLASSES = {
        "megabindings-table--key",
        "megabindings-table--description",
        "megabindings-table--divider",
        "megabindings-table--header",
    }

    BORDER_TITLE = "Bindings"

    @override
    def render_bindings_table(self) -> Table:
        """Render a table with all the key bindings.

        Returns:
            A Rich Table.
        """
        from collections import defaultdict
        from itertools import groupby
        from operator import itemgetter

        from rich import box
        from rich.text import Text

        bindings = self.binds.values()

        key_style = self.get_component_rich_style("megabindings-table--key")
        divider_transparent = (
            self.get_component_styles("megabindings-table--divider").color.a == 0
        )
        table = Table(
            padding=(0, 0),
            show_header=False,
            box=box.SIMPLE if divider_transparent else box.HORIZONTALS,
            border_style=self.get_component_rich_style("megabindings-table--divider"),
        )
        table.add_column("", justify="right")

        header_style = self.get_component_rich_style("megabindings-table--header")
        previous_namespace: object = None
        for namespace, _bindings in groupby(bindings, key=itemgetter(0)):
            table_bindings = list(_bindings)
            if not table_bindings:
                continue

            if namespace.BINDING_GROUP_TITLE:
                title = Text(namespace.BINDING_GROUP_TITLE, end="")
                title.stylize(header_style)
                table.add_row("", title)

            action_to_bindings: defaultdict[str, list[tuple[Binding, bool, str]]]
            action_to_bindings = defaultdict(list)
            for _, binding, enabled, tooltip in table_bindings:
                if not binding.system:
                    action_to_bindings[binding.action].append((binding, enabled, tooltip))

            description_style = self.get_component_rich_style("bindings-table--description")

            def render_description(binding: Binding) -> Text:
                """Render description text from a binding."""
                text = Text.from_markup(binding.description, end="", style=description_style)
                if binding.tooltip:
                    if binding.description:
                        text.append(" ")
                    text.append(binding.tooltip, "dim")
                return text

            get_key_display = self.app.get_key_display
            for multi_bindings in action_to_bindings.values():
                binding, enabled, tooltip = multi_bindings[0]
                keys_display = " ".join(
                    dict.fromkeys(  # Remove duplicates while preserving order
                        get_key_display(binding) for binding, _, _ in multi_bindings
                    )
                )
                table.add_row(
                    Text(keys_display, style=key_style),
                    render_description(binding),
                )
            if namespace != previous_namespace:
                table.add_section()

            previous_namespace = namespace

        return table

    @override
    def render(self) -> Table:
        return self.render_bindings_table()

    def __init__(self, binds, id):
        super().__init__(id=id)
        self.binds = binds


class HelpScreen(ModalScreen[None]):
    BINDINGS: list[BindingType] = [
        Binding(key="escape", action="quit_help", show=False, priority=True),
    ]

    def action_quit_help(self) -> None:
        self.dismiss()

    def __init__(self, keys: dict[str, ActiveBinding]):
        super().__init__(name="help", id="help-screen")
        self.display_keys = keys

    @override
    def compose(self) -> ComposeResult:
        binding_table = MegaTUIBindingsTable(self.display_keys, id="megabindings-table")

        yield binding_table
