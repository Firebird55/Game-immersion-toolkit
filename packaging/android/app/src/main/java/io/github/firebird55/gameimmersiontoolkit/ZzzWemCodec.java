package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;

/** Attested app-owned Wwise codec with one bounded in-memory decode at a time. */
public final class ZzzWemCodec {
    private static final String CONTRACT = "toolkit-zzz-wem-pcm-v1";
    private static final String LIBRARY = "libtoolkit_zzz_wem.so";
    private static final int MAX_WEM = 64 * 1024 * 1024;
    private static final int MAX_FRAMES = 4096;
    private static final AtomicBoolean active = new AtomicBoolean();
    private static JSONObject verified;
    private final Context context;

    ZzzWemCodec(Context context) { this.context = context.getApplicationContext(); }
    private static native String nativeProof();
    private static native long nativeOpen(byte[] input, int channels, int rate, int frames);
    private static native byte[] nativeRead(long handle, int frames);
    private static native void nativeClose(long handle);

    private static IllegalStateException unavailable() {
        return new IllegalStateException("The verified Android ZZZ audio decoder is unavailable");
    }

    private static byte[] read(InputStream input, int maximum) throws Exception {
        try (InputStream source = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] block = new byte[4096];
            for (int count; (count = source.read(block)) != -1;) {
                if (output.size() + count > maximum) throw unavailable();
                output.write(block, 0, count);
            }
            if (output.size() == 0) throw unavailable();
            return output.toByteArray();
        }
    }

    private static String digest(byte[] data) throws Exception {
        StringBuilder hash = new StringBuilder(64);
        for (byte value : MessageDigest.getInstance("SHA-256").digest(data))
            hash.append(String.format(Locale.ROOT, "%02x", value & 255));
        return hash.toString();
    }

    private JSONObject ready() throws Exception {
        synchronized (ZzzWemCodec.class) {
            if (verified != null) return verified;
            String arch = System.getProperty("os.arch", "");
            String abi = arch.equals("aarch64") || arch.equals("arm64") ? "arm64-v8a"
                    : arch.equals("x86_64") || arch.equals("amd64") ? "x86_64" : "";
            if (abi.isEmpty() || !android.os.Process.is64Bit()) throw unavailable();
            byte[] raw = read(context.getAssets().open("zzz-wem-manifest.json"), 16384);
            JSONObject manifest = new JSONObject(new String(raw, StandardCharsets.UTF_8));
            if (!manifest.getString("schema").equals("toolkit-android-zzz-wem-link-v2")
                    || !manifest.getString("contract").equals(CONTRACT)
                    || manifest.getInt("api") != 24 || manifest.getInt("max_wem_bytes") != MAX_WEM
                    || manifest.getInt("max_frames_per_read") != MAX_FRAMES) throw unavailable();

            JSONObject sources = manifest.getJSONObject("source_sha256");
            if (sources.length() != 3 ||
                    !sources.getString("vgmstream-r2168-source.tar.gz").equals("e74334a13007655b5812af1f4b5880dbb11516dfc0a114d3cffe2dd09dc4fe1b") ||
                    !sources.getString("libvorbis-1.3.7.tar.xz").equals("b33cc4934322bcbf6efcbacf49e3ca01aadbea4114ec9589d1b1e9d20f72954b") ||
                    !sources.getString("libogg-1.3.5.tar.xz").equals("c4d91be36fc8e54deae7575241e03f4211eb102afb3fc0775fbbc1b740016705"))
                throw unavailable();

            JSONObject notices = manifest.getJSONObject("notices_sha256");
            if (notices.length() != 3) throw unavailable();
            for (String notice : new String[]{"vgmstream-COPYING", "libogg-COPYING", "libvorbis-COPYING"}) {
                byte[] contents = read(context.getAssets().open("zzz-wem-licenses/" + notice), 16384);
                if (!digest(contents).equals(notices.getString(notice))) throw unavailable();
            }

            JSONObject libraries = manifest.getJSONObject("libraries");
            if (libraries.length() != 2 || !libraries.has("arm64-v8a") || !libraries.has("x86_64")) throw unavailable();
            String entryName = "lib/" + abi + "/" + LIBRARY;
            JSONObject receipt = libraries.getJSONObject(abi);
            if (receipt.getInt("minimum_load_alignment") < 16384) throw unavailable();
            String apk = context.getApplicationInfo().sourceDir;
            try (ZipFile archive = new ZipFile(apk)) {
                ZipEntry entry = archive.getEntry(entryName);
                if (entry == null || entry.getMethod() != ZipEntry.STORED || entry.getSize() != receipt.getLong("bytes")
                        || !digest(read(archive.getInputStream(entry), 1024 * 1024)).equals(receipt.getString("sha256")))
                    throw unavailable();
            }
            try {
                System.load(apk + "!/" + entryName);
                if (!(CONTRACT + ":" + abi).equals(nativeProof())) throw unavailable();
            } catch (LinkageError error) {
                throw unavailable();
            }
            verified = new JSONObject().put("schema", CONTRACT).put("abi", abi).put("source_sha256", sources)
                    .put("manifest_sha256", digest(raw)).put("library_sha256", receipt.getString("sha256"))
                    .put("max_wem_bytes", MAX_WEM).put("max_frames_per_read", MAX_FRAMES)
                    .put("apk_entry_verified", true).put("notices_verified", true).put("system_fallback", false);
            return verified;
        }
    }

    public String proof() throws Exception { return ready().toString(); }

    public Ticket begin(byte[] input, int channels, int rate, int frames) throws Exception {
        if (input == null || input.length < 99 || input.length > MAX_WEM || channels < 1 || channels > 2
                || rate < 8000 || rate > 96000 || frames <= 0
                || 44L + frames * channels * 2L > 128L * 1024 * 1024) throw unavailable();
        ready();
        if (!active.compareAndSet(false, true)) throw unavailable();
        long handle = 0;
        boolean opened = false;
        try {
            handle = nativeOpen(input, channels, rate, frames);
            if (handle == 0) throw unavailable();
            Ticket result = new Ticket(handle, channels, frames);
            opened = true;
            return result;
        } finally {
            if (!opened) {
                if (handle != 0) nativeClose(handle);
                active.set(false);
            }
        }
    }

    public static final class Ticket implements AutoCloseable {
        private long handle;
        private final int channels;
        private int remaining;

        private Ticket(long handle, int channels, int frames) {
            this.handle = handle;
            this.channels = channels;
            remaining = frames;
        }

        public synchronized byte[] readFrames(int count) {
            if (handle == 0 || count < 1 || count > MAX_FRAMES) throw unavailable();
            int frames = Math.min(count, remaining);
            byte[] result = nativeRead(handle, count);
            if (result == null || result.length != frames * channels * 2) throw unavailable();
            remaining -= frames;
            return result;
        }

        @Override public synchronized void close() {
            if (handle == 0) return;
            try {
                nativeClose(handle);
            } finally {
                handle = 0;
                active.set(false);
            }
        }
    }
}
