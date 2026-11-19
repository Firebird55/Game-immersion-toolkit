package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebMessage;
import android.webkit.WebMessagePort;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

/** An offline recognizer for subtitle scripts outside the bundled ML Kit models. */
final class PortableSubtitleOcr {
    private static final String ORIGIN = "https://ocr.toolkit.invalid";
    private static final String PAGE = ORIGIN + "/";
    private static final String DOCUMENT = "<!doctype html><meta charset=utf-8>"
        + "<meta http-equiv=Content-Security-Policy content=\"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; "
        + "worker-src 'self'; connect-src 'self'; img-src data: blob:; base-uri 'none'; form-action 'none'\">"
        + "<script type=module src=/native-subtitle-ocr.mjs></script>";
    private final Context context;
    private final File frontend;
    private final Handler main = new Handler(Looper.getMainLooper());
    private WebView view;
    private WebMessagePort port;
    private boolean ready;
    private CompletableFuture<String> pending;
    private String request;

    PortableSubtitleOcr(Context context, File frontend) {
        this.context = context;
        this.frontend = frontend;
    }

    JSONObject recognize(Bitmap bitmap, String language, int width, int height) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, bytes) || bytes.size() > 10 * 1024 * 1024)
            throw new IOException("Subtitle OCR image exceeds its limit");
        String data = new JSONObject().put("language", language).put("width", width).put("height", height)
            .put("image", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP)).toString();
        CompletableFuture<String> reply = new CompletableFuture<>();
        main.post(() -> {
            pending = reply;
            request = data;
            try {
                if (view == null) open();
                else if (ready) send();
            } catch (RuntimeException error) { close(); }
        });
        try { return new JSONObject(reply.get(20, TimeUnit.SECONDS)); }
        catch (Exception error) {
            main.post(() -> { if (pending == reply) close(); });
            throw error;
        }
    }

    private void send() {
        port.postMessage(new WebMessage(request));
        request = null;
    }

    private void open() {
        view = new WebView(context);
        view.getSettings().setJavaScriptEnabled(true);
        view.getSettings().setBlockNetworkLoads(true);
        view.getSettings().setAllowFileAccess(false);
        view.getSettings().setAllowContentAccess(false);
        view.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView web, WebResourceRequest resource) { return true; }

            @Override public WebResourceResponse shouldInterceptRequest(WebView web, WebResourceRequest resource) {
                Uri uri = resource.getUrl();
                String path = uri.getEncodedPath();
                if (!"https".equals(uri.getScheme()) || !"ocr.toolkit.invalid".equals(uri.getAuthority())
                        || uri.getQuery() != null || resource.isRedirect() || !"GET".equals(resource.getMethod()))
                    return unavailable();
                try {
                    if (resource.isForMainFrame() && "/".equals(path))
                        return new WebResourceResponse("text/html", "UTF-8",
                            new ByteArrayInputStream(DOCUMENT.getBytes(StandardCharsets.UTF_8)));
                    if ("/native-subtitle-ocr.mjs".equals(path))
                        return new WebResourceResponse("text/javascript", "UTF-8", context.getAssets().open("native-subtitle-ocr.mjs"));
                    if (path != null && path.matches("/ocr/(?:tesseract\\.esm\\.min\\.js|verified-worker\\.js|worker\\.min\\.js|core/tesseract-core-lstm\\.wasm(?:\\.js)?|lang/(?:rus|tha)\\.traineddata\\.gz)")) {
                        File file = new File(frontend, "mobile-capture" + path);
                        String mime = path.endsWith(".wasm") ? "application/wasm"
                            : path.endsWith(".gz") ? "application/gzip" : "text/javascript";
                        return new WebResourceResponse(mime, null, new FileInputStream(file));
                    }
                } catch (IOException error) { return unavailable(); }
                return unavailable();
            }

            @Override public void onPageFinished(WebView web, String url) {
                if (web != view || port != null || !PAGE.equals(url)) return;
                try {
                    WebMessagePort[] ports = web.createWebMessageChannel();
                    port = ports[0];
                    port.setWebMessageCallback(new WebMessagePort.WebMessageCallback() {
                        @Override public void onMessage(WebMessagePort source, WebMessage data) {
                            if (source != port) return;
                            String value = data.getData();
                            if (!ready && "ready".equals(value)) {
                                ready = true;
                                try { send(); } catch (RuntimeException error) { close(); }
                            } else if (pending != null) {
                                if (value != null && value.length() <= 2 * 1024 * 1024 && !"error".equals(value))
                                    pending.complete(value);
                                else pending.completeExceptionally(new IOException("Subtitle OCR failed"));
                                pending = null;
                            }
                        }
                    });
                    web.postWebMessage(new WebMessage("toolkit-native-subtitle-ocr",
                        new WebMessagePort[]{ports[1]}), Uri.parse(ORIGIN));
                } catch (RuntimeException error) { close(); }
            }

            @Override public boolean onRenderProcessGone(WebView web, RenderProcessGoneDetail detail) {
                if (web == view) close();
                return true;
            }
        });
        view.loadUrl(PAGE);
    }

    private static WebResourceResponse unavailable() {
        return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden",
            java.util.Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
    }

    private void close() {
        if (pending != null) pending.completeExceptionally(new IOException("Subtitle OCR unavailable"));
        pending = null;
        request = null;
        ready = false;
        if (port != null) port.close();
        port = null;
        if (view != null) view.destroy();
        view = null;
    }
}
