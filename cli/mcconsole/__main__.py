from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from mcconsole.completer import GameCompleter
from mcconsole.discovery import find_port
from mcconsole.lexer import GameLexer, CommandTreeIndex, MCCONSOLE_STYLE
from mcconsole.protocol import GameConnection, NotConnectedError

HISTORY_FILE = Path.home() / ".mcconsole_history"
POLL_INTERVAL_SECONDS = 2.0


class Session:
    """Holds the current GameConnection (or None while disconnected) so
    the completer/lexer closures can always see the live object without
    needing to be rebuilt on every reconnect."""

    def __init__(self, minecraft_dir: Path | None):
        self.minecraft_dir = minecraft_dir
        self.connection: GameConnection | None = None
        self.tree_index = CommandTreeIndex(None)

    def get_connection(self) -> GameConnection | None:
        return self.connection

    def get_tree_index(self) -> CommandTreeIndex:
        return self.tree_index

    def try_connect(self) -> bool:
        found = find_port(self.minecraft_dir)
        if found is None:
            return False

        port, _path = found
        connection = GameConnection("127.0.0.1", port)
        try:
            connection.connect()
            connection.ping()
        except (NotConnectedError, OSError, TimeoutError):
            connection.close()
            return False

        self.connection = connection
        root = connection.tree()
        self.tree_index = CommandTreeIndex(root)
        return True

    def disconnect(self) -> None:
        if self.connection is not None:
            self.connection.close()
        self.connection = None
        self.tree_index = CommandTreeIndex(None)


def wait_for_connection(session: Session) -> None:
    print("mcconsole: waiting for a running Minecraft instance with the MCConsole mod...")
    while not session.try_connect():
        time.sleep(POLL_INTERVAL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(prog="mcconsole", description=__doc__)
    parser.add_argument(
        "--minecraft-dir",
        type=Path,
        default=None,
        help="Path to a specific .minecraft directory, if auto-discovery doesn't find yours.",
    )
    args = parser.parse_args()

    session = Session(args.minecraft_dir)
    wait_for_connection(session)

    server_label = session.connection.ping() if session.connection else "unknown"
    print(f"mcconsole: connected ({server_label})")

    prompt_style = Style.from_dict(MCCONSOLE_STYLE)
    prompt_session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=GameCompleter(session.get_connection),
        lexer=GameLexer(session.get_tree_index),
        style=prompt_style,
    )

    while True:
        try:
            text = prompt_session.prompt("mc> ")
        except (EOFError, KeyboardInterrupt):
            print("\nmcconsole: bye")
            return 0

        if not text.strip():
            continue

        if session.connection is None or not session.connection.connected:
            print("mcconsole: disconnected, reconnecting...")
            session.disconnect()
            wait_for_connection(session)
            print("mcconsole: reconnected")

        try:
            result = session.connection.execute(text)
        except NotConnectedError:
            print("mcconsole: lost connection to the game, reconnecting...")
            session.disconnect()
            wait_for_connection(session)
            print("mcconsole: reconnected — resend your command")
            continue

        color = "\033[92m" if result.success else "\033[91m"
        reset = "\033[0m"
        print(f"{color}{result.feedback}{reset}")


if __name__ == "__main__":
    sys.exit(main())
