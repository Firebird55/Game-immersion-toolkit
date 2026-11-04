/* Original portions: additional BSD-3-Clause option; see
 * packaging/codecs/MP3-BUILD-RECIPES-LICENSE.txt. Native probe only. */
#include <stdio.h>
#include <windows.h>
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
#include <libavfilter/avfilter.h>
#include <libswresample/swresample.h>
#include <lame/lame.h>
int main(void) {
    const char *names[] = {"avcodec-r19-audio-lame-63.dll", "avformat-r19-audio-lame-63.dll",
        "avutil-r19-audio-lame-61.dll", "swresample-r19-audio-lame-7.dll", "avfilter-r19-audio-lame-12.dll", "libmp3lame.dll"};
    const AVCodec *codec = avcodec_find_encoder_by_name("libmp3lame");
    int i;
    if (!codec) return 1;
    printf("ffmpeg-version\t%s\n", av_version_info());
    printf("lame-version\t%s\n", get_lame_version());
    printf("mp3-encoder\t%s\n", codec->name);
    printf("license\t%s\n", avcodec_license());
    printf("configuration\t%s\n", avcodec_configuration());
    printf("configuration\t%s\n", avformat_configuration());
    printf("configuration\t%s\n", avutil_configuration());
    printf("configuration\t%s\n", swresample_configuration());
    printf("configuration\t%s\n", avfilter_configuration());
    for (i=0;i<6;++i) {
        HMODULE module=GetModuleHandleA(names[i]); char path[32768];
        if (!module || !GetModuleFileNameA(module,path,sizeof(path))) return 1;
        /* Private control output only; publisher retains fixed origin/hash. */
        printf("module\t%s\t%s\n",names[i],path);
    }
    return 0;
}
