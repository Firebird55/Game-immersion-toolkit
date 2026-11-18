package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;

/** Explicit XXH3 for inert publisher strings; unavailable without its own bundle. */
public final class PublisherHash {
    private static final String SOURCE = "c9b288e4c1f5dae54417bc8a05e6f6daf505783d916b4783f4dd2f2e7d5db486";
    private static final String HEADER = "3dc8d161e867a62d3417f7885b55fdaded8b7b497e2f165d05c94f4fe24f2ca4";
    private static final String LIBRARY = "libtoolkit_publisher_hash.so";
    private static JSONObject verified;
    private final Context context;
    public PublisherHash(Context context) { this.context = context.getApplicationContext(); }
    private static native String nativeProof();
    private static native String nativeHash64(byte[] data);
    private static byte[] read(InputStream input, int maximum) throws Exception {
        try (InputStream source = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] block = new byte[32768]; int count;
            while ((count = source.read(block)) != -1) {
                if ((long)output.size() + count > maximum) throw new IllegalStateException();
                output.write(block, 0, count);
            }
            return output.toByteArray();
        }
    }
    private static String digest(byte[] data) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(data))
            result.append(String.format(Locale.ROOT,"%02x",value & 255));
        return result.toString();
    }
    private JSONObject ready() throws Exception {
        synchronized (PublisherHash.class) {
            if (verified != null) return verified;
            String arch = System.getProperty("os.arch", "");
            String abi = arch.equals("aarch64") || arch.equals("arm64") ? "arm64-v8a"
                : arch.equals("x86_64") || arch.equals("amd64") ? "x86_64" : "";
            if (abi.isEmpty() || !android.os.Process.is64Bit()) throw new IllegalStateException();
            byte[] raw = read(context.getAssets().open("publisher-hash-manifest.json"), 65536);
            JSONObject manifest = new JSONObject(new String(raw, StandardCharsets.UTF_8));
            if (!manifest.getString("schema").equals("toolkit-android-publisher-hash-bundle-v1")
                    || !manifest.getString("contract").equals("toolkit-publisher-hash-v1")
                    || !manifest.getString("source_sha256").equals(SOURCE)
                    || !manifest.getString("header_sha256").equals(HEADER)
                    || !manifest.getString("version").equals("0.8.4")
                    || !manifest.getString("library").equals(LIBRARY)
                    || manifest.getInt("max_bytes") != 4096 || manifest.getInt("seed") != 0
                    || manifest.getBoolean("custom_secret") || manifest.getBoolean("original_client_execution"))
                throw new IllegalStateException();
            String[] names = {"publisher-hash-licenses/xxhash-LICENSE", "publisher-hash-licenses/python-xxhash-LICENSE"};
            JSONObject licenses = manifest.getJSONObject("licenses");
            if (licenses.length() != names.length) throw new IllegalStateException();
            for (String name : names) {
                byte[] notice = read(context.getAssets().open(name), 16384);
                JSONObject receipt = licenses.getJSONObject(name);
                if (notice.length != receipt.getInt("bytes") || !digest(notice).equals(receipt.getString("sha256")))
                    throw new IllegalStateException();
            }
            JSONObject libraries = manifest.getJSONObject("libraries");
            if (libraries.length() != 2 || !libraries.has("arm64-v8a") || !libraries.has("x86_64"))
                throw new IllegalStateException();
            String entryName = "lib/" + abi + "/" + LIBRARY;
            JSONObject receipt = libraries.getJSONObject(abi);
            if (!receipt.getString("entry").equals(entryName) || receipt.getLong("minimum_load_alignment") < 16384)
                throw new IllegalStateException();
            String apk = context.getApplicationInfo().sourceDir;
            try (ZipFile archive = new ZipFile(apk)) {
                ZipEntry entry = archive.getEntry(entryName);
                if (entry == null || entry.getMethod() != ZipEntry.STORED || entry.getSize() != receipt.getLong("bytes")
                        || !digest(read(archive.getInputStream(entry), 1024 * 1024)).equals(receipt.getString("sha256")))
                    throw new IllegalStateException();
            }
            System.load(apk + "!/" + entryName);
            JSONObject proof = new JSONObject(nativeProof());
            if (!proof.getString("schema").equals("toolkit-publisher-hash-v1") || !proof.getString("algorithm").equals("XXH3-64")
                    || !proof.getString("version").equals("0.8.4") || !proof.getString("abi").equals(abi)
                    || proof.getInt("pointer_bits") != 64 || proof.getInt("max_bytes") != 4096 || proof.getInt("seed") != 0
                    || proof.getBoolean("custom_secret") || proof.getBoolean("original_client_execution"))
                throw new IllegalStateException();
            proof.put("source_sha256", SOURCE).put("header_sha256", HEADER)
                .put("library_sha256", receipt.getString("sha256")).put("manifest_sha256", digest(raw))
                .put("apk_entry_verified", true).put("licenses_verified", true).put("system_fallback", false);
            verified = proof; return proof;
        }
    }
    public String proof() throws Exception { return ready().toString(); }
    public String xxh3_64(byte[] data) throws Exception {
        if (data == null || data.length > 4096) throw new IllegalArgumentException();
        byte[] stable = data.clone(); ready();
        String result = nativeHash64(stable);
        if (result == null || !result.matches("[0-9a-f]{16}")) throw new IllegalStateException();
        return result;
    }
}
