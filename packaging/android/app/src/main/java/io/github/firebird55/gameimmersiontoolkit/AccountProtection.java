package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import android.util.Base64;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Native-only authenticated blobs. No plaintext/key-file fallback or JS bridge. */
public final class AccountProtection {
    private static final int MAX_PLAINTEXT = 1024 * 1024;
    private static final Object KEY_LOCK = new Object();
    private static final byte[] MAGIC = "GIT-AK1".getBytes(StandardCharsets.US_ASCII);
    private final String alias;
    private final byte[] associatedData;
    public AccountProtection(Context context) { this(context, "toolkit.accounts.v1"); }
    private AccountProtection(Context context, String identity) {
        alias = identity;
        associatedData = (context.getPackageName() + "/" + identity).getBytes(StandardCharsets.UTF_8);
    }
    private SecretKey key(boolean create) throws Exception {
        synchronized (KEY_LOCK) {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if (store.containsAlias(alias)) return (SecretKey)store.getKey(alias, null);
        if (!create) throw new IllegalStateException();
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
        }
    }
    public String protect(String encoded, boolean decrypt) {
        byte[] input = null, plaintext = null;
        try {
            if (encoded == null || encoded.length() > 1400000 || (encoded.length() % 4) != 0
                    || !encoded.matches("[A-Za-z0-9+/]*={0,2}")) throw new IllegalArgumentException();
            input = Base64.decode(encoded, Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            if (decrypt) {
                if (input.length < MAGIC.length + 12 + 16 || input.length > MAX_PLAINTEXT + MAGIC.length + 28
                        || !Arrays.equals(Arrays.copyOf(input, MAGIC.length), MAGIC)) throw new IllegalArgumentException();
                byte[] nonce = Arrays.copyOfRange(input, MAGIC.length, MAGIC.length + 12);
                cipher.init(Cipher.DECRYPT_MODE, key(false), new GCMParameterSpec(128, nonce));
                cipher.updateAAD(associatedData);
                plaintext = cipher.doFinal(input, MAGIC.length + 12, input.length - MAGIC.length - 12);
                return Base64.encodeToString(plaintext, Base64.NO_WRAP);
            }
            if (input.length > MAX_PLAINTEXT) throw new IllegalArgumentException();
            cipher.init(Cipher.ENCRYPT_MODE, key(true));cipher.updateAAD(associatedData);
            byte[] encrypted = cipher.doFinal(input), nonce = cipher.getIV();
            if (nonce.length != 12) throw new IllegalStateException();
            byte[] envelope = ByteBuffer.allocate(MAGIC.length + nonce.length + encrypted.length)
                .put(MAGIC).put(nonce).put(encrypted).array();
            return Base64.encodeToString(envelope, Base64.NO_WRAP);
        } catch (Exception error) {
            // Provider messages can contain protected state; no exception chain.
            throw new IllegalStateException("Protected Android account storage is unavailable or the saved blob is invalid.");
        } finally {
            if (input != null) Arrays.fill(input, (byte)0);
            if (plaintext != null) Arrays.fill(plaintext, (byte)0);
        }
    }
    public static String authoredProbe(Context context) throws Exception {
        if (!BuildConfig.DEBUG) throw new IllegalStateException();
        AccountProtection first = new AccountProtection(context, "toolkit.authored-vault-probe.v1");
        String original = Base64.encodeToString("authored protected storage fixture".getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        // This authored blob deliberately survives cache eviction and APK
        // replacement. It uses the isolated probe key, never account data.
        AtomicFile persisted = new AtomicFile(new File(context.getFilesDir(), "authored-vault-probe.bin"));
        boolean previous = persisted.getBaseFile().isFile();
        if (previous && !first.protect(Base64.encodeToString(persisted.readFully(), Base64.NO_WRAP), true).equals(original))
            throw new IllegalStateException("The authored protected blob did not reopen.");
        String encrypted = first.protect(original, false), another = first.protect(original, false);
        if (encrypted.equals(another)) throw new IllegalStateException("The protected fixture reused its nonce.");
        AccountProtection reopened = new AccountProtection(context, "toolkit.authored-vault-probe.v1");
        if (!reopened.protect(encrypted, true).equals(original) || reopened.key(false).getEncoded() != null)
            throw new IllegalStateException("The authored protected key boundary failed.");
        byte[] tampered = Base64.decode(encrypted, Base64.NO_WRAP);tampered[tampered.length-1] ^= 1;
        boolean rejected = false;
        try {reopened.protect(Base64.encodeToString(tampered, Base64.NO_WRAP), true);} catch (IllegalStateException expected) {rejected=true;}
        if (!rejected) throw new IllegalStateException("An unauthenticated protected blob was admitted.");
        FileOutputStream stream = persisted.startWrite();
        try {stream.write(Base64.decode(encrypted, Base64.NO_WRAP));persisted.finishWrite(stream);}
        catch (Exception error) {persisted.failWrite(stream);throw error;}
        return new JSONObject().put("fixture", "authored-android-keystore-aes-gcm")
            .put("instance_reopened", true).put("previous_saved_blob_reopened", previous)
            .put("tamper_rejected", true).put("randomized_ciphertext", true).put("key_nonexportable", true).toString();
    }
}
