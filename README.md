# MCConsole

An external terminal for Minecraft: a Fabric client mod exposes a local
socket, and a companion CLI (`mcconsole`) connects to it from a normal
terminal window, giving you command execution, tab-completion, and
syntax highlighting driven live off whatever server/world your game is
currently connected to.

```
mod/         Fabric client-side mod (Java, Gradle)
cli/         mcconsole terminal client (Python, prompt_toolkit)
scripts/     build_installer.py — bundles cli/ into a single-file installer
install.fezi ezinstaller script for installing the CLI
```

## How it fits together

1. The mod starts a loopback-only (`127.0.0.1`) TCP socket when the game
   launches, and writes the port it picked to
   `.minecraft/config/mcconsole/port.json`.
2. `mcconsole` (the CLI) reads that file to find the port, connects, and
   sends/receives newline-delimited JSON messages (`ping`, `execute`,
   `complete`, `tree`).
3. Commands you type in the terminal get sent to the game and executed
   as if typed in chat; completion and highlighting are driven by
   Brigadier's own command dispatcher, so they always match whatever
   server you're actually connected to.

See `mod/src/main/java/dev/sushii/mcconsole/CommandBridge.java` for the
exact protocol if you want to build another client against it.

## Building the mod

```
cd mod
./gradlew build
```

(`gradle/wrapper/gradle-wrapper.jar` is already committed; see
`mod/BUILD_NOTES.md` if you ever need to regenerate it.)

Output jar lands in `mod/build/libs/`. Drop it into your Fabric `mods`
folder (alongside Fabric API) and launch the game once.

**Before your first real build**, check `mod/gradle.properties` against
whatever's current on https://fabricmc.net/develop (or `meta.fabricmc.net`
directly — the marketing page itself doesn't expose raw version numbers) —
Minecraft version, mappings, Loader, and Fabric API versions all move
fast, and the values committed here will go stale.

**Mappings note:** this currently targets Minecraft 26.2, which as of
2026-07-19 has no Yarn or Mojang mappings published at all — its client
jar ships unobfuscated, so `build.gradle` generates a trivial identity
mapping instead of fetching one. `CommandBridge.java` uses the real
(unobfuscated) class/method names for 26.2. Full story, including what to
do once real mappings exist for whatever version you're building against,
in `mod/BUILD_NOTES.md`.

This mod targets **Java 25** (Minecraft's current toolchain requirement)
and needs a Gradle version whose plugin API satisfies whatever
`fabric-loom` version is current (see `mod/gradle/wrapper/gradle-wrapper.properties`
and `mod/BUILD_NOTES.md` for what that resolved to most recently). Loom
also requires the JVM running Gradle itself to be Java 25+ — if your
default `java` is older, set `JAVA_HOME` before building (see
`mod/BUILD_NOTES.md`).

The mod has been build-verified (`./gradlew build` succeeds and produces
a jar) **and** live-tested against a real Fabric install (Prism Launcher):
it now loads without crashing. `ping`/tab-completion/syntax highlighting
against real commands (`/gamemode`, `/give`, `/tp`) still need a manual
end-to-end pass with the CLI attached — see "Live-game testing" below.

### Live-game testing

1. Build the jar (above), drop it and a matching Fabric API build into a
   real `.minecraft/mods` folder, and launch the game once.
2. Confirm `.minecraft/config/mcconsole/port.json` gets written.
3. Run the CLI (`cd cli && pip install -e . && mcconsole`) and verify
   `ping` connects, tab-completion and syntax highlighting work, and
   `/gamemode`, `/give`, and `/tp` execute with correct feedback.

## Running the CLI (dev)

```
cd cli
pip install -e .
mcconsole
```

`mcconsole` polls for `.minecraft/config/mcconsole/port.json` on
startup (and again if the game closes mid-session), auto-detecting
common `.minecraft` locations on Windows/macOS/Linux. Use
`--minecraft-dir` if your instance lives somewhere nonstandard (e.g. a
Prism/MultiMC instance folder).

The CLI half of this project has been test-run in isolation (packaging,
imports, and the full JSON wire protocol against a mock server) — see
`cli/` for the source. The mod half now builds and has loaded
successfully in a real Fabric install; a full CLI-attached pass against
a live game (tab-completion, syntax highlighting, real command feedback)
is still open — see "Live-game testing" above.

## Installing the CLI via ezinstaller

Once this repo is live at `github.com/codingsushi79/mcconsole`:

```
curl -fsSL https://raw.githubusercontent.com/codingsushi79/ezinstaller/main/ezi.py \
  | python3 - https://raw.githubusercontent.com/codingsushi79/mcconsole/main/install.fezi
```

Until then, test locally from the repo root:

```
ezi install.fezi --dry-run
ezi install.fezi
```

The installer only handles the CLI — you still need to build the mod
jar (or grab it from a release once one exists) and drop it into your
`mods` folder yourself; `install.fezi` prints a reminder about this at
the end of the run.

## Single-file CLI installer

`scripts/build_installer.py` bundles the whole `cli/mcconsole` package
plus `pyproject.toml` into one standalone script, `mcconsole-installer.py`
(base64-encoded zip embedded in a small bootstrap, same idea as
ezinstaller's own `ezi.py`):

```
python3 scripts/build_installer.py
python3 mcconsole-installer.py [install_dir]
```

It creates a venv under the install directory (default `~/apps/mcconsole`),
installs `prompt_toolkit` and the CLI into it, and either appends the venv's
`bin/` to your shell profile's `PATH` or prints the `export` line to add
yourself. `mcconsole-installer.py` is a generated artifact (gitignored) —
regenerate it after any `cli/` change.

## Release workflows

Two GitHub Actions workflows run on a `v*` tag push (or manual
`workflow_dispatch` with a `tag` input) and publish to the same GitHub
Release for that tag:

- `.github/workflows/mod-release.yml` — builds the mod with JDK 25 and
  attaches the jars from `mod/build/libs/`.
- `.github/workflows/cli-installer-release.yml` — regenerates
  `mcconsole-installer.py` via `scripts/build_installer.py` and attaches it.

Both have only been validated locally (YAML syntax + `actionlint`, and the
underlying `gradle build` / `build_installer.py` commands run directly) —
actually triggering them requires a real GitHub repo and a pushed tag,
which hasn't been done.

## Security note

The mod's socket only binds to `127.0.0.1` and isn't authenticated
beyond that. Anything else running as your user on the same machine can
also connect and execute commands as you — that's an acceptable trust
boundary for a local dev tool, but don't widen the bind address without
adding real auth first.
