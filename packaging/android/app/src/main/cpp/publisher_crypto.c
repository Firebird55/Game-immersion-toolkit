/* Owned bounded transport around the authenticated, UNMODIFIED original core.
 * Original BSD/public-domain notices accompany the separate software bundle.
 * No original game code, account keys, dynamic cipher or library search path.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "chacha20.c"

#define TOOLKIT_MAX_BYTES (64u * 1024u * 1024u)
#define TOOLKIT_LIMIT ((UINT64_C(0x100000000) - 1) * 64)

static void toolkit_wipe(void *data, size_t length) {
    volatile unsigned char *p = (volatile unsigned char *)data;
    while (length--) *p++ = 0;
}

__attribute__((visibility("default")))
int toolkit_publisher_chacha20(const uint8_t *key, size_t key_size,
                              const uint8_t *nonce, size_t nonce_size,
                              const uint8_t *input, uint8_t *output,
                              size_t size, uint64_t position) {
    stream_state *state = NULL;
    int result;
    if (!key || !nonce || key_size != 32 || nonce_size != 12 || size > TOOLKIT_MAX_BYTES
            || position > TOOLKIT_LIMIT || size > TOOLKIT_LIMIT - position
            || (size && (!input || !output))) return 1;
    if (!size) return 0;
    result = chacha20_init(&state, key, key_size, nonce, nonce_size);
    if (!result) result = chacha20_seek(state, 0, (unsigned long)(position / 64), (unsigned)(position % 64));
    if (!result) result = chacha20_encrypt(state, input, output, size);
    if (state) {
        /* The original destroy frees but does not wipe its private state.
         * This transport owns the allocation lifetime and clears it first. */
        toolkit_wipe(state, sizeof(*state));
        chacha20_destroy(state);
    }
    if (result && output) toolkit_wipe(output, size);
    return result;
}

#ifndef TOOLKIT_CRYPTO_NO_JNI
#include <jni.h>
#if defined(__aarch64__)
#define TOOLKIT_ABI "arm64-v8a"
#elif defined(__x86_64__)
#define TOOLKIT_ABI "x86_64"
#else
#error Unsupported publisher cryptography ABI
#endif

JNIEXPORT jstring JNICALL
Java_io_github_firebird55_gameimmersiontoolkit_PublisherCrypto_nativeProof(JNIEnv *env, jclass type) {
    (void)type;
    return (*env)->NewStringUTF(env,
        "{\"schema\":\"toolkit-publisher-crypto-v1\",\"abi\":\"" TOOLKIT_ABI "\","
        "\"pointer_bits\":64,\"key_bytes\":32,\"nonce_bytes\":12,"
        "\"max_bytes\":67108864,\"original_client_execution\":false,\"account_keys_reused\":false}");
}

JNIEXPORT jbyteArray JNICALL
Java_io_github_firebird55_gameimmersiontoolkit_PublisherCrypto_nativeChaCha20(
    JNIEnv *env, jclass type, jbyteArray key_array, jbyteArray nonce_array, jbyteArray data, jlong position) {
    uint8_t key[32] = {0}, nonce[12] = {0}, *buffer = NULL;
    jbyteArray output = NULL;
    jsize length = 0;
    int failed = 1;
    (void)type;
    if (!key_array || !nonce_array || !data || position < 0
            || (*env)->GetArrayLength(env, key_array) != 32 || (*env)->GetArrayLength(env, nonce_array) != 12) goto cleanup;
    length = (*env)->GetArrayLength(env, data);
    if ((uint64_t)length > TOOLKIT_MAX_BYTES || (uint64_t)position > TOOLKIT_LIMIT
            || (uint64_t)length > TOOLKIT_LIMIT - (uint64_t)position) goto cleanup;
    (*env)->GetByteArrayRegion(env, key_array, 0, 32, (jbyte *)key);
    (*env)->GetByteArrayRegion(env, nonce_array, 0, 12, (jbyte *)nonce);
    if ((*env)->ExceptionCheck(env)) goto cleanup;
    buffer = malloc(length ? (size_t)length : 1);
    if (!buffer) goto cleanup;
    if (length) (*env)->GetByteArrayRegion(env, data, 0, length, (jbyte *)buffer);
    if ((*env)->ExceptionCheck(env)) goto cleanup;
    if (toolkit_publisher_chacha20(key,32,nonce,12,buffer,buffer,(size_t)length,(uint64_t)position)) goto cleanup;
    output = (*env)->NewByteArray(env, length);
    if (!output) goto cleanup;
    if (length) (*env)->SetByteArrayRegion(env, output, 0, length, (jbyte *)buffer);
    if ((*env)->ExceptionCheck(env)) goto cleanup;
    failed = 0;
cleanup:
    toolkit_wipe(key, sizeof(key));toolkit_wipe(nonce, sizeof(nonce));
    if (buffer) { toolkit_wipe(buffer, length ? (size_t)length : 1);free(buffer); }
    if (failed && !(*env)->ExceptionCheck(env)) {
        jclass error = (*env)->FindClass(env, "java/lang/IllegalArgumentException");
        if (error) (*env)->ThrowNew(env, error, "Unsupported publisher cryptography input or runtime.");
    }
    return failed ? NULL : output;
}
#endif
