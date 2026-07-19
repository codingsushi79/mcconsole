package dev.sushii.mcconsole;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Loopback-only TCP server. Accepts exactly one {@code mcconsole} CLI
 * connection at a time; a second connection attempt is rejected with a
 * short error message and closed immediately.
 *
 * <p>Security note: this only binds to 127.0.0.1, which is a reasonable
 * local trust boundary for a single-player-adjacent dev tool, but it is
 * NOT authenticated. Anything else running as your user on this machine
 * can also connect and execute commands as you. Don't widen the bind
 * address without adding real auth first.
 */
public class ConsoleServer {

    private final int port;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private Thread acceptThread;
    private ServerSocket serverSocket;
    private volatile Socket activeClient;

    public ConsoleServer(int port) {
        this.port = port;
    }

    public void start() {
        running.set(true);
        acceptThread = new Thread(this::acceptLoop, "mcconsole-accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
    }

    public void stop() {
        running.set(false);
        closeQuietly(activeClient);
        try {
            if (serverSocket != null) {
                serverSocket.close();
            }
        } catch (IOException ignored) {
            // shutting down anyway
        }
    }

    private void acceptLoop() {
        try {
            serverSocket = new ServerSocket(port, 1, InetAddress.getLoopbackAddress());
            PortFile.write(port);
            McConsoleClient.LOGGER.info("[MCConsole] Listening on 127.0.0.1:{}", port);

            while (running.get()) {
                Socket socket = serverSocket.accept();

                if (activeClient != null && !activeClient.isClosed()) {
                    McConsoleClient.LOGGER.info("[MCConsole] Rejecting extra connection from {}", socket.getRemoteSocketAddress());
                    rejectExtraConnection(socket);
                    continue;
                }

                activeClient = socket;
                McConsoleClient.LOGGER.info("[MCConsole] Terminal connected");
                Thread clientThread = new Thread(() -> handleClient(socket), "mcconsole-client");
                clientThread.setDaemon(true);
                clientThread.start();
            }
        } catch (IOException e) {
            if (running.get()) {
                McConsoleClient.LOGGER.error("[MCConsole] Server socket error", e);
            }
        }
    }

    private void rejectExtraConnection(Socket socket) {
        try (OutputStream out = socket.getOutputStream()) {
            JsonObject error = new JsonObject();
            error.addProperty("type", "error");
            error.addProperty("message", "Another mcconsole terminal is already connected.");
            out.write((error.toString() + "\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
        } catch (IOException ignored) {
            // best-effort notice
        } finally {
            closeQuietly(socket);
        }
    }

    private void handleClient(Socket socket) {
        CommandBridge bridge = null;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
             OutputStream out = socket.getOutputStream()) {

            bridge = new CommandBridge(out);

            String line;
            while (running.get() && (line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                try {
                    JsonObject message = JsonParser.parseString(line).getAsJsonObject();
                    bridge.handle(message);
                } catch (Exception e) {
                    McConsoleClient.LOGGER.warn("[MCConsole] Bad message from terminal: {}", line, e);
                    bridge.sendError("Could not parse message: " + e.getMessage());
                }
            }
        } catch (IOException e) {
            McConsoleClient.LOGGER.info("[MCConsole] Terminal disconnected ({})", e.getMessage());
        } finally {
            if (bridge != null) {
                bridge.onDisconnect();
            }
            closeQuietly(socket);
            if (socket == activeClient) {
                activeClient = null;
            }
            McConsoleClient.LOGGER.info("[MCConsole] Terminal connection closed");
        }
    }

    private static void closeQuietly(Socket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (IOException ignored) {
            // closing anyway
        }
    }
}
