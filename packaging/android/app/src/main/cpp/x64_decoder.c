/* Owned bounded JNI transport. Capstone decodes DATA, never executes it.
 * Capstone's complete BSD/LLVM notices accompany the signed application.
 */
#include <jni.h>
#include <capstone/capstone.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#define MAX_INPUT 65536
#define MAX_OUTPUT (32u * 1024u * 1024u)
#if defined(__aarch64__)
#define ABI "arm64-v8a"
#elif defined(__x86_64__)
#define ABI "x86_64"
#else
#error Unsupported Android decoder ABI
#endif

typedef struct { char *data; size_t length, capacity; int failed; } output;
static void reserve(output *o, size_t more) {
    if (o->failed || more > MAX_OUTPUT || o->length > MAX_OUTPUT - more) { o->failed = 1; return; }
    size_t need = o->length + more + 1;
    if (need <= o->capacity) return;
    size_t capacity = o->capacity ? o->capacity : 4096;
    while (capacity < need) capacity *= 2;
    if (capacity > MAX_OUTPUT + 1u) capacity = MAX_OUTPUT + 1u;
    char *next = realloc(o->data, capacity);
    if (!next) { o->failed = 1; return; }
    o->data = next; o->capacity = capacity;
}
static void raw(output *o, const char *text) {
    size_t length = strlen(text); reserve(o, length);
    if (!o->failed) { memcpy(o->data + o->length, text, length); o->length += length; o->data[o->length] = 0; }
}
static void number(output *o, const char *format, ...) {
    char data[96]; va_list args; va_start(args, format);
    int length = vsnprintf(data, sizeof(data), format, args); va_end(args);
    if (length < 0 || (size_t)length >= sizeof(data)) { o->failed = 1; return; }
    raw(o, data);
}
static void string(output *o, const char *text) {
    if (!text) { raw(o, "null"); return; }
    raw(o, "\"");
    for (size_t i = 0; text[i]; ++i) {
        unsigned char c = (unsigned char)text[i];
        if (i > 1024 || c >= 127 || c < 32) { o->failed = 1; return; }
        if (c == '"' || c == '\\') raw(o, "\\");
        char one[] = {(char)c, 0}; raw(o, one);
    }
    raw(o, "\"");
}
static jstring finish(JNIEnv *env, output *o) {
    jstring result = NULL;
    if (!o->failed && o->data) result = (*env)->NewStringUTF(env, o->data);
    free(o->data);
    if (!result && !(*env)->ExceptionCheck(env)) {
        jclass type = (*env)->FindClass(env, "java/lang/IllegalStateException");
        if (type) (*env)->ThrowNew(env, type, "Bounded original-data decoder did not complete");
    }
    return result;
}
static void registers(output *o, const uint16_t *values, unsigned count) {
    raw(o, "[");
    if (count > 64) { o->failed = 1; return; }
    for (unsigned i = 0; i < count; ++i) { if (i) raw(o, ","); number(o, "%u", (unsigned)values[i]); }
    raw(o, "]");
}

JNIEXPORT jstring JNICALL
Java_io_github_firebird55_gameimmersiontoolkit_NativeX64Decoder_nativeProof(JNIEnv *env, jclass type) {
    (void)type;
    output o = {0}; int major = 0, minor = 0;
    cs_version(&major, &minor);
    csh handle = 0;
    if (major != 5 || minor != 0 || cs_open(CS_ARCH_X86, CS_MODE_64, &handle) != CS_ERR_OK) {
        o.failed = 1; return finish(env, &o);
    }
    number(&o, "{\"schema\":\"toolkit-x64-capi-v1\",\"api_major\":%d,\"api_minor\":%d,\"abi\":", major, minor);
    string(&o, ABI);
    number(&o, ",\"pointer_bits\":%u,\"register_names\":[", (unsigned)(8 * sizeof(void *)));
    for (unsigned i = 0; i < X86_REG_ENDING; ++i) {
        if (i) raw(&o, ","); string(&o, cs_reg_name(handle, i));
    }
    raw(&o, "],\"original_client_execution\":false}");
    cs_close(&handle);
    return finish(env, &o);
}

