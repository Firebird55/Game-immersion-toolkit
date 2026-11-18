/* Owned bounded JNI transport. The pinned original XXH3 header is build input. */
#include <jni.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <inttypes.h>
#define XXH_INLINE_ALL
#define XXH_NO_STREAM
#include "xxhash.h"
#if XXH_VERSION_NUMBER != 804
#error Review the original XXH3 software before changing it.
#endif

#define EXPORT __attribute__((visibility("default")))
EXPORT int toolkit_publisher_xxh3_64(const unsigned char *data, size_t size, uint64_t *result) {
    static const unsigned char empty = 0;
    if (!result || size > 4096 || (!data && size)) return 1;
    *result = XXH3_64bits(data ? data : &empty, size);
    return 0;
}

JNIEXPORT jstring JNICALL Java_io_github_firebird55_gameimmersiontoolkit_PublisherHash_nativeProof(JNIEnv *env, jclass cls) {
    (void)cls;
#if defined(__aarch64__)
    const char *abi = "arm64-v8a";
#elif defined(__x86_64__)
    const char *abi = "x86_64";
#else
#error Unsupported publisher hash ABI
#endif
    char proof[384];
    int count = snprintf(proof, sizeof(proof),
        "{\"schema\":\"toolkit-publisher-hash-v1\",\"algorithm\":\"XXH3-64\",\"version\":\"0.8.4\","
        "\"abi\":\"%s\",\"pointer_bits\":%zu,\"max_bytes\":4096,\"seed\":0,\"custom_secret\":false,"
        "\"original_client_execution\":false}", abi, sizeof(void *) * 8);
    if (count < 0 || (size_t)count >= sizeof(proof)) return NULL;
    return (*env)->NewStringUTF(env, proof);
}

JNIEXPORT jstring JNICALL Java_io_github_firebird55_gameimmersiontoolkit_PublisherHash_nativeHash64(JNIEnv *env, jclass cls, jbyteArray input) {
    (void)cls;
    if (!input) return NULL;
    jsize size = (*env)->GetArrayLength(env, input);
    if (size < 0 || size > 4096) return NULL;
    unsigned char data[4096]; uint64_t result;
    if (size) (*env)->GetByteArrayRegion(env, input, 0, size, (jbyte *)data);
    if ((*env)->ExceptionCheck(env) || toolkit_publisher_xxh3_64(size ? data : NULL, (size_t)size, &result)) return NULL;
    char text[17];
    if (snprintf(text, sizeof(text), "%016" PRIx64, result) != 16) return NULL;
    return (*env)->NewStringUTF(env, text);
}
