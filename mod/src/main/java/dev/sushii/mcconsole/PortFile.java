package dev.sushii.mcconsole;

import com.google.gson.Gson;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.io.Writer;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Writes/deletes {@code .minecraft/config/mcconsole/port.json} so the
 * external {@code mcconsole} CLI can auto-discover which port to connect
 * to without any manual configuration.
 */
public final class PortFile {

    private static final Gson GSON = new Gson();

    private PortFile() {
    }

    private static Path file() {
        return FabricLoader.getInstance().getConfigDir()
                .resolve(McConsoleClient.MOD_ID)
                .resolve("port.json");
    }

    public static void write(int port) {
        try {
            Files.createDirectories(file().getParent());
            long pid = ProcessHandle.current().pid();
            String processInfo = ManagementFactory.getRuntimeMXBean().getName();

            Entry entry = new Entry(port, pid, processInfo);
            try (Writer writer = Files.newBufferedWriter(file(), StandardCharsets.UTF_8)) {
                GSON.toJson(entry, writer);
            }
        } catch (IOException e) {
            McConsoleClient.LOGGER.warn("[MCConsole] Failed to write port file", e);
        }
    }

    public static void delete() {
        try {
            Files.deleteIfExists(file());
        } catch (IOException e) {
            McConsoleClient.LOGGER.warn("[MCConsole] Failed to delete port file", e);
        }
    }

    private record Entry(int port, long pid, String process) {
    }
}
