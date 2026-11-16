package io.github.firebird55.gameimmersiontoolkit;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.concurrent.Executors;

/** Native storage/lifecycle host; the reader and matching behavior stay shared. */
public final class MainActivity extends Activity {
    private WebView reader;
    private ValueCallback<Uri[]> picker;
    private String origin;
    private boolean foreground;
    private long lifecycleRevision;
    private final java.util.concurrent.ExecutorService worker = Executors.newSingleThreadExecutor();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView loading = new TextView(this);
        loading.setText("Opening Game Immersion Toolkit…");
        loading.setPadding(32, 48, 32, 32);
        setContentView(loading);
        worker.execute(() -> {
            try {
                File web = preparedReader();
                FrameOcr ocr = new FrameOcr(getApplicationContext());
                PyObject module = Python.getInstance().getModule("backend.android_host");
                String address = module.callAttr("start", new File(getFilesDir(), "toolkit").getCanonicalPath(),
                    web.getCanonicalPath(), ocr).toString();
                origin = address.substring(0, address.length() - 1);
                String sessionCookie = module.callAttr("bootstrap_cookie").toString();
                if (BuildConfig.DEBUG && getIntent().getBooleanExtra("toolkitSelfTest", false)) {
                    String proof = Python.getInstance().getModule("backend.android_probe")
                        .callAttr("run", new File(getCacheDir(), "core-probe").getCanonicalPath()).toString();
                    org.json.JSONObject report = new org.json.JSONObject(proof);
                    android.media.MediaPlayer player = new android.media.MediaPlayer();
                    java.util.concurrent.CountDownLatch complete = new java.util.concurrent.CountDownLatch(1);
                    try {
                        player.setDataSource(report.getString("private_audio_path"));
                        player.setOnCompletionListener(ignored -> complete.countDown());
                        player.prepare();player.start();
                        report.put("native_media_completed", complete.await(5, java.util.concurrent.TimeUnit.SECONDS));
                    } finally { player.release(); }
                    report.remove("private_audio_path");
                    report.put("native_ocr", new org.json.JSONObject(Python.getInstance().getModule("backend.android_probe")
                        .callAttr("run_ocr", new File(getCacheDir(), "ocr-probe").getCanonicalPath(),
                            ocr.authoredProbe()).toString()));
                    try (FileOutputStream output = new FileOutputStream(new File(getFilesDir(), "android-core-proof.json"))) {
                        output.write(report.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
                    }
                }
                runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) openReader(address, sessionCookie); });
            } catch (Exception error) {
                runOnUiThread(() -> loading.setText("The local toolkit could not start. Your imported data has been preserved."));
                if (BuildConfig.DEBUG) android.util.Log.e("ToolkitAndroid", "Local host startup failed", error);
            }
        });
    }

    private File preparedReader() throws Exception {
        String manifest;
        try (java.util.zip.ZipInputStream source = new java.util.zip.ZipInputStream(getAssets().open("reader.bundle"))) {
            java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
            java.util.zip.ZipEntry entry;
            while ((entry = source.getNextEntry()) != null && !entry.getName().equals("desktop-manifest.json")) {}
            if (entry == null) throw new java.io.IOException("Missing shared reader manifest");
            byte[] block = new byte[65536];int count;
            while ((count = source.read(block)) > 0) {
                if (bytes.size() + count > 1024 * 1024) throw new java.io.IOException();
                bytes.write(block, 0, count);
            }
            manifest = bytes.toString("UTF-8");
        }
        org.json.JSONObject document = new org.json.JSONObject(manifest);
        String identity = document.getString("build_id");
        if (!identity.matches("[0-9a-f]{64}")) throw new java.io.IOException("Invalid reader identity");
        File destination = new File(getFilesDir(), "reader-" + identity);
        File marker = new File(destination, ".complete");
        if (marker.isFile()) return destination;
        File pending = new File(getFilesDir(), "reader-" + identity + "-" + java.util.UUID.randomUUID());
        if (!pending.mkdirs()) throw new java.io.IOException();
        try (java.util.zip.ZipInputStream source = new java.util.zip.ZipInputStream(getAssets().open("reader.bundle"))) {
            java.util.HashSet<String> seen = new java.util.HashSet<>();
            java.util.zip.ZipEntry entry;long total = 0;
            while ((entry = source.getNextEntry()) != null) {
                String name = entry.getName();
                File target = new File(pending, name);
                if (entry.isDirectory() || !seen.add(name) || seen.size() > 4096 || name.contains("\\")
                    || !target.getCanonicalPath().startsWith(pending.getCanonicalPath() + File.separator)) throw new java.io.IOException();
                File parent = target.getParentFile();
                if (!parent.isDirectory() && !parent.mkdirs()) throw new java.io.IOException();
                try (FileOutputStream output = new FileOutputStream(target)) {
                    byte[] block = new byte[65536];int count;
                    while ((count = source.read(block)) > 0) {
                        total += count;if (total > 256L * 1024 * 1024) throw new java.io.IOException();
                        output.write(block, 0, count);
                    }
                }
            }
        }
        org.json.JSONObject files = document.getJSONObject("files");
        java.util.Iterator<String> names = files.keys();
        while (names.hasNext()) {
            String name = names.next();
            File file = new File(pending, name);
            if (!file.getCanonicalPath().startsWith(pending.getCanonicalPath() + File.separator)) throw new java.io.IOException();
            org.json.JSONObject expected = files.getJSONObject(name);
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            try (InputStream source = new java.io.FileInputStream(file)) {
                byte[] block = new byte[65536];int count;
                while ((count = source.read(block)) > 0) digest.update(block, 0, count);
            }
            StringBuilder hash = new StringBuilder();
            for (byte value : digest.digest()) hash.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            if (file.length() != expected.getLong("bytes") || !hash.toString().equals(expected.getString("sha256")))
                throw new java.io.IOException("Reader resource changed");
        }
        if (!new File(pending, ".complete").createNewFile() || !pending.renameTo(destination)) throw new java.io.IOException("Reader publication failed");
        return destination;
    }

    private void openReader(String address, String sessionCookie) {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        reader = new WebView(this);
        reader.getSettings().setJavaScriptEnabled(true);
        reader.getSettings().setDomStorageEnabled(true);
        reader.getSettings().setAllowFileAccess(false);
        reader.getSettings().setAllowContentAccess(true); // Explicit user-selected SAF file uploads.
        reader.getSettings().setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(reader, false);
        // No unrestricted JavaScript interface is exposed to remote frames.
        reader.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!request.isForMainFrame()) return !"https".equals(uri.getScheme()) || !"vdo.ninja".equals(uri.getHost());
                if (uri.toString().startsWith(origin + "/")) return false;
                if ("https".equals(uri.getScheme())) {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                }
                return true;
            }
        });
        reader.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (picker != null) picker.onReceiveValue(null);
                picker = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("application/zip");
                startActivityForResult(intent, 21);
                return true;
            }
        });
        setContentView(reader);
        CookieManager.getInstance().setCookie(origin, sessionCookie, accepted -> {
            if (reader != null && !isFinishing() && !isDestroyed()) reader.loadUrl(address);
        });
    }

    @Override protected void onActivityResult(int request, int result, Intent intent) {
        super.onActivityResult(request, result, intent);
        if (request == 21 && picker != null) {
            picker.onReceiveValue(result == RESULT_OK && intent != null && intent.getData() != null
                ? new Uri[]{intent.getData()} : null);
            picker = null;
        }
    }

    @Override protected void onStop() {
        foreground = false;lifecycleRevision++;
        CookieManager.getInstance().flush();
        pauseReaderMedia();
        if (reader != null) {
            reader.onPause();
        }
        pauseCapture();
        super.onStop();
    }
    private void pauseReaderMedia() {
        if (reader != null) reader.evaluateJavascript("window.dispatchEvent(new Event('toolkit-host-pause'));document.querySelectorAll('audio,video').forEach(function(x){x.pause()})", null);
    }
    @Override public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (!hasFocus) {
            lifecycleRevision++;pauseReaderMedia();pauseCapture();
        } else resumeReader();
    }
    private void pauseCapture() {
        if (!worker.isShutdown()) worker.execute(() -> Python.getInstance().getModule("backend.android_host").callAttr("pause"));
    }
    private void resumeReader() {
        final long revision = ++lifecycleRevision;
        // Resume hints wait behind every earlier native pause fence. Never
        // deliver an old queued resume after a newer stop/focus loss.
        if (!worker.isShutdown()) worker.execute(() -> runOnUiThread(() -> {
            if (reader != null && foreground && hasWindowFocus() && revision == lifecycleRevision && !isDestroyed())
                reader.evaluateJavascript("window.dispatchEvent(new Event('toolkit-host-resume'))", null);
        }));
    }
    @Override protected void onStart() {
        super.onStart();foreground = true;if (reader != null) reader.onResume();resumeReader();
    }
    @Override protected void onDestroy() {
        if (picker != null) { picker.onReceiveValue(null); picker = null; }
        if (reader != null) { reader.stopLoading();reader.destroy();reader = null; }
        worker.shutdown();
        super.onDestroy();
    }
}
