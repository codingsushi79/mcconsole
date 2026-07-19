# mcconsole (CLI)

External terminal client for the MCConsole Fabric mod. Connects to the
mod's local socket and gives you tab-completion and syntax highlighting
for commands, driven live off whatever server/world the game is
currently connected to.

## Dev install

```
pip install -e .
mcconsole
```

## Features

- **Live chat/log tail** — chat and system messages from the game print
  straight into the terminal as they happen, not just command feedback.
- **Per-server history** — up-arrow recall is scoped to whichever server
  you're currently connected to (files under `~/.mcconsole/history/`),
  so it doesn't mix commands from unrelated servers/worlds.
- **Aliases** — define shortcuts for longer commands with client-side
  `:alias` commands (never sent to the game):
  ```
  :alias set hub warp hub          # "hub" -> "warp hub"
  :alias set tpme tp $* Sasha      # "$*" is replaced with anything typed after the alias
  :alias list
  :alias remove hub
  ```
  Stored in `~/.mcconsole/aliases.json`.

## Requirements

- Python 3.10+
- The MCConsole Fabric mod running in-game (see `../mod`)
