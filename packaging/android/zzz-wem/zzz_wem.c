#include "zzz_wem.h"

#include <math.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "coding/vorbis_custom_decoder.h"

#define MAX_WEM (64u * 1024u * 1024u)
#define MAX_WAV (128u * 1024u * 1024u)
#define MAX_FRAMES_PER_READ 4096u
#define HEADER_BYTES 94u
#define PACKET_BUFFER_BYTES 0x8000u
#define MAX_PACKETS_WITHOUT_OUTPUT 32u

typedef struct {
    STREAMFILE interface;
    const uint8_t *bytes;
    size_t size;
    offv_t offset;
} memory_stream;

struct zzz_wem {
    memory_stream input;
    VGMSTREAMCHANNEL channel;
    vorbis_custom_codec_data vorbis;
    zzz_wem_format format;
    unsigned remaining;
    bool failed;
    uint8_t packet[PACKET_BUFFER_BYTES];
    uint8_t bytes[];
};

static size_t memory_read(STREAMFILE *sf, uint8_t *out, offv_t start, size_t count) {
    memory_stream *input = (memory_stream *)sf;
    if (start < 0 || (uint64_t)start >= input->size)
        return 0;
    size_t available = input->size - (size_t)start;
    if (count > available)
        count = available;
    memcpy(out, input->bytes + start, count);
    input->offset = start + count;
    return count;
}

static size_t memory_size(STREAMFILE *sf) {
    return ((memory_stream *)sf)->size;
}

static offv_t memory_offset(STREAMFILE *sf) {
    return ((memory_stream *)sf)->offset;
}

static void memory_name(STREAMFILE *sf, char *name, size_t capacity) {
    (void)sf;
    static const char label[] = "original.wem";
    if (capacity == 0)
        return;
    size_t count = sizeof(label) < capacity ? sizeof(label) : capacity;
    memcpy(name, label, count);
    name[count - 1] = 0;
}

static STREAMFILE *no_open(STREAMFILE *sf, const char *path, size_t buffer_size) {
    (void)sf;
    (void)path;
    (void)buffer_size;
    return NULL;
}

static void no_close(STREAMFILE *sf) {
    (void)sf;
}

