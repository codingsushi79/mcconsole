# Build notes

Status as of 2026-07-19: the mod builds cleanly with `./gradlew build`
against **Minecraft 26.2**, and has been smoke-tested against a real,
live Fabric install (Prism Launcher, real account) — it loads, `ping`
should work, and the wire protocol is unchanged from the 1.21.11 build.
See "What changed to get here" below for the full story, since it was
not a simple version bump.

## Minecraft 26.2 has no obfuscation, and no mappings

Minecraft's release train has moved to a `26.x` (year-based) versioning
scheme. As of this writing, **Fabric's modding toolchain has no Yarn
mappings and Mojang publishes no `client_mappings` for any `26.x`
release** — checked directly against `meta.fabricmc.net` and
`piston-meta.mojang.com`, not just the fabricmc.net marketing page.

The reason turns out to be that there's nothing to map: the 26.2 client
jar ships **unobfuscated**, with real class/method names already baked
in (confirmed both by inspecting the jar directly — `net.minecraft.client.Minecraft`,
`net.minecraft.client.multiplayer.ClientPacketListener`, etc. — and by
Fabric's own `net.fabricmc:intermediary:0.0.0` artifact, a tiny 578-byte
stub jar whose mapping table is a single header line with zero entries:
`tiny 2 0 official intermediary`).

Loom's `dependencies { mappings ... }` still needs *something* that
satisfies its "named" + "intermediary" namespace expectations, though,
even when there's no real remapping to do. `build.gradle` generates a
throwaway local jar at configuration time (`$buildDir/generated/identity-named-mappings.jar`)
containing just that same empty mapping table, relabeled with `named`
and `intermediary` namespaces, and points `mappings files(...)` at it.
No real mapping data exists anywhere, so there's nothing to download or
maintain — this just satisfies Loom's plumbing. If Yarn or Mojang ever
publish real mappings for a `26.x` release, prefer those instead (delete
this generator and go back to a normal `mappings "net.fabricmc:yarn:..."`
or `loom.officialMojangMappings()` line).

## What changed to get here

- `gradle/wrapper/gradle-wrapper.jar` was missing (only `gradle-wrapper.properties`
  was committed) and has now been generated.
- `gradle.properties`: `minecraft_version=26.2` (not `1.21.x` — see
  above), `loader_version=0.19.3`, `fabric_version=0.155.2+26.2`. No
  `yarn_mappings` property anymore since Yarn isn't used.
- `build.gradle`'s `fabric-loom` plugin version (`1.9-SNAPSHOT`) was
  ancient; bumped to `1.17-SNAPSHOT`.
- Current Loom needs Gradle's plugin API 9.5+, so the wrapper now points at
  Gradle 9.6.1 instead of the originally-committed 8.12.
- `settings.gradle` gained the `foojay-resolver-convention` plugin so Gradle
  can auto-provision the Java 25 toolchain without hitting a Gradle-10
  deprecation warning.
- `build.gradle` had `loom { splitEnvironmentSourceSets() }`, which is for
  mods that ship separate common (`src/main`) and client-only (`src/client`)
  source sets. This mod is 100% client-only and only has `src/main/java`, so
  that call walled the client-only Minecraft/Fabric API classes off from
  `main` entirely. Removed it; `fabric.mod.json`'s `"environment": "client"`
  was already correct on its own.
- `CommandBridge.java`: `ClientReceiveMessageEvents.ALLOW_GAME.unregister(...)`
  doesn't exist — Fabric API's `Event<T>` has no unregister mechanism at all,
  by design. The per-command register/unregister pattern was replaced with
  one persistent listener that buffers recent chat/game messages with
  timestamps; `execute` now filters that buffer by the command's send time
  instead. The JSON wire protocol (message types/fields) is unchanged, so
  `cli/mcconsole/protocol.py` didn't need updating.
- `CommandBridge.java` renamed every Minecraft/Fabric API class and method
  reference to the real (unobfuscated) names for 26.2, read directly out of
  the game jar with `javap` — most notably `MinecraftClient` → `Minecraft`,
  `ClientCommandSource` → `ClientSuggestionProvider`, `getNetworkHandler()`
  → `getConnection()`, `sendChatCommand()` → `sendCommand()`,
  `getCommandSource()` → `getSuggestionsProvider()`, `getCommandDispatcher()`
  → `getCommands()`, `Text` → `Component`, `ServerEntry.address` →
  `ServerData.ip`. `ClientLifecycleEvents` (used in `McConsoleClient.java`)
  and `ClientReceiveMessageEvents`'s package/shape were unchanged.

## Local build quirk: JAVA_HOME

Loom checks that **the JVM running Gradle itself** (not just the compile
toolchain) is Java 25+ for Minecraft 26.2, and errors out early
("`Minecraft 26.2 requires Java 25 but Gradle is using 21`") if the
`java` on `PATH` resolves to something older. On this machine that meant
running with an explicit override, e.g.:

```
JAVA_HOME="/opt/homebrew/Cellar/openjdk/25.0.1/libexec/openjdk.jdk/Contents/Home" ./gradlew build
```

This isn't an issue in the GitHub Actions workflow (`actions/setup-java`
with `java-version: 25` sets `JAVA_HOME` correctly), only for local
builds on a machine whose default `java` is older than 25.

## Before your next build

Re-check `gradle.properties` against https://fabricmc.net/develop (or
`meta.fabricmc.net` / `maven.fabricmc.net` directly, which is what was
actually used above — the marketing page itself doesn't expose raw version
numbers) since these move fast, especially right after a Minecraft release.
Also re-check whether Yarn/Mojang mappings have caught up to whatever the
current Minecraft version is — if so, prefer them over the identity-mapping
workaround above.
