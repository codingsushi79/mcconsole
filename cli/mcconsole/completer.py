from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from mcconsole.protocol import GameConnection, NotConnectedError


class GameCompleter(Completer):
    """Delegates tab-completion to the mod's Brigadier dispatcher.

    Brigadier suggestions already come back with the exact [start, end)
    character range they replace, so this maps directly onto
    prompt_toolkit's start_position semantics rather than needing any
    prefix-guessing on our side.
    """

    def __init__(self, connection_holder):
        # connection_holder is a zero-arg callable returning the current
        # GameConnection (or None), so this stays usable across reconnects.
        self._connection_holder = connection_holder

    def get_completions(self, document: Document, complete_event):
        connection: GameConnection | None = self._connection_holder()
        if connection is None or not connection.connected:
            return

        text = document.text_before_cursor
        try:
            suggestions = connection.complete(text)
        except NotConnectedError:
            return

        cursor_pos = len(text)
        for suggestion in suggestions:
            start_position = suggestion.start - cursor_pos
            yield Completion(suggestion.text, start_position=start_position)
