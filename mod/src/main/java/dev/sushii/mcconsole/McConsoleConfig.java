package dev.sushii.mcconsole;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Simple JSON config for the mod, stored at
 * {@code .minecraft/config/mcconsole/config.json}.
 *
 * Right now this only holds the socket port, but it's a natural place
 * to add things like an allowlist of command prefixes later.
 */
public class McConsoleConfig {

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final int DEFAULT_PORT = 31111;

    private int port = DEFAULT_PORT;

    public int port() {
        return port;
    }

    private static Path configDir() {
        return FabricLoader.getInstance().getConfigDir().resolve(McConsoleClient.MOD_ID);
    }

    private static Path configFile() {
        return configDir().resolve("config.json");
    }

    public static McConsoleConfig loadOrCreate() {
        Path file = configFile();
        try {
            if (Files.exists(file)) {
                try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                    McConsoleConfig loaded = GSON.fromJson(reader, McConsoleConfig.class);
                    if (loaded != null && loaded.port > 0) {
                        return loaded;
                    }
                }
            }
        } catch (IOException e) {
            McConsoleClient.LOGGER.warn("[MCConsole] Failed to read config, using defaults", e);
        }

        McConsoleConfig fresh = new McConsoleConfig();
        fresh.save();
        return fresh;
    }

    public void save() {
        try {
            Files.createDirectories(configDir());
            try (Writer writer = Files.newBufferedWriter(configFile(), StandardCharsets.UTF_8)) {
                GSON.toJson(this, writer);
            }
        } catch (IOException e) {
            McConsoleClient.LOGGER.warn("[MCConsole] Failed to write config", e);
        }
    }
}
