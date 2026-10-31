/* Authored non-shipping build-host probe; original project LICENSE applies.
 * Uses published FFmpeg/Opus APIs, not upstream implementation snippets.
 * No game inputs, system-wide codec discovery or runtime dispatch changes.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <libswresample/swresample.h>
#include <opus/opus.h>

typedef struct { unsigned char *data; int size; int pos; } Input;

static int read_memory(void *opaque, uint8_t *buffer, int size) {
    Input *input = opaque;
    int count = input->size - input->pos;
    if (count <= 0) return AVERROR_EOF;
    if (count > size) count = size;
    memcpy(buffer, input->data + input->pos, count);
    input->pos += count;
    return count;
}

static int64_t seek_memory(void *opaque, int64_t offset, int whence) {
    Input *input = opaque;
    int64_t next;
    if (whence == AVSEEK_SIZE) return input->size;
    whence &= ~AVSEEK_FORCE;
    if (whence == SEEK_SET) next = offset;
    else if (whence == SEEK_CUR) next = input->pos + offset;
    else if (whence == SEEK_END) next = input->size + offset;
    else return AVERROR(EINVAL);
    if (next < 0 || next > input->size) return AVERROR(EINVAL);
    input->pos = (int)next;
    return next;
}

static int flac(const char *source, const char *output) {
    FILE *file = NULL, *pcm = NULL;
    Input input = {0};
    AVIOContext *io = NULL;
    AVFormatContext *format = NULL;
    AVCodecContext *codec = NULL;
    AVPacket *packet = NULL;
    AVFrame *frame = NULL;
    int status = 1, stream = -1, result, decoded = 0;
    file = fopen(source, "rb");
    if (!file || fseek(file, 0, SEEK_END) || (input.size = (int)ftell(file)) <= 0
            || input.size > 1048576 || fseek(file, 0, SEEK_SET)) goto done;
    input.data = av_malloc(input.size);
    if (!input.data || fread(input.data, 1, input.size, file) != (size_t)input.size) goto done;
    io = avio_alloc_context(av_malloc(4096), 4096, 0, &input, read_memory, NULL, seek_memory);
    format = avformat_alloc_context();
    if (!io || !format) goto done;
    format->pb = io;
    format->flags |= AVFMT_FLAG_CUSTOM_IO;
    if (avformat_open_input(&format, NULL, NULL, NULL) < 0 || avformat_find_stream_info(format, NULL) < 0) goto done;
    stream = av_find_best_stream(format, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    if (stream < 0 || format->streams[stream]->codecpar->codec_id != AV_CODEC_ID_FLAC) goto done;
    codec = avcodec_alloc_context3(avcodec_find_decoder(AV_CODEC_ID_FLAC));
    if (!codec || avcodec_parameters_to_context(codec, format->streams[stream]->codecpar) < 0) goto done;
    codec->err_recognition = AV_EF_CRCCHECK | AV_EF_EXPLODE;
    if (avcodec_open2(codec, codec->codec, NULL) < 0) goto done;
    packet = av_packet_alloc(); frame = av_frame_alloc(); pcm = fopen(output, "wb");
    if (!packet || !frame || !pcm) goto done;
    while ((result = av_read_frame(format, packet)) >= 0) {
        if (packet->stream_index == stream) {
            if (avcodec_send_packet(codec, packet) < 0) goto done;
            while ((result = avcodec_receive_frame(codec, frame)) >= 0) {
                if (frame->format != AV_SAMPLE_FMT_S16 || frame->ch_layout.nb_channels != 1
                        || frame->sample_rate != 16000 || frame->nb_samples <= 0
                        || fwrite(frame->data[0], 2, frame->nb_samples, pcm) != (size_t)frame->nb_samples) goto done;
                decoded += frame->nb_samples;
                av_frame_unref(frame);
            }
            if (result != AVERROR(EAGAIN) && result != AVERROR_EOF) goto done;
        }
        av_packet_unref(packet);
    }
    if (result != AVERROR_EOF || decoded != 512) goto done;
    status = 0;
done:
    if (file) fclose(file);
    if (pcm && fclose(pcm)) status = 1;
    av_frame_free(&frame); av_packet_free(&packet); avcodec_free_context(&codec);
    avformat_close_input(&format);
    if (io) av_freep(&io->buffer);
    avio_context_free(&io); av_free(input.data);
    return status;
}

static AVCodecContext *opus_context(void) {
    AVCodecContext *context = avcodec_alloc_context3(avcodec_find_decoder_by_name("libopus"));
    if (!context) return NULL;
    context->sample_rate = 48000;
    av_channel_layout_default(&context->ch_layout, 1);
    context->request_sample_fmt = AV_SAMPLE_FMT_S16;
    if (avcodec_open2(context, context->codec, NULL) < 0) avcodec_free_context(&context);
    return context;
}

static int opus(const char *output) {
    opus_int16 silence[960] = {0};
    unsigned char encoded[4096];
    OpusEncoder *encoder = NULL;
    AVCodecContext *context = NULL;
    AVPacket *packet = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    FILE *pcm = NULL;
    int error, bytes, rejection, status = 1;
    encoder = opus_encoder_create(48000, 1, OPUS_APPLICATION_AUDIO, &error);
    if (!encoder || error != OPUS_OK || !packet || !frame) goto done;
    bytes = opus_encode(encoder, silence, 960, encoded, sizeof(encoded));
    context = opus_context();
    if (bytes <= 0 || !context || av_new_packet(packet, bytes) < 0) goto done;
    memcpy(packet->data, encoded, bytes);
    if (avcodec_send_packet(context, packet) < 0 || avcodec_receive_frame(context, frame) < 0
            || frame->format != AV_SAMPLE_FMT_S16 || frame->nb_samples != 960
            || frame->sample_rate != 48000 || frame->ch_layout.nb_channels != 1) goto done;
    pcm = fopen(output, "wb");
    if (!pcm || fwrite(frame->data[0], 2, 960, pcm) != 960) goto done;
    if (fclose(pcm)) { pcm = NULL; goto done; }
    pcm = NULL;
    /* A code-3 packet without its required framing byte is malformed. */
    avcodec_free_context(&context); context = opus_context();
    av_packet_unref(packet); av_frame_unref(frame);
    if (!context || av_new_packet(packet, 1) < 0) goto done;
    packet->data[0] = 0xff;
    rejection = avcodec_send_packet(context, packet);
    if (rejection >= 0) rejection = avcodec_receive_frame(context, frame);
    if (rejection != AVERROR_INVALIDDATA) goto done;
    puts("opus-roundtrip-and-fault\tpassed");
    status = 0;
