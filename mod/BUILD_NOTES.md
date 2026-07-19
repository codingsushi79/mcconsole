# Build notes

Status as of 2026-07-19: the mod builds cleanly with `./gradlew build`
(verified in this environment) and produces `build/libs/mcconsole-0.1.0.jar`.
It has **not** been smoke-tested against a live, running Minecraft client
(no Fabric install / game account / display available in this environment)
— see the README's "Live-game testing" section for what that still needs.

## What changed to get here

- `gradle/wrapper/gradle-wrapper.jar` was missing (only `gradle-wrapper.properties`
  was committed) and has now been generated.
- `gradle.properties` versions were stale placeholders written from memory;
  they've been updated against `meta.fabricmc.net` / `maven.fabricmc.net`:
  `minecraft_version=1.21.11`, `yarn_mappings=1.21.11+build.6`,
  `loader_version=0.19.3`, `fabric_version=0.141.5+1.21.11`. Note Minecraft's
  own release train has moved on to a `26.x` versioning scheme, but Yarn/
  Loom/Fabric API modding support hasn't caught up past `1.21.11` yet — that's
  still the right version to build against.
- `build.gradle`'s `fabric-loom` plugin version (`1.9-SNAPSHOT`) was
  ancient; bumped to `1.17-SNAPSHOT` (current line as of this writing, same
  convention Fabric's own example-mod template uses).
- Current Loom needs Gradle's plugin API 9.5+, so the wrapper now points at
  Gradle 9.6.1 instead of the originally-committed 8.12.
- `settings.gradle` gained the `foojay-resolver-convention` plugin so Gradle
  can auto-provision the Java 25 toolchain without hitting a Gradle-10
  deprecation warning.
- `build.gradle` had `loom { splitEnvironmentSourceSets() }`, which is for
  mods that ship separate common (`src/main`) and client-only (`src/client`)
  source sets. This mod is 100% client-only and only has `src/main/java`, so
  that call walled the client-only Minecraft/Fabric API classes off from
  `main` entirely — every `MinecraftClient`/`ClientCommandSource`/event
  import failed to resolve. Removed it; `fabric.mod.json`'s
  `"environment": "client"` was already correct on its own.
- `CommandBridge.java`: `ClientReceiveMessageEvents.ALLOW_GAME.unregister(...)`
  doesn't exist — Fabric API's `Event<T>` has no unregister mechanism at all,
  by design. The per-command register/unregister pattern was replaced with
  one persistent listener that buffers recent chat/game messages with
  timestamps; `execute` now filters that buffer by the command's send time
  instead. The JSON wire protocol (message types/fields) is unchanged, so
  `cli/mcconsole/protocol.py` didn't need updating.

## Before your next build

Re-check `gradle.properties` against https://fabricmc.net/develop (or
`meta.fabricmc.net` / `maven.fabricmc.net` directly, which is what was
actually used above — the marketing page itself doesn't expose raw version
numbers) since these move fast, especially right after a Minecraft release.
