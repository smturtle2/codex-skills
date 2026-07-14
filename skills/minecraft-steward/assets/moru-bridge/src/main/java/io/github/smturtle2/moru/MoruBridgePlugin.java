package io.github.smturtle2.moru;

import io.papermc.paper.event.player.AsyncChatEvent;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** A local, authenticated transport only. It never decides how to answer players. */
public final class MoruBridgePlugin extends JavaPlugin implements Listener {
    private static final int MAX_HEADER_BYTES = 8_192;
    private static final int MAX_BODY_BYTES = 8_192;
    private static final Duration ACTION_CACHE_TTL = Duration.ofMinutes(10);

    private final Object eventLock = new Object();
    private final Deque<BridgeEvent> events = new ArrayDeque<>();
    private final LinkedHashMap<UUID, Deque<ChatRecord>> contextByPlayer = new LinkedHashMap<>(16, 0.75F, true);
    private final Object actionLock = new Object();
    private final Map<String, CachedAction> actionCache = new HashMap<>();

    private String bridgeId;
    private String token;
    private int queueCapacity;
    private int contextPerPlayer;
    private int maxContextPlayers;
    private long contextWindowMillis;
    private int maxMessageLength;
    private int maxCommandLength;
    private long nextEventId = 1;
    private long droppedBefore;
    private volatile boolean running;
    private ServerSocket serverSocket;
    private ExecutorService httpExecutor;
    private Thread acceptThread;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        try {
            configureAndStart();
            getServer().getPluginManager().registerEvents(this, this);
            getLogger().info("MoruBridge is listening on loopback only.");
        } catch (Exception exception) {
            getLogger().severe("MoruBridge did not start: " + exception.getMessage());
            getServer().getPluginManager().disablePlugin(this);
        }
    }

    @Override
    public void onDisable() {
        running = false;
        synchronized (eventLock) {
            eventLock.notifyAll();
        }
        closeQuietly(serverSocket);
        if (httpExecutor != null) {
            httpExecutor.shutdownNow();
        }
    }

    private void configureAndStart() throws IOException {
        String host = getConfig().getString("bind-host", "127.0.0.1");
        InetAddress address = InetAddress.getByName(host);
        if (!address.isLoopbackAddress()) {
            throw new IllegalArgumentException("bind-host must resolve to a loopback address");
        }
        token = getConfig().getString("auth-token", "");
        if (token == null || token.equals("CHANGE_ME") || token.length() < 24) {
            throw new IllegalArgumentException("set a fresh auth-token of at least 24 characters in config.yml");
        }
        queueCapacity = boundedConfig("queue-capacity", 512, 16, 4096);
        contextPerPlayer = boundedConfig("context-per-player", 20, 1, 100);
        maxContextPlayers = boundedConfig("max-context-players", 256, 1, 10_000);
        int contextSeconds = boundedConfig("context-window-seconds", 900, 30, 86_400);
        contextWindowMillis = TimeUnit.SECONDS.toMillis(contextSeconds);
        maxMessageLength = boundedConfig("max-message-length", 512, 1, 2_048);
        maxCommandLength = boundedConfig("max-command-length", 512, 1, 2_048);
        bridgeId = randomId();

        serverSocket = new ServerSocket();
        serverSocket.setReuseAddress(true);
        serverSocket.bind(new InetSocketAddress(address, getConfig().getInt("port", 25576)));
        httpExecutor = Executors.newCachedThreadPool(task -> {
            Thread thread = new Thread(task, "MoruBridge HTTP");
            thread.setDaemon(true);
            return thread;
        });
        running = true;
        acceptThread = new Thread(this::acceptLoop, "MoruBridge accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
    }

    private int boundedConfig(String key, int fallback, int minimum, int maximum) {
        int value = getConfig().getInt(key, fallback);
        if (value < minimum || value > maximum) {
            throw new IllegalArgumentException(key + " must be between " + minimum + " and " + maximum);
        }
        return value;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlayerChat(AsyncChatEvent event) {
        String message = PlainTextComponentSerializer.plainText().serialize(event.originalMessage()).trim();
        if (!message.isEmpty()) {
            addEvent(BridgeEvent.chat(event.getPlayer().getUniqueId(), event.getPlayer().getName(), message));
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        addEvent(BridgeEvent.join(player.getUniqueId(), player.getName(), !player.hasPlayedBefore()));
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();
        addEvent(BridgeEvent.quit(player.getUniqueId(), player.getName()));
    }

    private void addEvent(BridgeEvent event) {
        synchronized (eventLock) {
            event.id = nextEventId++;
            events.addLast(event);
            if (event.type.equals("chat")) {
                pruneAllContexts(event.timestamp);
                Deque<ChatRecord> playerContext = contextByPlayer.computeIfAbsent(event.playerId, ignored -> new ArrayDeque<>());
                playerContext.addLast(new ChatRecord(event.timestamp, event.playerName, event.message));
                pruneContext(playerContext, event.timestamp);
                while (playerContext.size() > contextPerPlayer) {
                    playerContext.removeFirst();
                }
                while (contextByPlayer.size() > maxContextPlayers) {
                    Iterator<UUID> iterator = contextByPlayer.keySet().iterator();
                    iterator.next();
                    iterator.remove();
                }
            }
            while (events.size() > queueCapacity) {
                BridgeEvent removed = events.removeFirst();
                droppedBefore = Math.max(droppedBefore, removed.id);
            }
            eventLock.notifyAll();
        }
    }

    private void acceptLoop() {
        while (running) {
            try {
                Socket socket = serverSocket.accept();
                httpExecutor.execute(() -> handleSocket(socket));
            } catch (IOException exception) {
                if (running) {
                    getLogger().warning("MoruBridge accept failed: " + exception.getMessage());
                }
            }
        }
    }

    private void handleSocket(Socket socket) {
        try (socket; InputStream input = socket.getInputStream(); OutputStream output = socket.getOutputStream()) {
            try {
                HttpRequest request = readRequest(input);
                if (!authorized(request)) {
                    writeJson(output, 401, Map.of("error", "unauthorized"));
                    return;
                }
                route(request, output);
            } catch (RequestException exception) {
                writeJson(output, exception.status, Map.of("error", exception.getMessage()));
            }
        } catch (IOException exception) {
            if (running) {
                getLogger().fine("MoruBridge request failed: " + exception.getMessage());
            }
        }
    }

    private void route(HttpRequest request, OutputStream output) throws IOException, RequestException {
        URI uri;
        try {
            uri = URI.create(request.target);
        } catch (IllegalArgumentException exception) {
            throw new RequestException(400, "invalid request target");
        }
        String path = uri.getPath();
        Map<String, String> query = parseForm(uri.getRawQuery());
        if (request.method.equals("GET") && path.equals("/v1/health")) {
            writeJson(output, 200, healthPayload());
            return;
        }
        if (request.method.equals("GET") && path.equals("/v1/events")) {
            long after = nonNegativeLong(query.get("after"), "after", 0);
            int limit = boundedNumber(query.get("limit"), "limit", 16, 1, 64);
            int waitSeconds = boundedNumber(query.get("wait"), "wait", 25, 0, 25);
            writeJson(output, 200, eventsPayload(after, limit, waitSeconds));
            return;
        }
        if (request.method.equals("GET") && path.equals("/v1/context")) {
            UUID playerId = parseUuid(required(query, "player_uuid"));
            int limit = boundedNumber(query.get("limit"), "limit", 12, 1, contextPerPlayer);
            writeJson(output, 200, contextPayload(playerId, limit));
            return;
        }
        if (request.method.equals("POST") && path.equals("/v1/actions")) {
            Map<String, String> form = parseForm(new String(request.body, StandardCharsets.UTF_8));
            writeJson(output, 200, performAction(form));
            return;
        }
        throw new RequestException(404, "not found");
    }

    private Map<String, Object> healthPayload() {
        synchronized (eventLock) {
            return Map.of(
                "bridge_id", bridgeId,
                "running", running,
                "queue_depth", events.size(),
                "dropped_before", droppedBefore,
                "next_event_id", nextEventId
            );
        }
    }

    private Map<String, Object> eventsPayload(long after, int limit, int waitSeconds) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(waitSeconds);
        synchronized (eventLock) {
            while (running && !hasEventsAfter(after) && waitSeconds > 0) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    break;
                }
                try {
                    TimeUnit.NANOSECONDS.timedWait(eventLock, remaining);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            List<Map<String, Object>> payloadEvents = new ArrayList<>();
            for (BridgeEvent event : events) {
                if (event.id > after) {
                    payloadEvents.add(event.asMap());
                    if (payloadEvents.size() == limit) {
                        break;
                    }
                }
            }
            Map<String, Object> response = new LinkedHashMap<>();
            response.put("bridge_id", bridgeId);
            response.put("events", payloadEvents);
            if (!events.isEmpty() && after < events.getFirst().id - 1) {
                response.put("dropped_before", events.getFirst().id - 1);
            } else if (droppedBefore > 0 && after < droppedBefore) {
                response.put("dropped_before", droppedBefore);
            }
            return response;
        }
    }

    private boolean hasEventsAfter(long after) {
        return !events.isEmpty() && events.getLast().id > after;
    }

    private Map<String, Object> contextPayload(UUID playerId, int limit) {
        synchronized (eventLock) {
            Deque<ChatRecord> records = contextByPlayer.get(playerId);
            List<Map<String, Object>> payload = new ArrayList<>();
            if (records != null) {
                pruneContext(records, System.currentTimeMillis());
                int skip = Math.max(0, records.size() - limit);
                int index = 0;
                for (ChatRecord record : records) {
                    if (index++ >= skip) {
                        payload.add(record.asMap());
                    }
                }
            }
            return Map.of("player_uuid", playerId.toString(), "messages", payload);
        }
    }

    private void pruneContext(Deque<ChatRecord> records, long now) {
        while (!records.isEmpty() && now - records.getFirst().timestamp > contextWindowMillis) {
            records.removeFirst();
        }
    }

    private void pruneAllContexts(long now) {
        Iterator<Map.Entry<UUID, Deque<ChatRecord>>> iterator = contextByPlayer.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<UUID, Deque<ChatRecord>> entry = iterator.next();
            pruneContext(entry.getValue(), now);
            if (entry.getValue().isEmpty()) {
                iterator.remove();
            }
        }
    }

    private Map<String, Object> performAction(Map<String, String> form) throws RequestException {
        String actionId = required(form, "action_id");
        if (actionId.length() > 128) {
            throw new RequestException(400, "action_id is too long");
        }
        CompletableFuture<ActionResult> future;
        boolean schedule = false;
        synchronized (actionLock) {
            pruneActions();
            CachedAction cached = actionCache.get(actionId);
            if (cached == null) {
                future = new CompletableFuture<>();
                actionCache.put(actionId, new CachedAction(System.currentTimeMillis(), future));
                schedule = true;
            } else {
                future = cached.result;
            }
        }
        if (schedule) {
            scheduleAction(form, future);
        }
        try {
            return future.get(5, TimeUnit.SECONDS).asMap(actionId);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new RequestException(503, "action was interrupted");
        } catch (TimeoutException exception) {
            throw new RequestException(504, "action timed out");
        } catch (ExecutionException exception) {
            throw new RequestException(500, "action failed");
        }
    }

    private void scheduleAction(Map<String, String> form, CompletableFuture<ActionResult> future) {
        getServer().getGlobalRegionScheduler().execute(this, () -> {
            try {
                String type = form.get("type");
                if ("command".equals(type)) {
                    String command = form.get("command");
                    if (command == null || command.isBlank() || command.length() > maxCommandLength) {
                        future.complete(ActionResult.failed("command must be between 1 and " + maxCommandLength + " characters"));
                        return;
                    }
                    String normalized = command.strip();
                    if (normalized.startsWith("/")) {
                        normalized = normalized.substring(1);
                    }
                    if (normalized.isBlank()) {
                        future.complete(ActionResult.failed("command must not be only a slash"));
                        return;
                    }
                    boolean handled = Bukkit.dispatchCommand(Bukkit.getConsoleSender(), normalized);
                    future.complete(handled ? ActionResult.success("command_dispatched") : ActionResult.failed("command_not_handled"));
                    return;
                }
                String message = form.get("message");
                if (message == null || message.isBlank() || message.length() > maxMessageLength) {
                    future.complete(ActionResult.failed("message must be between 1 and " + maxMessageLength + " characters"));
                    return;
                }
                Component rendered = Component.text(message);
                if ("public".equals(type)) {
                    Bukkit.broadcast(rendered);
                    future.complete(ActionResult.success("sent_public"));
                    return;
                }
                if ("direct".equals(type)) {
                    String rawPlayerId = form.get("player_uuid");
                    UUID playerId;
                    try {
                        playerId = UUID.fromString(rawPlayerId);
                    } catch (IllegalArgumentException exception) {
                        future.complete(ActionResult.failed("player_uuid must be a UUID"));
                        return;
                    }
                    Player player = Bukkit.getPlayer(playerId);
                    if (player == null || !player.isOnline()) {
                        future.complete(ActionResult.failed("player is not online"));
                        return;
                    }
                    player.sendMessage(rendered);
                    future.complete(ActionResult.success("sent_direct"));
                    return;
                }
                future.complete(ActionResult.failed("type must be public, direct, or command"));
            } catch (RuntimeException exception) {
                future.complete(ActionResult.failed("server rejected the action"));
                getLogger().warning("MoruBridge action failed: " + exception.getClass().getSimpleName());
            }
        });
    }

    private void pruneActions() {
        long cutoff = System.currentTimeMillis() - ACTION_CACHE_TTL.toMillis();
        actionCache.entrySet().removeIf(entry -> entry.getValue().createdAt < cutoff);
    }

    private boolean authorized(HttpRequest request) {
        String authorization = request.headers.get("authorization");
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return false;
        }
        return MessageDigest.isEqual(
            token.getBytes(StandardCharsets.UTF_8),
            authorization.substring("Bearer ".length()).getBytes(StandardCharsets.UTF_8)
        );
    }

    private static HttpRequest readRequest(InputStream input) throws IOException, RequestException {
        String requestLine = readLine(input);
        String[] parts = requestLine.split(" ", 3);
        if (parts.length != 3 || !parts[2].startsWith("HTTP/")) {
            throw new RequestException(400, "invalid request line");
        }
        Map<String, String> headers = new HashMap<>();
        for (int lines = 0; lines < 100; lines++) {
            String line = readLine(input);
            if (line.isEmpty()) {
                break;
            }
            int separator = line.indexOf(':');
            if (separator <= 0) {
                throw new RequestException(400, "invalid header");
            }
            headers.put(line.substring(0, separator).trim().toLowerCase(), line.substring(separator + 1).trim());
        }
        int contentLength = boundedNumber(headers.get("content-length"), "content-length", 0, 0, MAX_BODY_BYTES);
        byte[] body = input.readNBytes(contentLength);
        if (body.length != contentLength) {
            throw new RequestException(400, "truncated request body");
        }
        return new HttpRequest(parts[0], parts[1], headers, body);
    }

    private static String readLine(InputStream input) throws IOException, RequestException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (bytes.size() < MAX_HEADER_BYTES) {
            int value = input.read();
            if (value == -1) {
                throw new RequestException(400, "unexpected end of request");
            }
            if (value == '\n') {
                String line = bytes.toString(StandardCharsets.ISO_8859_1);
                return line.endsWith("\r") ? line.substring(0, line.length() - 1) : line;
            }
            bytes.write(value);
        }
        throw new RequestException(431, "request header is too large");
    }

    private static Map<String, String> parseForm(String raw) throws RequestException {
        Map<String, String> result = new HashMap<>();
        if (raw == null || raw.isEmpty()) {
            return result;
        }
        for (String part : raw.split("&")) {
            String[] item = part.split("=", 2);
            try {
                String key = URLDecoder.decode(item[0], StandardCharsets.UTF_8);
                String value = item.length == 2 ? URLDecoder.decode(item[1], StandardCharsets.UTF_8) : "";
                result.put(key, value);
            } catch (IllegalArgumentException exception) {
                throw new RequestException(400, "invalid URL encoding");
            }
        }
        return result;
    }

    private static String required(Map<String, String> values, String key) throws RequestException {
        String value = values.get(key);
        if (value == null || value.isBlank()) {
            throw new RequestException(400, key + " is required");
        }
        return value;
    }

    private static int boundedNumber(String raw, String name, int fallback, int minimum, int maximum) throws RequestException {
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            int value = Integer.parseInt(raw);
            if (value < minimum || value > maximum) {
                throw new RequestException(400, name + " must be between " + minimum + " and " + maximum);
            }
            return value;
        } catch (NumberFormatException exception) {
            throw new RequestException(400, name + " must be an integer");
        }
    }

    private static long nonNegativeLong(String raw, String name, long fallback) throws RequestException {
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            long value = Long.parseLong(raw);
            if (value < 0) {
                throw new RequestException(400, name + " must not be negative");
            }
            return value;
        } catch (NumberFormatException exception) {
            throw new RequestException(400, name + " must be an integer");
        }
    }

    private static UUID parseUuid(String value) throws RequestException {
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException exception) {
            throw new RequestException(400, "player_uuid must be a UUID");
        }
    }

    private static void writeJson(OutputStream output, int status, Object payload) throws IOException {
        byte[] body = json(payload).getBytes(StandardCharsets.UTF_8);
        String reason = switch (status) {
            case 200 -> "OK";
            case 400 -> "Bad Request";
            case 401 -> "Unauthorized";
            case 404 -> "Not Found";
            case 431 -> "Request Header Fields Too Large";
            case 503 -> "Service Unavailable";
            case 504 -> "Gateway Timeout";
            default -> "Internal Server Error";
        };
        output.write(("HTTP/1.1 " + status + " " + reason + "\r\n"
            + "Content-Type: application/json; charset=utf-8\r\n"
            + "Content-Length: " + body.length + "\r\n"
            + "Connection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        output.write(body);
    }

    @SuppressWarnings("unchecked")
    private static String json(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String string) {
            return '"' + escapeJson(string) + '"';
        }
        if (value instanceof Number || value instanceof Boolean) {
            return value.toString();
        }
        if (value instanceof Map<?, ?> map) {
            List<String> items = new ArrayList<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                items.add(json(String.valueOf(entry.getKey())) + ":" + json(entry.getValue()));
            }
            return "{" + String.join(",", items) + "}";
        }
        if (value instanceof Collection<?> collection) {
            List<String> items = new ArrayList<>();
            for (Object item : collection) {
                items.add(json(item));
            }
            return "[" + String.join(",", items) + "]";
        }
        throw new IllegalArgumentException("unsupported JSON value: " + value.getClass().getName());
    }

    private static String escapeJson(String value) {
        StringBuilder result = new StringBuilder(value.length() + 16);
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\b' -> result.append("\\b");
                case '\f' -> result.append("\\f");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (character < 0x20) {
                        result.append(String.format("\\u%04x", (int) character));
                    } else {
                        result.append(character);
                    }
                }
            }
        }
        return result.toString();
    }

    private static String randomId() {
        byte[] bytes = new byte[16];
        new SecureRandom().nextBytes(bytes);
        StringBuilder result = new StringBuilder(32);
        for (byte value : bytes) {
            result.append(String.format("%02x", value));
        }
        return result.toString();
    }

    private static void closeQuietly(ServerSocket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (IOException ignored) {
            // Shutdown is best effort.
        }
    }

    private record HttpRequest(String method, String target, Map<String, String> headers, byte[] body) {}

    private static final class RequestException extends Exception {
        private final int status;

        private RequestException(int status, String message) {
            super(message);
            this.status = status;
        }
    }

    private static final class BridgeEvent {
        private long id;
        private final long timestamp;
        private final String type;
        private final UUID playerId;
        private final String playerName;
        private final String message;
        private final Boolean firstJoin;

        private BridgeEvent(String type, UUID playerId, String playerName, String message, Boolean firstJoin) {
            this.timestamp = System.currentTimeMillis();
            this.type = type;
            this.playerId = playerId;
            this.playerName = playerName;
            this.message = message;
            this.firstJoin = firstJoin;
        }

        private static BridgeEvent chat(UUID playerId, String playerName, String message) {
            return new BridgeEvent("chat", playerId, playerName, message, null);
        }

        private static BridgeEvent join(UUID playerId, String playerName, boolean firstJoin) {
            return new BridgeEvent("join", playerId, playerName, null, firstJoin);
        }

        private static BridgeEvent quit(UUID playerId, String playerName) {
            return new BridgeEvent("quit", playerId, playerName, null, null);
        }

        private Map<String, Object> asMap() {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("id", id);
            result.put("timestamp", timestamp);
            result.put("type", type);
            result.put("player_uuid", playerId.toString());
            result.put("player_name", playerName);
            if (message != null) {
                result.put("message", message);
            }
            if (firstJoin != null) {
                result.put("first_join", firstJoin);
            }
            return result;
        }
    }

    private record ChatRecord(long timestamp, String playerName, String message) {
        private Map<String, Object> asMap() {
            return Map.of("timestamp", timestamp, "player_name", playerName, "message", message);
        }
    }

    private record CachedAction(long createdAt, CompletableFuture<ActionResult> result) {}

    private record ActionResult(boolean ok, String result) {
        private static ActionResult success(String result) {
            return new ActionResult(true, result);
        }

        private static ActionResult failed(String result) {
            return new ActionResult(false, result);
        }

        private Map<String, Object> asMap(String actionId) {
            return Map.of("action_id", actionId, "ok", ok, "result", result);
        }
    }
}
