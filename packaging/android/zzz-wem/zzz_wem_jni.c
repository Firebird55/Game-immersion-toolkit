#include "zzz_wem.h"

#include <jni.h>
#include <stdlib.h>

#define MAX_WEM (64 * 1024 * 1024)
#define MAX_FRAMES 4096

#define JNI_NAME(name) Java_io_github_firebird55_gameimmersiontoolkit_ZzzWemCodec_##name

typedef struct {
    zzz_wem *stream;
    zzz_wem_format format;
} decoder_ticket;

static decoder_ticket *ticket(jlong value) {
    return (decoder_ticket *)(intptr_t)value;
}

JNIEXPORT jstring JNICALL JNI_NAME(nativeProof)(JNIEnv *env, jclass owner) {
    (void)owner;
#if defined(__aarch64__)
    return (*env)->NewStringUTF(env, "toolkit-zzz-wem-pcm-v1:arm64-v8a");
#elif defined(__x86_64__)
    return (*env)->NewStringUTF(env, "toolkit-zzz-wem-pcm-v1:x86_64");
#else
    return NULL;
#endif
}

JNIEXPORT jlong JNICALL JNI_NAME(nativeOpen)(
        JNIEnv *env, jclass owner, jbyteArray input, jint channels, jint rate, jint frames) {
    (void)owner;
    if (!input || channels < 1 || channels > 2 || rate < 8000 || rate > 96000 || frames < 1)
        return 0;
    jsize size = (*env)->GetArrayLength(env, input);
    if (size < 99 || size > MAX_WEM)
        return 0;
    decoder_ticket *value = calloc(1, sizeof(*value));
    if (!value)
        return 0;
    jbyte *bytes = (*env)->GetByteArrayElements(env, input, NULL);
    if (bytes) {
        value->stream = zzz_wem_open((const uint8_t *)bytes, (size_t)size, &value->format);
        (*env)->ReleaseByteArrayElements(env, input, bytes, JNI_ABORT);
    }
    if (!value->stream || value->format.channels != (uint32_t)channels ||
            value->format.rate != (uint32_t)rate || value->format.frames != (uint32_t)frames) {
        zzz_wem_close(value->stream);
        free(value);
        return 0;
    }
    return (jlong)(intptr_t)value;
}

JNIEXPORT jbyteArray JNICALL JNI_NAME(nativeRead)(
        JNIEnv *env, jclass owner, jlong handle, jint frames) {
    (void)owner;
    if (!handle || frames <= 0 || frames > MAX_FRAMES)
        return NULL;
    decoder_ticket *value = ticket(handle);
    uint8_t pcm[MAX_FRAMES * 4];
    int result = zzz_wem_read(value->stream, (unsigned)frames, pcm, sizeof(pcm));
    if (result < 0 || result > frames)
        return NULL;
    jsize length = result * (int)value->format.channels * 2;
    jbyteArray output = (*env)->NewByteArray(env, length);
    if (output && length)
        (*env)->SetByteArrayRegion(env, output, 0, length, (const jbyte *)pcm);
    return output;
}

JNIEXPORT void JNICALL JNI_NAME(nativeClose)(JNIEnv *env, jclass owner, jlong handle) {
    (void)env;
    (void)owner;
    if (!handle)
        return;
    decoder_ticket *value = ticket(handle);
    zzz_wem_close(value->stream);
    free(value);
}
