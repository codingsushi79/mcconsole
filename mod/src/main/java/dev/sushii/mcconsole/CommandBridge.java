package dev.sushii.mcconsole;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.ParseResults;
import com.mojang.brigadier.suggestion.Suggestions;
import com.mojang.brigadier.tree.CommandNode;
import com.mojang.brigadier.tree.LiteralCommandNode;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientSuggestionProvider;
import net.minecraft.network.chat.Component;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Translates JSON messages coming from the external terminal into calls
 * against Minecraft's client-side Brigadier dispatcher and chat/command
 * pipeline, and writes JSON responses back.
 *
 * <p>NOTE ON MAPPINGS: this Minecraft version (26.2) ships an unobfuscated
 * client jar — there's no Yarn or Mojang mappings project for it (nothing
 * to map), so these are just the real class/method names read directly out
 * of the jar. See mod/BUILD_NOTES.md.
 */
public class CommandBridge {

    private static final long FEEDBACK_WINDOW_MS = 300;
    // Fabric API's Event<T> has no unregister(), so instead of a per-command
    // listener we register one persistent listener and filter its buffered
    // output by timestamp per command.
    private static final long BUFFER_RETENTION_MS = 5_000;
    private static final List<TimestampedMessage> RECENT_MESSAGES = new CopyOnWriteArrayList<>();
    private static final AtomicBoolean LISTENER_REGISTERED = new AtomicBoolean(false);
    // While a command's feedback window is open, its result messages are
    // hidden from the normal in-game chat/HUD — they already show up in
    // the mcconsole terminal, so echoing them in-game too is just noise.
    // There's no way to tag which incoming game messages belong to a
    // given command, so this reuses the same timing window as feedback
    // capture: only one `execute` can be in flight at a time (the CLI
    // blocks until it gets a response), so this is safe, but as a
    // consequence any unrelated system message that happens to arrive
    // during that ~300ms window gets hidden too.
    private static volatile long suppressGameMessagesUntilMs = -1;

    private record TimestampedMessage(long timestampMs, String text) {
    }

    private final OutputStream out;
    private final Object writeLock = new Object();

    public CommandBridge(OutputStream out) {
        this.out = out;
        ensureMessageListenerRegistered();
    }

    private static void ensureMessageListenerRegistered() {
        if (LISTENER_REGISTERED.compareAndSet(false, true)) {
            ClientReceiveMessageEvents.ALLOW_GAME.register((Component messageText, boolean overlay) -> {
                long now = System.currentTimeMillis();
                RECENT_MESSAGES.add(new TimestampedMessage(now, messageText.getString()));
                RECENT_MESSAGES.removeIf(m -> now - m.timestampMs() > BUFFER_RETENTION_MS);
                return now > suppressGameMessagesUntilMs;
            });
        }
    }

    public void handle(JsonObject message) {
        String type = message.has("type") ? message.get("type").getAsString() : null;
        if (type == null) {
            sendError("Missing 'type' field");
            return;
        }

        switch (type) {
            case "ping" -> handlePing();
            case "execute" -> handleExecute(message);
            case "complete" -> handleComplete(message);
            case "tree" -> handleTree();
            default -> sendError("Unknown message type: " + type);
        }
    }

    private void handlePing() {
        Minecraft client = Minecraft.getInstance();
        String connected;
        if (client.hasSingleplayerServer()) {
            connected = "singleplayer";
        } else if (client.getCurrentServer() != null) {
            connected = client.getCurrentServer().ip;
        } else {
            connected = "unknown";
        }

        JsonObject response = new JsonObject();
        response.addProperty("type", "pong");
        response.addProperty("connected_server", connected);
        send(response);
    }

