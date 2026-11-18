package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebMessage;
import android.webkit.WebMessagePort;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Iterator;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

/** An optional app-owned ZZZ reader with one cancellable stage and no external I/O. */
public final class ZzzCatalogueWorker {
    private static final String ORIGIN = "https://toolkit-zzz-catalogue.invalid";
    private static final String PAGE = ORIGIN + "/";
    private static final String IDENTITY = "e2c8551d8841c7447689b356d09d77e6c72651d94b9bc9bf245634b3362bc24b";
    private static final int LIMIT = 128 * 1024;
    private static final int CHUNK_MESSAGE_LIMIT = 33_000;
    private static final int TIMEOUT_MS = 180_000;
    private final Context context;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile Ticket active;
    private volatile Progress last;
    private volatile String softwarePhase = "not-started";
    private Software software;
    // Created and destroyed exclusively on the WebView's owning looper.
    private Session session;

    ZzzCatalogueWorker(Context context) { this.context = context.getApplicationContext(); }

    private static IllegalStateException unavailable() {
        return new IllegalStateException("The verified Android ZZZ catalogue worker is unavailable");
    }

    private byte[] asset(String path, int limit) throws Exception {
        try (InputStream stream = context.getAssets().open("zzz-catalogue/" + path)) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            for (int count; (count = stream.read(buffer)) != -1;) {
                if (output.size() + count > limit) throw unavailable();
                output.write(buffer, 0, count);
            }
            if (output.size() == 0) throw unavailable();
            return output.toByteArray();
        }
    }

    private static String sha(byte[] raw) throws Exception {
        StringBuilder hex = new StringBuilder(64);
        for (byte value : MessageDigest.getInstance("SHA-256").digest(raw)) {
            hex.append(Character.forDigit((value >>> 4) & 15, 16));
            hex.append(Character.forDigit(value & 15, 16));
        }
        return hex.toString();
    }

    private byte[] member(JSONObject receipt, String path) throws Exception {
        byte[] raw = asset(path, LIMIT);
        if (raw.length != receipt.getInt("bytes") || !sha(raw).equals(receipt.getString("sha256"))) throw unavailable();
        return raw;
    }

    private static String encoded(String id, byte[] content) {
        return "<script type=\"application/octet-stream\" id=\"" + id + "\">"
                + Base64.encodeToString(content, Base64.NO_WRAP) + "</script>";
    }

    private synchronized Software verifiedSoftware() throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) throw unavailable();
        if (software != null) return software;
        softwarePhase = "verifying-software";
        final byte[] raw = asset("manifest.json", 16 * 1024);
        if (!IDENTITY.equals(sha(raw))) throw unavailable();
        final JSONObject manifest = new JSONObject(new String(raw, StandardCharsets.UTF_8));
        final JSONObject modules = manifest.getJSONObject("modules");
        if (!"toolkit-android-zzz-catalogue-assets-v1".equals(manifest.getString("schema")) || modules.length() != 13)
            throw unavailable();
        final StringBuilder data = new StringBuilder(encoded("manifest", raw));
        for (Iterator<String> names = modules.keys(); names.hasNext();) {
            final String name = names.next();
            if (!name.matches("[a-z0-9.-]{1,80}\\.mjs")) throw unavailable();
            data.append(encoded("file-" + name, member(modules.getJSONObject(name), name)));
        }
        data.append(encoded("worker", member(manifest.getJSONObject("worker"), "catalogue-worker.mjs")));
        final String host = new String(member(manifest.getJSONObject("host"), "catalogue-host.js"), StandardCharsets.UTF_8);
        if (host.toLowerCase(java.util.Locale.ROOT).contains("</script")) throw unavailable();
        software = new Software(data.toString(), host);
        softwarePhase = "software-verified";
        return software;
    }

    public String proof() throws Exception {
        verifiedSoftware();
        return IDENTITY;
    }

    String authoredPhase() {
        if (!BuildConfig.DEBUG) throw unavailable();
        final Progress progress = last;
        return progress == null ? softwarePhase : progress.phase;
    }

    public synchronized Ticket begin(String mode, String input) throws Exception {
        final Software verified = verifiedSoftware();
        if (active != null || mode == null || input == null || input.length() > 192 * 1024) throw unavailable();
        final String start = new JSONObject().put("type", "start").put("mode", mode).put("input", new JSONObject(input))
                .put("identity", IDENTITY).toString();
        if (start.length() > 256 * 1024) throw unavailable();
        final Ticket ticket = new Ticket(start);
        last = ticket.progress;
        active = ticket;
        main.post(() -> {
            if (active != ticket) return;
            try {
                session = new Session(ticket);
                session.open(verified);
            } catch (RuntimeException error) {
                ticket.progress.phase = "open-failed";
                finish(ticket);
            }
        });
        main.postDelayed(ticket.timeout, TIMEOUT_MS);
        return ticket;
    }

    private synchronized void finish(Ticket ticket) {
        if (active != ticket) return;
        main.removeCallbacks(ticket.timeout);
        main.post(() -> {
            if (session == null || session.ticket != ticket) return;
            final Session finished = session;
            session = null;
            try {
                if (finished.port != null) finished.port.close();
            } finally {
                finished.view.destroy();
            }
        });
        active = null;
        ticket.closed = true;
    }

    private static final class Progress {
        volatile String phase = "opening-document";
    }

    public final class Ticket {
        private final String start;
        private final ArrayBlockingQueue<String> events = new ArrayBlockingQueue<>(2);
        private final Progress progress = new Progress();
        private final Runnable timeout = () -> {
            if (active == this) progress.phase = "worker-deadline";
            finish(this);
        };
        private volatile boolean closed;

        Ticket(String start) { this.start = start; }

        public String poll(int milliseconds) throws InterruptedException {
            if (milliseconds < 1 || milliseconds > 1000 || Looper.myLooper() == Looper.getMainLooper())
                throw new IllegalArgumentException();
            String event = events.poll(milliseconds, TimeUnit.MILLISECONDS);
            if (event == null && closed) throw unavailable();
            return event;
        }

        public void send(String message) {
            if (active != this || message == null || message.length() > CHUNK_MESSAGE_LIMIT) throw unavailable();
            main.post(() -> {
                if (active != this) return;
                try {
                    if (session == null || session.ticket != this || session.port == null) throw unavailable();
                    session.port.postMessage(new WebMessage(message));
                } catch (RuntimeException error) {
                    progress.phase = "chunk-send-failed";
                    finish(this);
                }
            });
        }

        public void cancel() { finish(this); }
    }

    private static final class Software {
        final byte[] document;
        Software(String data, String host) {
            final String nonce = UUID.randomUUID().toString();
            final String html = "<!doctype html><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\""
                    + "default-src 'none'; script-src 'nonce-" + nonce + "' blob: 'wasm-unsafe-eval'; "
                    + "worker-src blob:; connect-src 'none'; base-uri 'none'; form-action 'none'\">"
                    + data + "<script nonce=\"" + nonce + "\">" + host + "</script>";
            document = html.getBytes(StandardCharsets.UTF_8);
        }
    }

    private final class Session {
        final Ticket ticket;
        final WebView view;
        WebMessagePort port;
        boolean ready;

        Session(Ticket ticket) {
            this.ticket = ticket;
            view = new WebView(context);
        }

        void open(Software software) {
            final WebSettings settings = view.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setAllowFileAccess(false);
            settings.setAllowContentAccess(false);
            settings.setBlockNetworkLoads(true);
            settings.setDomStorageEnabled(false);
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
            if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(false);
            view.setWebViewClient(new WebViewClient() {
                @Override public boolean shouldOverrideUrlLoading(WebView web, WebResourceRequest request) { return true; }
                @Override public WebResourceResponse shouldInterceptRequest(WebView web, WebResourceRequest request) {
                    // Give the port and Blob worker a committed HTTPS
                    // document origin through the same route as browser CI.
                    // Network loads remain blocked by WebSettings.
                    if (active == ticket && request.isForMainFrame() && !request.isRedirect()
                            && "GET".equals(request.getMethod()) && PAGE.equals(request.getUrl().toString())) {
                        ticket.progress.phase = "document-served";
                        return new WebResourceResponse("text/html", "UTF-8", 200, "OK",
                                Collections.singletonMap("Cache-Control", "no-store"),
                                new ByteArrayInputStream(software.document));
                    }
                    return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden",
                            Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
                }
                @Override public void onReceivedError(WebView web, WebResourceRequest request, WebResourceError error) {
                    if (active == ticket && request.isForMainFrame()) {
                        ticket.progress.phase = "document-load-failed";
                        finish(ticket);
                    }
                }
                @Override public void onPageFinished(WebView web, String url) {
                    if (active != ticket || port != null || !PAGE.equals(url)) return;
                    try {
                        final WebMessagePort[] ports = web.createWebMessageChannel();
                        port = ports[0];
                        port.setWebMessageCallback(new WebMessagePort.WebMessageCallback() {
                            @Override public void onMessage(WebMessagePort source, WebMessage value) {
                                receive(value.getData());
                            }
                        });
                        web.postWebMessage(new WebMessage("toolkit-zzz-catalogue-v1",
                                new WebMessagePort[]{ports[1]}), Uri.parse(ORIGIN));
                        ticket.progress.phase = "port-posted";
                    } catch (RuntimeException error) {
                        ticket.progress.phase = "port-post-failed";
                        finish(ticket);
                    }
                }
                @Override public boolean onRenderProcessGone(WebView web, RenderProcessGoneDetail detail) {
                    if (active == ticket) ticket.progress.phase = "renderer-exited";
                    finish(ticket);
                    return true;
                }
            });
            view.loadUrl(PAGE);
        }

        void receive(String message) {
            if (active != ticket) return;
            try {
                if (message == null || message.length() > CHUNK_MESSAGE_LIMIT) throw unavailable();
                final String type = new JSONObject(message).getString("type");
                if (!ready) {
                    if (!type.equals("ready")) throw unavailable();
                    ready = true;
                    ticket.progress.phase = "port-ready";
                    port.postMessage(new WebMessage(ticket.start));
                    return;
                }
                switch (type) {
                    case "started": ticket.progress.phase = "worker-started"; break;
                    case "read": ticket.progress.phase = "input-requested"; break;
                    case "pull": ticket.progress.phase = "input-streaming"; break;
                    case "write": ticket.progress.phase = "output-requested"; break;
                    case "chunk": ticket.progress.phase = "output-streaming"; break;
                    case "complete": ticket.progress.phase = "worker-complete"; break;
                    case "failed": ticket.progress.phase = "worker-rejected"; break;
                    default: throw unavailable();
                }
                if (!ticket.events.offer(message)) throw unavailable();
                if (type.equals("complete") || type.equals("failed")) finish(ticket);
            } catch (Exception error) {
                ticket.progress.phase = "port-protocol-failed";
                finish(ticket);
            }
        }
    }
}
