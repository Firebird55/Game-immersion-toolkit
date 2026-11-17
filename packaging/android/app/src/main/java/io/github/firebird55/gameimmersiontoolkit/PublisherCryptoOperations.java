package io.github.firebird55.gameimmersiontoolkit;

import java.math.BigInteger;
import java.security.KeyFactory;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAPrivateCrtKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Bounded publisher DATA operations. No AndroidKeyStore, network or key export. */
public final class PublisherCryptoOperations {
    public static final int MAX_BYTES = 64 * 1024 * 1024;
    public static final long CHACHA_LIMIT = ((1L << 32) - 1) * 64;
    private static final BigInteger ONE = BigInteger.ONE;
    private static final BigInteger MAX_EXPONENT = BigInteger.valueOf(0xffffffffL);
    private PublisherCryptoOperations() {}
    private static void check(boolean value) {
        if (!value) throw new IllegalArgumentException("Unsupported publisher cryptography input or runtime.");
    }
    private static void bytes(byte[] value, int maximum) { check(value != null && value.length <= maximum); }
    private static IllegalArgumentException rejected() {
        return new IllegalArgumentException("Unsupported publisher cryptography input or runtime.");
    }
    private static void wipe(byte[] value) { if (value != null) Arrays.fill(value, (byte)0); }

    public static byte[] blockCipher(String algorithm, String mode, byte[] key, byte[] iv, byte[] data, boolean decrypt) {
        byte[] stableKey = null, stableIv = null, stableData = null;
        try {
            check("AES".equals(algorithm) || "DES".equals(algorithm));
            check("ECB".equals(mode) || "CBC".equals(mode));
            bytes(key, 32); bytes(data, MAX_BYTES);
            int block = "AES".equals(algorithm) ? 16 : 8;
            check("AES".equals(algorithm) ? key.length == 16 || key.length == 24 || key.length == 32 : key.length == 8);
            check(data.length % block == 0);
            check("CBC".equals(mode) ? iv != null && iv.length == block : iv == null);
            stableKey = key.clone(); stableData = data.clone(); stableIv = iv == null ? null : iv.clone();
            Cipher cipher = Cipher.getInstance(algorithm + "/" + mode + "/NoPadding");
            SecretKeySpec secret = new SecretKeySpec(stableKey, algorithm);
            int operation = decrypt ? Cipher.DECRYPT_MODE : Cipher.ENCRYPT_MODE;
            if (stableIv == null) cipher.init(operation, secret);
            else cipher.init(operation, secret, new IvParameterSpec(stableIv));
            byte[] output = cipher.doFinal(stableData);
            check(output.length == data.length);
            return output;
        } catch (Exception error) { throw rejected(); }
        finally { wipe(stableKey); wipe(stableIv); wipe(stableData); }
    }

    private static BigInteger unsigned(byte[] encoded, int maximum) {
        bytes(encoded, maximum);check(encoded.length > 0 && encoded[0] != 0);
        return new BigInteger(1, encoded);
    }
    private static void publicNumbers(BigInteger modulus, BigInteger exponent) {
        check(modulus.bitLength() >= 1024 && modulus.bitLength() <= 4096 && modulus.testBit(0));
        check(exponent.compareTo(BigInteger.valueOf(3)) >= 0 && exponent.compareTo(MAX_EXPONENT) <= 0 && exponent.testBit(0));
    }

    public static boolean rsaVerifySha256(byte[] spki, byte[] data, byte[] signature) {
        try {
            bytes(spki, 8192);bytes(data, MAX_BYTES);bytes(signature, 512);check(spki.length > 0);
            RSAPublicKey key = (RSAPublicKey)KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(spki));
            publicNumbers(key.getModulus(), key.getPublicExponent());
            if (signature.length != (key.getModulus().bitLength() + 7) / 8) return false;
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(key);verifier.update(data);
            try { return verifier.verify(signature); }
            catch (java.security.SignatureException badSignature) { return false; }
        } catch (Exception error) { throw rejected(); }
    }

    public static byte[] rsaDecryptPkcs1(byte[] n, byte[] e, byte[] d, byte[] p, byte[] q, byte[] data) {
        try {
            BigInteger modulus = unsigned(n, 512), exponent = unsigned(e, 4), privateExponent = unsigned(d, 512);
            BigInteger first = unsigned(p, 512), second = unsigned(q, 512);
            publicNumbers(modulus, exponent);bytes(data, 512);
            check(first.compareTo(ONE) > 0 && second.compareTo(ONE) > 0 && !first.equals(second)
                && first.testBit(0) && second.testBit(0) && first.multiply(second).equals(modulus));
            check(privateExponent.compareTo(ONE) > 0 && privateExponent.compareTo(modulus) < 0);
            BigInteger pm = first.subtract(ONE), qm = second.subtract(ONE);
            BigInteger lcm = pm.divide(pm.gcd(qm)).multiply(qm);
            check(exponent.multiply(privateExponent).mod(lcm).equals(ONE));
            check(first.isProbablePrime(128) && second.isProbablePrime(128));
            check(data.length == (modulus.bitLength() + 7) / 8 && new BigInteger(1, data).compareTo(modulus) < 0);
            RSAPrivateCrtKeySpec spec = new RSAPrivateCrtKeySpec(modulus, exponent, privateExponent,
                first, second, privateExponent.mod(pm), privateExponent.mod(qm), second.modInverse(first));
            Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding");
            cipher.init(Cipher.DECRYPT_MODE, KeyFactory.getInstance("RSA").generatePrivate(spec));
            try { return cipher.doFinal(data); }
            catch (BadPaddingException invalidPadding) { return null; }
        } catch (Exception error) { throw rejected(); }
    }

    public static void validateChaCha(byte[] key, byte[] nonce, byte[] data, long position) {
        bytes(key, 32);bytes(nonce, 12);bytes(data, MAX_BYTES);
        check(key.length == 32 && nonce.length == 12 && position >= 0 && position <= CHACHA_LIMIT
            && (long)data.length <= CHACHA_LIMIT - position);
    }
}
