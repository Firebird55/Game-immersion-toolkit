package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;

/** Exact signed-APK software input; original client bytes remain inert data. */
public final class NativeX64Decoder {
    private static final String SOURCE = "796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede";
    private static final String LIBRARY = "libtoolkit_x64_decoder.so";
    private static JSONObject proof;
    private final Context context;
    public NativeX64Decoder(Context context) { this.context = context.getApplicationContext(); }
    private static native String nativeProof();
    private static native String nativeDisassemble(byte[] data, long address, int count);

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
        byte[] bytes = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder result = new StringBuilder();
        for (byte value : bytes) result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }
    private synchronized JSONObject ready() throws Exception {
        synchronized (NativeX64Decoder.class) {
            if (proof != null) return proof;
            String arch = System.getProperty("os.arch", "");
            String abi = arch.equals("aarch64") || arch.equals("arm64") ? "arm64-v8a" : arch.equals("x86_64") || arch.equals("amd64") ? "x86_64" : "";
            if (abi.isEmpty() || !android.os.Process.is64Bit()) throw new IllegalStateException();
            byte[] manifestBytes = read(context.getAssets().open("native-decoder-manifest.json"), 65536);
            JSONObject manifest = new JSONObject(new String(manifestBytes, java.nio.charset.StandardCharsets.UTF_8));
            if (!manifest.getString("schema").equals("toolkit-android-native-decoders-v1")
                    || !manifest.getString("source_sha256").equals(SOURCE) || !manifest.getString("version").equals("5.0.7")
                    || !manifest.getString("library").equals(LIBRARY) || manifest.getBoolean("original_client_execution"))
                throw new IllegalStateException();
            JSONObject licenses = manifest.getJSONObject("licenses");
            String[] names = {"native-decoder-licenses/0-LICENSE.TXT", "native-decoder-licenses/1-LICENSE.TXT", "native-decoder-licenses/2-LICENSE_LLVM.TXT"};
            if (licenses.length() != names.length) throw new IllegalStateException();
            for (String name : names) {
                byte[] license = read(context.getAssets().open(name), 65536);
                JSONObject receipt = licenses.getJSONObject(name);
                if (license.length != receipt.getInt("bytes") || !digest(license).equals(receipt.getString("sha256")))
                    throw new IllegalStateException();
            }
            String entryName = "lib/" + abi + "/" + LIBRARY;
            JSONObject receipt = manifest.getJSONObject("libraries").getJSONObject(abi);
            if (!receipt.getString("entry").equals(entryName) || receipt.getLong("minimum_load_alignment") < 16384)
                throw new IllegalStateException();
            String apk = context.getApplicationInfo().sourceDir;
            try (ZipFile archive = new ZipFile(apk)) {
                ZipEntry entry = archive.getEntry(entryName);
                if (entry == null || entry.getMethod() != ZipEntry.STORED || entry.getSize() != receipt.getLong("bytes"))
                    throw new IllegalStateException();
                byte[] library = read(archive.getInputStream(entry), 16 * 1024 * 1024);
                if (!digest(library).equals(receipt.getString("sha256"))) throw new IllegalStateException();
            }
            // Android's APK linker loads this exact verified stored entry.
            // Never use loadLibrary, a global search path or downloaded inputs.
            System.load(apk + "!/" + entryName);
            JSONObject actual = new JSONObject(nativeProof());
            if (!actual.getString("schema").equals("toolkit-x64-capi-v1") || !actual.getString("abi").equals(abi)
                    || actual.getInt("api_major") != 5 || actual.getInt("api_minor") != 0
                    || actual.getInt("pointer_bits") != 64 || actual.getBoolean("original_client_execution"))
                throw new IllegalStateException();
            actual.put("source_sha256", SOURCE).put("version", "5.0.7")
                .put("library_sha256", receipt.getString("sha256")).put("manifest_sha256", digest(manifestBytes))
                .put("apk_entry_verified", true).put("licenses_verified", true).put("system_fallback", false);
            proof = actual;
            return proof;
        }
    }
    public String proof() throws Exception { return ready().toString(); }
    public String disassemble(byte[] data, long address, int count) throws Exception {
        ready();
        if (data == null || data.length < 1 || data.length > 65536 || count < 0 || count > 65536)
            throw new IllegalArgumentException();
        return nativeDisassemble(data, address, count);
    }
}