JNIEXPORT jstring JNICALL
Java_io_github_firebird55_gameimmersiontoolkit_NativeX64Decoder_nativeDisassemble(
    JNIEnv *env, jclass type, jbyteArray input, jlong address, jint limit) {
    (void)type;
    output o = {0}; csh handle = 0; cs_insn *instructions = NULL;
    if (!input || limit < 0 || limit > MAX_INPUT) { o.failed = 1; return finish(env, &o); }
    jsize length = (*env)->GetArrayLength(env, input);
    if (length < 1 || length > MAX_INPUT) { o.failed = 1; return finish(env, &o); }
    uint8_t *bytes = malloc((size_t)length);
    if (!bytes) { o.failed = 1; return finish(env, &o); }
    (*env)->GetByteArrayRegion(env, input, 0, length, (jbyte *)bytes);
    if ((*env)->ExceptionCheck(env)) { free(bytes); return NULL; }
    if (cs_open(CS_ARCH_X86, CS_MODE_64, &handle) != CS_ERR_OK ||
        cs_option(handle, CS_OPT_DETAIL, CS_OPT_ON) != CS_ERR_OK) { o.failed = 1; goto done; }
    size_t count = cs_disasm(handle, bytes, (size_t)length, (uint64_t)address, (size_t)limit, &instructions);
    if (count > MAX_INPUT || (!count && cs_errno(handle) != CS_ERR_OK)) { o.failed = 1; goto done; }
    raw(&o, "[");
    for (size_t at = 0; at < count; ++at) {
        cs_insn *i = &instructions[at];
        if (!i->detail || i->size < 1 || i->size > sizeof(i->bytes) || i->detail->groups_count > 8) { o.failed = 1; break; }
        if (at) raw(&o, ",");
        number(&o, "{\"address\":%" PRIu64 ",\"size\":%u,\"id\":%u,\"mnemonic\":", i->address, (unsigned)i->size, i->id);
        string(&o, i->mnemonic); raw(&o, ",\"op_str\":"); string(&o, i->op_str);
        raw(&o, ",\"bytes\":\"");
        for (unsigned k = 0; k < i->size; ++k) number(&o, "%02x", (unsigned)i->bytes[k]);
        raw(&o, "\",\"groups\":[");
        for (unsigned k = 0; k < i->detail->groups_count; ++k) { if (k) raw(&o, ","); number(&o, "%u", (unsigned)i->detail->groups[k]); }
        cs_regs reads, writes; uint8_t read_count = 0, write_count = 0;
        if (cs_regs_access(handle, i, reads, &read_count, writes, &write_count) != CS_ERR_OK) { o.failed = 1; break; }
        raw(&o, "],\"regs_read\":"); registers(&o, reads, read_count);
        raw(&o, ",\"regs_write\":"); registers(&o, writes, write_count);
        raw(&o, ",\"operands\":[");
        cs_x86 *x86 = &i->detail->x86;
        if (x86->op_count > 8) { o.failed = 1; break; }
        for (unsigned k = 0; k < x86->op_count; ++k) {
            const cs_x86_op *op = &x86->operands[k];
            if (k) raw(&o, ",");
            number(&o, "{\"type\":%u,\"size\":%u,\"access\":%u", (unsigned)op->type, (unsigned)op->size, (unsigned)op->access);
            if (op->type == X86_OP_REG) number(&o, ",\"reg\":%u", (unsigned)op->reg);
            else if (op->type == X86_OP_IMM) number(&o, ",\"imm\":%" PRId64, op->imm);
            else if (op->type == X86_OP_MEM) number(&o,
                ",\"mem\":{\"segment\":%u,\"base\":%u,\"index\":%u,\"scale\":%d,\"disp\":%" PRId64 "}",
                (unsigned)op->mem.segment, (unsigned)op->mem.base, (unsigned)op->mem.index, op->mem.scale, op->mem.disp);
            else { o.failed = 1; break; }
            raw(&o, "}");
        }
        raw(&o, "]}");
    }
    raw(&o, "]");
done:
    if (instructions) cs_free(instructions, count);
    if (handle) cs_close(&handle);
    free(bytes);
    return finish(env, &o);
}
