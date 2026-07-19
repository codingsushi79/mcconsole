from __future__ import annotations

import itertools
import threading
import time

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from mcconsole.protocol import GameConnection, NotConnectedError

# Every completion request is a full round trip to the game, and briefly
# occupies its render thread while it computes suggestions. Firing one on
# every keystroke made fast typing (especially on long/complex commands)
# visibly stall the game. Debouncing means a request only actually goes
# out after a short pause in typing; get_completions is expected to run
# on a background thread (see ThreadedCompleter in __main__.py) since it
# blocks for the debounce delay plus the network round trip.
DEBOUNCE_SECONDS = 0.12


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
        self._generation = itertools.count()
        self._latest = -1
        self._generation_lock = threading.Lock()

    def get_completions(self, document: Document, complete_event):
        with self._generation_lock:
            my_id = next(self._generation)
            self._latest = my_id

        time.sleep(DEBOUNCE_SECONDS)
        if self._latest != my_id:
            return  # superseded by newer input while we were waiting

        connection: GameConnection | None = self._connection_holder()
        if connection is None or not connection.connected:
            return

        text = document.text_before_cursor
        try:
            suggestions = connection.complete(text)
        except NotConnectedError:
            return

        if self._latest != my_id:
            return  # superseded while the request was in flight

        cursor_pos = len(text)
        for suggestion in suggestions:
            start_position = suggestion.start - cursor_pos
            yield Completion(suggestion.text, start_position=start_position)
