"""Client-side command aliases/macros.

Aliases are expanded locally before a line ever reaches the game, and are
managed with `:alias` commands typed at the mcconsole prompt (see
handle_local_command in __main__.py) — never sent to the game itself.
Stored as a flat name -> expansion mapping in ~/.mcconsole/aliases.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ALIASES_FILE = Path.home() / ".mcconsole" / "aliases.json"


def load_aliases() -> dict[str, str]:
    try:
        return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_aliases(aliases: dict[str, str]) -> None:
    ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALIASES_FILE.write_text(json.dumps(aliases, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def expand(text: str, aliases: dict[str, str]) -> str:
    """Expands a leading alias name in `text`, if any; text with no
    matching alias is returned unchanged.

    An expansion containing `$*` has it replaced with whatever the user
    typed after the alias name. Otherwise, that extra text is appended,
    the same way `git alias.foo` handles trailing arguments.
    """
    name, _, rest = text.partition(" ")
    expansion = aliases.get(name)
    if expansion is None:
        return text
    if "$*" in expansion:
        return expansion.replace("$*", rest)
    return f"{expansion} {rest}".rstrip() if rest else expansion