static uint32_t read_le32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
            (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static uint16_t read_le16(const uint8_t *bytes) {
    return (uint16_t)bytes[0] | (uint16_t)bytes[1] << 8;
}

static bool inspect(const uint8_t *bytes, size_t size, zzz_wem_format *format) {
    if (!bytes || size < HEADER_BYTES + 5 || size > MAX_WEM ||
            memcmp(bytes, "RIFF", 4) != 0 || read_le32(bytes + 4) != size - 8 ||
            memcmp(bytes + 8, "WAVEfmt ", 8) != 0 || read_le32(bytes + 16) != 66 ||
            read_le16(bytes + 20) != 0xffff || read_le16(bytes + 32) != 0 ||
            read_le16(bytes + 34) != 0 || read_le16(bytes + 36) != 0x30 ||
            memcmp(bytes + 86, "data", 4) != 0 || read_le32(bytes + 90) != size - HEADER_BYTES)
        return false;

    format->channels = read_le16(bytes + 22);
    format->rate = read_le32(bytes + 24);
    format->frames = read_le32(bytes + 44);
    uint32_t seek_size = read_le32(bytes + 60);
    uint32_t audio_offset = read_le32(bytes + 64);
    if ((format->channels != 1 && format->channels != 2) || format->rate < 8000 || format->rate > 96000 ||
            format->frames == 0 || format->frames > (MAX_WAV - 44) / (format->channels * 2) ||
            audio_offset < 2 || audio_offset > size - HEADER_BYTES - 3 || seek_size > audio_offset - 2 ||
            seek_size % 4 != 0 || bytes[84] < 6 || bytes[84] > bytes[85] || bytes[85] > 13)
        return false;
    uint16_t setup_size = read_le16(bytes + HEADER_BYTES + seek_size);
    return setup_size > 0 && seek_size + 2 + setup_size == audio_offset;
}

static void clear_vorbis(vorbis_custom_codec_data *data) {
    vorbis_block_clear(&data->vb);
    vorbis_dsp_clear(&data->vd);
    vorbis_comment_clear(&data->vc);
    vorbis_info_clear(&data->vi);
}

static bool setup(zzz_wem *wem, int version, off_t setup_offset) {
    vorbis_custom_codec_data *data = &wem->vorbis;
    memset(data, 0, sizeof(*data));
    data->buffer = wem->packet;
    data->buffer_size = sizeof(wem->packet);
    data->type = VORBIS_WWISE;
    data->config.ww_version = version;
    data->config.channels = wem->format.channels;
    data->config.sample_rate = wem->format.rate;
    data->config.stream_end = wem->input.size;
    data->config.blocksize_1_exp = wem->bytes[84];
    data->config.blocksize_0_exp = wem->bytes[85];
    vorbis_info_init(&data->vi);
    vorbis_comment_init(&data->vc);
    data->op.packet = data->buffer;
    data->op.b_o_s = 1;
    bool ok = vorbis_custom_setup_init_wwise(&wem->input.interface, setup_offset, data);
    data->op.b_o_s = 0;
    if (ok && data->vi.channels == (int)wem->format.channels && data->vi.rate == (long)wem->format.rate &&
            vorbis_synthesis_init(&data->vd, &data->vi) == 0 && vorbis_block_init(&data->vd, &data->vb) == 0)
        return true;
    clear_vorbis(data);
    return false;
}

zzz_wem *zzz_wem_open(const uint8_t *bytes, size_t size, zzz_wem_format *format) {
    if (!bytes || !format || size < HEADER_BYTES + 5 || size > MAX_WEM)
        return NULL;
    zzz_wem *wem = calloc(1, sizeof(*wem) + size);
    if (!wem)
        return NULL;
    memcpy(wem->bytes, bytes, size);
    zzz_wem_format verified;
    if (!inspect(wem->bytes, size, &verified)) {
        free(wem);
        return NULL;
    }
    wem->input.interface = (STREAMFILE) {
        .read = memory_read, .get_size = memory_size, .get_offset = memory_offset,
        .get_name = memory_name, .open = no_open, .close = no_close,
    };
    wem->input.bytes = wem->bytes;
    wem->input.size = size;
    wem->channel.streamfile = &wem->input.interface;
    wem->channel.offset = HEADER_BYTES + read_le32(wem->bytes + 64);
    wem->remaining = verified.frames;
    wem->format = verified;
    off_t setup_offset = HEADER_BYTES + read_le32(wem->bytes + 60);
    // Same modern .wem preference and codebook retry as r2168's Wwise parser.
    if (!setup(wem, WWVORBIS_V62, setup_offset) && !setup(wem, WWVORBIS_V56, setup_offset)) {
        free(wem);
        return NULL;
    }
    *format = verified;
    return wem;
}

static bool next_packet(zzz_wem *wem) {
    vorbis_custom_codec_data *data = &wem->vorbis;
    offv_t previous = wem->channel.offset;
    if (previous < 0 || (uint64_t)previous > wem->input.size - 3)
        return false;
    uint16_t packet_size = read_le16(wem->bytes + previous);
    offv_t end = previous + 2 + packet_size;
    if (packet_size == 0 || (uint64_t)end > wem->input.size ||
            !vorbis_custom_parse_packet_wwise(&wem->channel, data) || wem->channel.offset != end)
        return false;
    int status = vorbis_synthesis(&data->vb, &data->op);
    if (status == OV_ENOTAUDIO)
        return true;
    if (status != 0 || vorbis_synthesis_blockin(&data->vd, &data->vb) != 0)
        return false;
    data->op.packetno++;
    return true;
}

static bool write_sample(uint8_t *dst, float sample) {
    if (!isfinite(sample))
        return false;
    // r2168's PCM16 conversion multiplies by 32767 and truncates, then clamps.
    float scaled = sample * 32767.0f;
    if (scaled > 32767.0f)
        scaled = 32767.0f;
    if (scaled < -32768.0f)
        scaled = -32768.0f;
    uint16_t output = (uint16_t)(int16_t)scaled;
    dst[0] = (uint8_t)output;
    dst[1] = (uint8_t)(output >> 8);
    return true;
}

int zzz_wem_read(zzz_wem *wem, unsigned frames, uint8_t *pcm, size_t capacity) {
    if (!wem || wem->failed || !pcm || frames == 0 || frames > MAX_FRAMES_PER_READ)
        return -1;
    if (frames > wem->remaining)
        frames = wem->remaining;
    unsigned channels = wem->format.channels;
    if (capacity < frames * channels * 2u)
        return -1;

    unsigned written = 0;
    unsigned skipped = 0;
    while (written < frames) {
        float **planes = NULL;
        int count = vorbis_synthesis_pcmout(&wem->vorbis.vd, &planes);
        if (count < 0)
            goto failed;
        if (count == 0) {
            if (skipped++ >= MAX_PACKETS_WITHOUT_OUTPUT || !next_packet(wem))
                goto failed;
            continue;
        }
        skipped = 0;
        if ((unsigned)count > frames - written)
            count = (int)(frames - written);
        for (int i = 0; i < count; i++) {
            for (unsigned channel = 0; channel < channels; channel++) {
                unsigned offset = ((written + (unsigned)i) * channels + channel) * 2u;
                if (!write_sample(pcm + offset, planes[channel][i]))
                    goto failed;
            }
        }
        if (vorbis_synthesis_read(&wem->vorbis.vd, count) != 0)
            goto failed;
        written += (unsigned)count;
    }
    wem->remaining -= written;
    return (int)written;

failed:
    wem->failed = true;
    return -1;
}

void zzz_wem_close(zzz_wem *wem) {
    if (!wem)
        return;
    clear_vorbis(&wem->vorbis);
    free(wem);
}
