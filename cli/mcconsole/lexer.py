from __future__ import annotations

from typing import Any

from prompt_toolkit.lexers import Lexer
from prompt_toolkit.document import Document

STYLE_LITERAL = "class:mcconsole.literal"
STYLE_ARGUMENT = "class:mcconsole.argument"
STYLE_ERROR = "class:mcconsole.error"
STYLE_SLASH = "class:mcconsole.slash"

MCCONSOLE_STYLE = {
    "mcconsole.literal": "fg:#59d9a5 bold",
    "mcconsole.argument": "fg:#e8c15e",
    "mcconsole.error": "fg:#ff6b6b",
    "mcconsole.slash": "fg:#888888",
    # Prompt
    "mcconsole.prompt.icon": "fg:#59d9a5 bold",
    "mcconsole.prompt.server": "fg:#e8c15e bold",
    "mcconsole.prompt.arrow": "fg:#59d9a5",
    # Status lines (connecting/reconnecting/etc.)
    "mcconsole.info": "fg:#7aa2f7",
    "mcconsole.success": "fg:#59d9a5 bold",
    "mcconsole.warn": "fg:#e8c15e",
}


class CommandTreeIndex:
    """Wraps the JSON command tree dumped by the mod so we can classify
    tokens locally, without round-tripping to the game on every
    keystroke. Rebuilt whenever a fresh `tree` response comes in
    (typically once per connection)."""

    def __init__(self, root: dict[str, Any] | None):
        self._root = root

    @property
    def available(self) -> bool:
        return self._root is not None

    def classify(self, tokens: list[str]) -> list[str]:
        """Returns a style name per token: literal / argument / error."""
        if self._root is None:
            return [STYLE_ARGUMENT for _ in tokens]

        styles: list[str] = []
        node = self._root
        fell_off_tree = False

        for token in tokens:
            if fell_off_tree:
                styles.append(STYLE_ERROR)
                continue

            children = node.get("children", [])
            literal_match = next(
                (c for c in children if c.get("kind") == "literal" and c.get("name") == token),
                None,
            )
            argument_child = next((c for c in children if c.get("kind") == "argument"), None)

            if literal_match is not None:
                styles.append(STYLE_LITERAL)
                node = literal_match
            elif argument_child is not None:
                # Brigadier argument types vary too much to validate
                # client-side without duplicating a lot of parsing logic,
                # so we optimistically highlight it as an argument and
                # keep walking from that node.
                styles.append(STYLE_ARGUMENT)
                node = argument_child
            else:
                styles.append(STYLE_ERROR)
                fell_off_tree = True

        return styles


class GameLexer(Lexer):
    """prompt_toolkit Lexer driven by a CommandTreeIndex. Only re-derives
    styling locally from cached tree data — see CommandTreeIndex for the
    actual classification logic."""

    def __init__(self, tree_index_holder):
        # zero-arg callable returning the current CommandTreeIndex, so a
        # fresh tree (e.g. after reconnecting to a different server with
        # different commands) is picked up automatically.
        self._tree_index_holder = tree_index_holder

    def lex_document(self, document: Document):
        def get_line(lineno: int):
            line = document.lines[lineno]
            return self._tokenize_line(line)

        return get_line

    def _tokenize_line(self, line: str) -> list[tuple[str, str]]:
        if line.startswith(":"):
            # Client-side local command (":alias ..."), never sent to the
            # game and not part of its command tree — don't try to
            # classify it against Brigadier, just dim the whole line.
            return [(STYLE_SLASH, line)]

        result: list[tuple[str, str]] = []

        working = line
        if working.startswith("/"):
            result.append((STYLE_SLASH, "/"))
            working = working[1:]

        if not working:
            return result

        root = self._get_root()
        index = CommandTreeIndex(root)
        parts = working.split(" ")
        tokens = [p for p in parts if p != ""]
        styles = index.classify(tokens)

        token_iter = iter(styles)
        current_style = next(token_iter, None)

        buffer = ""
        for ch in working:
            if ch == " ":
                if buffer:
                    result.append((current_style or STYLE_ARGUMENT, buffer))
                    buffer = ""
                    current_style = next(token_iter, None)
                result.append(("", " "))
            else:
                buffer += ch
        if buffer:
            result.append((current_style or STYLE_ARGUMENT, buffer))

        return result

    def _get_root(self) -> dict[str, Any] | None:
        tree_index = self._tree_index_holder()
        return tree_index._root if tree_index is not None else None
