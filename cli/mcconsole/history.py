"""Per-server command history files.

One history file per connected server, so pressing up-arrow on your
survival server doesn't dredge up commands from the creative flat-world
you were just testing something in.
"""

from __future__ import annotations

import re
from pathlib import Path

from prompt_toolkit.history import FileHistory

HISTORY_DIR = Path.home() / ".mcconsole" / "history"


def history_for(server_label: str) -> FileHistory:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", server_label).strip("_") or "unknown"
    return FileHistory(str(HISTORY_DIR / f"{safe}.history"))