done:
    if (pcm) fclose(pcm);
    if (encoder) opus_encoder_destroy(encoder);
    avcodec_free_context(&context); av_packet_free(&packet); av_frame_free(&frame);
    return status;
}

static int metadata(void) {
    const char *names[] = {"avcodec-vgmstream-63.dll", "avformat-vgmstream-63.dll",
        "avutil-vgmstream-61.dll", "swresample-vgmstream-7.dll"};
    int index;
    printf("ffmpeg-version\t%s\n", av_version_info());
    printf("opus-version\t%s\n", opus_get_version_string());
    printf("configuration\t%s\n", avcodec_configuration());
    printf("configuration\t%s\n", avformat_configuration());
    printf("configuration\t%s\n", avutil_configuration());
    printf("configuration\t%s\n", swresample_configuration());
    printf("license\t%s\n", avcodec_license());
    for (index = 0; index < 4; ++index) {
        HMODULE module = GetModuleHandleA(names[index]);
        char path[32768];
        if (!module || !GetModuleFileNameA(module, path, sizeof(path))) return 1;
        /* Consumed privately; Python publishes only relative origin and hash. */
        printf("module\t%s\t%s\n", names[index], path);
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    if (!strcmp(argv[1], "opus")) return opus(argv[3]);
    if (strcmp(argv[1], "flac") || flac(argv[2], argv[3])) return 1;
    return metadata();
}
