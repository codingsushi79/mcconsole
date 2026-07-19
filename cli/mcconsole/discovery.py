"""Finds the running game's MCConsole socket port.

The Fabric mod writes `.minecraft/config/mcconsole/port.json` on startup.
This module knows the default `.minecraft` locations for each OS so the
CLI can find it without any manual configuration, but also lets the user
override the path via `--minecraft-dir` or the `MCCONSOLE_MC_DIR` env var.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path


def _launcher_data_roots() -> list[Path]:
    """Return likely install/data directories for Prism Launcher and
    MultiMC, whose instances each get their own game directory rather
    than sharing one `.minecraft` like the vanilla launcher."""

    home = Path.home()
    system = platform.system()

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return []
        base = Path(appdata)
        return [base / "PrismLauncher", base / "MultiMC"]
    elif system == "Darwin":
        base = home / "Library" / "Application Support"
        return [base / "PrismLauncher", base / "MultiMC"]
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", "") or (home / ".local" / "share"))
        return [
            data_home / "PrismLauncher",
            data_home / "multimc",
            data_home / "MultiMC",
        ]


def _instance_minecraft_dirs() -> list[Path]:
    """Glob every instance under known Prism/MultiMC-style launcher roots
    for its actual game directory (named `minecraft` or `.minecraft`
    depending on the launcher version)."""

    dirs: list[Path] = []
    for root in _launcher_data_roots():
        instances_dir = root / "instances"
        if not instances_dir.is_dir():
            continue
        try:
            instances = sorted(instances_dir.iterdir())
        except OSError:
            continue
        for instance in instances:
            if not instance.is_dir():
                continue
            for name in ("minecraft", ".minecraft"):
                candidate = instance / name
                if candidate.is_dir():
                    dirs.append(candidate)
    return dirs


def default_minecraft_dirs() -> list[Path]:
    """Return likely `.minecraft` locations for the current OS, in
    priority order: the vanilla launcher's default profile first, then
    every instance found under Prism Launcher / MultiMC's data
    directories, since a lot of people aren't running the vanilla
    launcher's default profile."""

    home = Path.home()
    system = platform.system()

    candidates: list[Path] = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / ".minecraft")
    elif system == "Darwin":
        candidates.append(home / "Library" / "Application Support" / "minecraft")
    else:
        candidates.append(home / ".minecraft")

    # Always also check a plain ~/.minecraft as a fallback, some Linux
    # launchers and Windows portable installs use it directly.
    candidates.append(home / ".minecraft")

    candidates.extend(_instance_minecraft_dirs())

    seen: set[Path] = set()
    unique: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def port_file_candidates(minecraft_dir: Path | None = None) -> list[Path]:
    if minecraft_dir is not None:
        return [minecraft_dir / "config" / "mcconsole" / "port.json"]

    override = os.environ.get("MCCONSOLE_MC_DIR")
    if override:
        return [Path(override) / "config" / "mcconsole" / "port.json"]

    return [d / "config" / "mcconsole" / "port.json" for d in default_minecraft_dirs()]


def find_port(minecraft_dir: Path | None = None) -> tuple[int, Path] | None:
    """Returns (port, path_used) for the first readable, valid port.json
    found, or None if the game doesn't appear to be running with the mod
    loaded yet."""

    for candidate in port_file_candidates(minecraft_dir):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            port = int(data["port"])
            return port, candidate
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            continue

    return None