    private void handleExecute(JsonObject message) {
        String text = getText(message);
        if (text == null) {
            sendError("Missing 'text' field for execute");
            return;
        }
        final String command = text.startsWith("/") ? text.substring(1) : text;

        Minecraft.getInstance().execute(() -> {
            Minecraft client = Minecraft.getInstance();
            if (client.player == null || client.getConnection() == null) {
                sendExecuteResult(false, "Not connected to a world.");
                return;
            }

            long sentAt = System.currentTimeMillis();
            suppressGameMessagesUntilMs = sentAt + FEEDBACK_WINDOW_MS;
            boolean sendFailed = false;
            String sendFailureMessage = null;
            try {
                client.getConnection().sendCommand(command);
            } catch (Exception e) {
                sendFailed = true;
                sendFailureMessage = "Failed to send command: " + e.getMessage();
            }

            final boolean failed = sendFailed;
            final String failureMessage = sendFailureMessage;
            new Thread(() -> {
                try {
                    Thread.sleep(FEEDBACK_WINDOW_MS);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
                List<String> feedback = new CopyOnWriteArrayList<>();
                if (failureMessage != null) {
                    feedback.add(failureMessage);
                }
                for (TimestampedMessage m : RECENT_MESSAGES) {
                    if (m.timestampMs() >= sentAt) {
                        feedback.add(m.text());
                    }
                }
                String combined = String.join("\n", feedback);
                sendExecuteResult(!failed, combined.isBlank() ? "(no feedback)" : combined);
            }, "mcconsole-feedback-wait").start();
        });
    }

    private void handleComplete(JsonObject message) {
        String text = getText(message);
        if (text == null) {
            sendError("Missing 'text' field for complete");
            return;
        }

        Minecraft.getInstance().execute(() -> {
            Minecraft client = Minecraft.getInstance();
            if (client.player == null || client.getConnection() == null) {
                JsonObject response = new JsonObject();
                response.addProperty("type", "completion");
                response.add("suggestions", new JsonArray());
                send(response);
                return;
            }

            try {
                // Brigadier's dispatcher parses raw command text ("gamemode ..."),
                // not chat-style text with a leading slash ("/gamemode ..."),
                // same as handleExecute below. Suggestion ranges come back
                // relative to whatever we hand the parser, so re-offset them
                // by the character we stripped to keep them aligned with the
                // original (slash-included) text the CLI is tracking.
                boolean hadSlash = text.startsWith("/");
                String parseText = hadSlash ? text.substring(1) : text;
                int offset = hadSlash ? 1 : 0;

                ClientSuggestionProvider source = client.getConnection().getSuggestionsProvider();
                ParseResults<ClientSuggestionProvider> parsed =
                        client.getConnection().getCommands().parse(parseText, source);

                // getCompletionSuggestions() can be genuinely slow for complex
                // commands (long entity selectors, NBT paths, etc). Blocking
                // this render-thread task on .join() until it finishes would
                // stall every frame — and therefore the whole game — for that
                // long. Attach a continuation instead and let this task (and
                // the render thread) move on; the response goes out whenever
                // the future actually completes, from whatever thread that is.
                client.getConnection().getCommands()
                        .getCompletionSuggestions(parsed)
                        .whenComplete((suggestions, throwable) -> {
                            if (throwable != null) {
                                sendError("Completion failed: " + throwable.getMessage());
                                return;
                            }
                            send(suggestionsToResponse(suggestions, offset));
                        });
            } catch (Exception e) {
                sendError("Completion failed: " + e.getMessage());
            }
        });
    }

    private static JsonObject suggestionsToResponse(Suggestions suggestions, int offset) {
        JsonArray suggestionArray = new JsonArray();
        suggestions.getList().forEach(s -> {
            JsonObject entry = new JsonObject();
            entry.addProperty("text", s.getText());
            entry.addProperty("start", s.getRange().getStart() + offset);
            entry.addProperty("end", s.getRange().getEnd() + offset);
            suggestionArray.add(entry);
        });

        JsonObject response = new JsonObject();
        response.addProperty("type", "completion");
        response.add("suggestions", suggestionArray);
        return response;
    }

    private void handleTree() {
        Minecraft.getInstance().execute(() -> {
            Minecraft client = Minecraft.getInstance();
            if (client.getConnection() == null) {
                sendError("Not connected to a world.");
                return;
            }

            JsonObject root = nodeToJson(client.getConnection().getCommands().getRoot());
            JsonObject response = new JsonObject();
            response.addProperty("type", "tree");
            response.add("root", root);
            send(response);
        });
    }

    private JsonObject nodeToJson(CommandNode<ClientSuggestionProvider> node) {
        JsonObject json = new JsonObject();
        String kind = node instanceof LiteralCommandNode ? "literal" : "argument";
        json.addProperty("kind", kind);
        json.addProperty("name", node.getName());

        JsonArray children = new JsonArray();
        for (CommandNode<ClientSuggestionProvider> child : node.getChildren()) {
            children.add(nodeToJson(child));
        }
        json.add("children", children);
        return json;
    }

    private static String getText(JsonObject message) {
        return message.has("text") ? message.get("text").getAsString() : null;
    }

    private void sendExecuteResult(boolean success, String feedback) {
        JsonObject response = new JsonObject();
        response.addProperty("type", "result");
        response.addProperty("success", success);
        response.addProperty("feedback", feedback);
        send(response);
    }

    public void sendError(String message) {
        JsonObject response = new JsonObject();
        response.addProperty("type", "error");
        response.addProperty("message", message);
        send(response);
    }

    private void send(JsonObject json) {
        synchronized (writeLock) {
            try {
                out.write((json.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.flush();
            } catch (IOException e) {
                McConsoleClient.LOGGER.info("[MCConsole] Failed to write to terminal (likely disconnected): {}", e.getMessage());
            }
        }
    }
}
