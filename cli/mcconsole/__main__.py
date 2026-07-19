from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from mcconsole.completer import GameCompleter
from mcconsole.discovery import find_port
from mcconsole.lexer import GameLexer, CommandTreeIndex, MCCONSOLE_STYLE
from mcconsole.protocol import GameConnection, NotConnectedError

HISTORY_FILE = Path.home() / ".mcconsole_history"
POLL_INTERVAL_SECONDS = 2.0
WATCH_INTERVAL_SECONDS = 3.0
PROMPT_ICON = "⛏"

PROMPT_STYLE = Style.from_dict(MCCONSOLE_STYLE)
ANSI_GREEN = "\033[92m"
ANSI_RESET = "\033[0m"


class Session:
    """Holds the current GameConnection (or None while disconnected) so
    the completer/lexer closures can always see the live object without
    needing to be rebuilt on every reconnect."""

    def __init__(self, minecraft_dir: Path | None):
        self.minecraft_dir = minecraft_dir
        self.connection: GameConnection | None = None
        self.tree_index = CommandTreeIndex(None)
        self.server_label = "mcconsole"

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
            self.server_label = connection.ping()
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


def info(text: str) -> None:
    print_formatted_text(FormattedText([("class:mcconsole.info", text)]), style=PROMPT_STYLE)


def success(text: str) -> None:
    print_formatted_text(FormattedText([("class:mcconsole.success", text)]), style=PROMPT_STYLE)


def warn(text: str) -> None:
    print_formatted_text(FormattedText([("class:mcconsole.warn", text)]), style=PROMPT_STYLE)


def wait_for_connection(session: Session) -> None:
    info(f"{PROMPT_ICON} waiting for a running Minecraft instance with the MCConsole mod...")
    while not session.try_connect():
        time.sleep(POLL_INTERVAL_SECONDS)


def build_prompt(session: Session) -> list[tuple[str, str]]:
    return [
        ("class:mcconsole.prompt.icon", f"{PROMPT_ICON} "),
        ("class:mcconsole.prompt.server", session.server_label),
        ("class:mcconsole.prompt.arrow", " ❯ "),
    ]


def _watch_for_server_changes(session: Session, connection: GameConnection) -> None:
    """Runs for the lifetime of one connection, in the background.

    The mod's socket comes up as soon as the game launches, often before
    you've joined any server, so the first ping can report "unknown".
    This notices when the connected server actually changes (joining one
    after attaching, or switching servers) and refreshes the command
    tree + prompt to match, instead of leaving them stuck on whatever was
    true at the moment mcconsole first connected.

    Uses plain print() (not print_formatted_text) since it's called from
    a background thread while a prompt may be actively running — that
    only interleaves safely with patch_stdout(), which main() wraps the
    whole session in.
    """
    while session.connection is connection and connection.connected:
        time.sleep(WATCH_INTERVAL_SECONDS)
        if session.connection is not connection or not connection.connected:
            return
        try:
            label = connection.ping()
        except NotConnectedError:
            return
        if label == session.server_label:
            continue

        session.server_label = label
        try:
            root = connection.tree()
        except NotConnectedError:
            return
        if session.connection is not connection:
            return
        session.tree_index = CommandTreeIndex(root)
        print(f"{ANSI_GREEN}{PROMPT_ICON} connected to {label}{ANSI_RESET}")


def start_watcher(session: Session) -> None:
    connection = session.connection
    if connection is None:
        return
    threading.Thread(
        target=_watch_for_server_changes,
        args=(session, connection),
        daemon=True,
        name="mcconsole-watch",
    ).start()


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
    success(f"{PROMPT_ICON} connected ({session.server_label})")
    start_watcher(session)

    prompt_session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=ThreadedCompleter(GameCompleter(session.get_connection)),
        lexer=GameLexer(session.get_tree_index),
        style=PROMPT_STYLE,
    )

    with patch_stdout():
        while True:
            try:
                text = prompt_session.prompt(lambda: build_prompt(session))
            except (EOFError, KeyboardInterrupt):
                print_formatted_text(
                    FormattedText([("class:mcconsole.info", "\nmcconsole: bye")]), style=PROMPT_STYLE
                )
                return 0

            if not text.strip():
                continue

            if session.connection is None or not session.connection.connected:
                warn(f"{PROMPT_ICON} disconnected, reconnecting...")
                session.disconnect()
                wait_for_connection(session)
                success(f"{PROMPT_ICON} reconnected ({session.server_label})")
                start_watcher(session)

            try:
                result = session.connection.execute(text)
            except NotConnectedError:
                warn(f"{PROMPT_ICON} lost connection to the game, reconnecting...")
                session.disconnect()
                wait_for_connection(session)
                success(f"{PROMPT_ICON} reconnected ({session.server_label}) — resend your command")
                start_watcher(session)
                continue

            style_class = "class:mcconsole.success" if result.success else "class:mcconsole.error"
            print_formatted_text(FormattedText([(style_class, result.feedback)]), style=PROMPT_STYLE)


if __name__ == "__main__":
    sys.exit(main())
