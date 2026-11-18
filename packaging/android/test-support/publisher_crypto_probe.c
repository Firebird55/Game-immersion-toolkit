/* Authored-only standalone CAPI acceptance; never packaged in the application.
 * The host verifies this executable, explicit library and fixture hashes first.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef int (*cipher_fn)(const uint8_t *,size_t,const uint8_t *,size_t,const uint8_t *,uint8_t *,size_t,uint64_t);
static int take(FILE *input, void *out, size_t length) { return fread(out,1,length,input) == length; }
static int u32(FILE *input, uint32_t *value) {
    uint8_t b[4];if (!take(input,b,4)) return 0;
    *value = (uint32_t)b[0] | (uint32_t)b[1]<<8 | (uint32_t)b[2]<<16 | (uint32_t)b[3]<<24;return 1;
}
static int u64(FILE *input, uint64_t *value) {
    uint32_t lo,hi;if (!u32(input,&lo) || !u32(input,&hi)) return 0;
    *value = (uint64_t)lo | (uint64_t)hi<<32;return 1;
}
int main(int argc,char **argv) {
    if (argc != 3 || argv[1][0] != '/' || strstr(argv[1],"..") || strlen(argv[1]) > 1024) return 2;
    void *library = dlopen(argv[1],RTLD_NOW | RTLD_LOCAL);
    if (!library) return 3;
    cipher_fn cipher = (cipher_fn)dlsym(library,"toolkit_publisher_chacha20");
    FILE *input = fopen(argv[2],"rb");
    if (!cipher || !input) return 4;
    char magic[4];uint32_t count;
    if (!take(input,magic,4) || memcmp(magic,"TPC1",4) || !u32(input,&count) || count < 1 || count > 64) return 5;
    for (uint32_t index=0;index<count;index++) {
        uint32_t key_size,nonce_size,length,expected_ok;uint64_t claimed,position;
        uint8_t key[64],nonce[32],data[4096],expected[4096],actual[4096];
        if (!u32(input,&key_size) || !u32(input,&nonce_size) || !u32(input,&length)
                || !u64(input,&claimed) || !u64(input,&position) || !u32(input,&expected_ok)
                || key_size > sizeof(key) || nonce_size > sizeof(nonce) || length > sizeof(data)
                || claimed > 64u*1024u*1024u+1 || expected_ok > 1
                || (expected_ok && claimed != length)
                || !take(input,key,key_size) || !take(input,nonce,nonce_size) || !take(input,data,length)
                || (expected_ok && !take(input,expected,length))) return 6;
        /* Oversize negative deliberately proves rejection before reading data. */
        if (claimed != length && claimed <= 64u*1024u*1024u) return 7;
        int result = cipher(key,key_size,nonce,nonce_size,data,actual,(size_t)claimed,position);
        if ((expected_ok && (result || memcmp(expected,actual,length))) || (!expected_ok && !result)) return 8;
    }
    if (fgetc(input) != EOF) return 9;
    fclose(input);dlclose(library);
    printf("{\"schema\":\"toolkit-publisher-crypto-capi-probe-v1\",\"cases\":%u,\"passed\":true,\"original_game_execution\":false}\n",count);
    return 0;
}
