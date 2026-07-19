package dev.sushii.mcconsole;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Entry point for the MCConsole client mod.
 *
 * <p>This mod is intentionally client-only: it opens a loopback-only TCP
 * socket that an external terminal (the companion {@code mcconsole} CLI)
 * connects to, so commands typed in a regular terminal window can be
 * executed against whatever Minecraft server/world the client is
 * currently connected to.
 */
public class McConsoleClient implements ClientModInitializer {

    public static final String MOD_ID = "mcconsole";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private ConsoleServer consoleServer;

    @Override
    public void onInitializeClient() {
        McConsoleConfig config = McConsoleConfig.loadOrCreate();

        ClientLifecycleEvents.CLIENT_STARTED.register(client -> {
            LOGGER.info("[MCConsole] Starting console server on port {}", config.port());
            consoleServer = new ConsoleServer(config.port());
            consoleServer.start();
        });

        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> {
            if (consoleServer != null) {
                LOGGER.info("[MCConsole] Shutting down console server");
                consoleServer.stop();
            }
            PortFile.delete();
        });
    }
}
