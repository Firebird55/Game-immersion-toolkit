#ifndef TOOLKIT_ZZZ_WEM_H
#define TOOLKIT_ZZZ_WEM_H

#include <stddef.h>
#include <stdint.h>

typedef struct zzz_wem zzz_wem;

typedef struct {
    uint32_t channels;
    uint32_t rate;
    uint32_t frames;
} zzz_wem_format;

#define ZZZ_WEM_API __attribute__((visibility("default")))

/* The stream owns a bounded copy of the WEM. It never opens any file. */
ZZZ_WEM_API zzz_wem *zzz_wem_open(const uint8_t *bytes, size_t size, zzz_wem_format *format);
/* Write interleaved signed 16-bit little-endian PCM. Negative is failure. */
ZZZ_WEM_API int zzz_wem_read(zzz_wem *wem, unsigned frames, uint8_t *pcm, size_t capacity);
ZZZ_WEM_API void zzz_wem_close(zzz_wem *wem);

#endif
