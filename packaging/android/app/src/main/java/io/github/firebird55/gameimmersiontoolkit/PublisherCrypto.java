package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;

/** Explicit private platform API. Original source parameters remain inert data. */
public final class PublisherCrypto {
    private static final String SOURCE = "3f9e74444c0ecbec7af232a95d282c74b114d53212ce075ed17b7fd7dca32bb3";
    private static final String LIBRARY = "libtoolkit_publisher_crypto.so";
    private static JSONObject verified;
    private final Context context;
    public PublisherCrypto(Context context) { this.context = context.getApplicationContext(); }
    private static native String nativeProof();
    private static native byte[] nativeChaCha20(byte[] key, byte[] nonce, byte[] data, long position);
    private static byte[] read(InputStream input, int maximum) throws Exception {
        try (InputStream source = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] block = new byte[32768];int count;
            while ((count = source.read(block)) != -1) {
                if ((long)output.size() + count > maximum) throw new IllegalStateException();
                output.write(block,0,count);
            }
            return output.toByteArray();
        }
    }
    private static String digest(byte[] data) throws Exception {
        StringBuilder output = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(data))
            output.append(String.format(Locale.ROOT,"%02x",value & 255));
        return output.toString();
    }
    private JSONObject ready() throws Exception {
        synchronized (PublisherCrypto.class) {
            if (verified != null) return verified;
            String arch = System.getProperty("os.arch","");
            String abi = arch.equals("aarch64") || arch.equals("arm64") ? "arm64-v8a"
                : arch.equals("x86_64") || arch.equals("amd64") ? "x86_64" : "";
            if (abi.isEmpty() || !android.os.Process.is64Bit()) throw new IllegalStateException();
            byte[] manifestBytes = read(context.getAssets().open("publisher-crypto-manifest.json"),65536);
            JSONObject manifest = new JSONObject(new String(manifestBytes,StandardCharsets.UTF_8));
            if (!manifest.getString("schema").equals("toolkit-android-publisher-crypto-bundle-v1")
                    || !manifest.getString("contract").equals("toolkit-publisher-crypto-v1")
                    || !manifest.getString("source_sha256").equals(SOURCE)
                    || !manifest.getString("version").equals("3.24.1")
                    || !manifest.getString("library").equals(LIBRARY)
                    || !manifest.getString("platform_primitives").equals("JCA")
                    || manifest.getBoolean("original_client_execution") || manifest.getBoolean("account_keys_reused"))
                throw new IllegalStateException();
            String[] names = {"publisher-crypto-licenses/LICENSE.rst","publisher-crypto-licenses/chacha20.c.notice",
                "publisher-crypto-licenses/common.h.notice","publisher-crypto-licenses/endianess.h.notice"};
            JSONObject licenses = manifest.getJSONObject("licenses");
            if (licenses.length() != names.length) throw new IllegalStateException();
            for (String name : names) {
                byte[] original = read(context.getAssets().open(name),16384);
                JSONObject receipt = licenses.getJSONObject(name);
                if (original.length != receipt.getInt("bytes") || !digest(original).equals(receipt.getString("sha256")))
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
                if (!digest(read(archive.getInputStream(entry),1024*1024)).equals(receipt.getString("sha256")))
                    throw new IllegalStateException();
            }
            // Load exactly the already verified stored signed-APK entry.
            System.load(apk + "!/" + entryName);
            JSONObject proof = new JSONObject(nativeProof());
            if (!proof.getString("schema").equals("toolkit-publisher-crypto-v1") || !proof.getString("abi").equals(abi)
                    || proof.getInt("pointer_bits") != 64 || proof.getInt("key_bytes") != 32 || proof.getInt("nonce_bytes") != 12
                    || proof.getInt("max_bytes") != PublisherCryptoOperations.MAX_BYTES
                    || proof.getBoolean("original_client_execution") || proof.getBoolean("account_keys_reused"))
                throw new IllegalStateException();
            proof.put("source_sha256",SOURCE).put("library_sha256",receipt.getString("sha256"))
                .put("manifest_sha256",digest(manifestBytes)).put("platform_primitives","JCA")
                .put("apk_entry_verified",true).put("licenses_verified",true).put("system_fallback",false);
            verified = proof;return proof;
        }
    }
    public String proof() throws Exception { return ready().toString(); }
    public byte[] blockCipher(String algorithm, String mode, byte[] key, byte[] iv, byte[] data, boolean decrypt) throws Exception {
        ready();return PublisherCryptoOperations.blockCipher(algorithm,mode,key,iv,data,decrypt);
    }
    public boolean rsaVerifySha256(byte[] spki, byte[] data, byte[] signature) throws Exception {
        ready();return PublisherCryptoOperations.rsaVerifySha256(spki,data,signature);
    }
    public byte[] rsaDecryptPkcs1(byte[] n, byte[] e, byte[] d, byte[] p, byte[] q, byte[] data) throws Exception {
        ready();return PublisherCryptoOperations.rsaDecryptPkcs1(n,e,d,p,q,data);
    }
    public byte[] chacha20(byte[] key, byte[] nonce, byte[] data, long position) throws Exception {
        PublisherCryptoOperations.validateChaCha(key,nonce,data,position);
        byte[] stableKey = key.clone(), stableNonce = nonce.clone(), stableData = data.clone();
        try { ready();return nativeChaCha20(stableKey,stableNonce,stableData,position); }
        finally { Arrays.fill(stableKey,(byte)0);Arrays.fill(stableNonce,(byte)0);Arrays.fill(stableData,(byte)0); }
    }
}
