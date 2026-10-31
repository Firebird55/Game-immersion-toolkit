"""Authored build-policy regressions; native compilation runs on each CI host."""
import pytest

from scripts import audio_runtime_posix as build


def test_all_vgmstream_features_must_actually_reach_the_compiler():
    entry = {'file': '/build/vgmstream/src/vgmstream.c',
             'arguments': ['cc', *('-DVGM_USE_' + name for name in build.FEATURES), '-c', 'vgmstream.c']}
    assert build.verify_features([entry]) == list(build.FEATURES)
    for name in build.FEATURES:
        damaged = {**entry, 'arguments': [value for value in entry['arguments'] if value != '-DVGM_USE_' + name]}
        with pytest.raises(ValueError, match='missing codec'):
            build.verify_features([damaged])
    with pytest.raises(ValueError, match='compile evidence'):
        build.verify_features([{'file': '/build/other.c', 'command': entry['arguments']}])


@pytest.mark.parametrize('system,text', [
    ('linux', ' 0x1 (NEEDED) Shared library: [libc.so.6]\n 0x1 (NEEDED) Shared library: [libm.so.6]'),
    ('darwin', '/bundle/vgmstream-cli:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n'),
])
def test_native_binary_may_depend_only_on_base_os_libraries(system, text):
    assert build.validate_dynamic_dependencies(text, system)


@pytest.mark.parametrize('system,text', [
    ('linux', '0x1 (NEEDED) Shared library: [libavcodec.so.63]'),
    ('linux', '0x1 (NEEDED) Shared library: [libc.so.6]\n0x1 (RUNPATH) Library runpath: [/build/prefix/lib]'),
    ('linux', '0x1 (NEEDED) Shared library: [/tmp/libc.so.6]'),
    ('darwin', '/bundle/vgmstream-cli:\n\t/opt/homebrew/lib/libopus.dylib (compatibility version 1.0.0)'),
    ('darwin', '/bundle/vgmstream-cli:\n\t@rpath/libopus.dylib (compatibility version 1.0.0)'),
    ('darwin', '/bundle/vgmstream-cli:\n\t/usr/lib/../../tmp/libopus.dylib (compatibility version 1.0.0)'),
    ('linux', ''), ('darwin', '/bundle/vgmstream-cli:'),
])
def test_external_codec_and_build_host_dependencies_fail_closed(system, text):
    with pytest.raises(ValueError, match='depends'):
        build.validate_dynamic_dependencies(text, system)


def test_ffmpeg_must_preserve_every_pinned_upstream_audio_component(tmp_path):
    options = tmp_path / 'vgm/ext_libs/extra/ffmpeg_options.txt'
    options.parent.mkdir(parents=True)
    options.write_text('--enable-decoder=xma2,libopus\n--enable-demuxer=xmv\n--enable-parser=opus\n')
    ffmpeg = tmp_path / 'ffmpeg'
    ffmpeg.mkdir()
    (ffmpeg / 'config.h').write_text('#define CONFIG_GPL 0\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 0\n')
    expected = '#define CONFIG_XMA2_DECODER 1\n#define CONFIG_LIBOPUS_DECODER 1\n#define CONFIG_XMV_DEMUXER 1\n#define CONFIG_OPUS_PARSER 1\n'
    (ffmpeg / 'config_components.h').write_text(expected)
    assert build.verify_ffmpeg_features(tmp_path / 'vgm', ffmpeg)['decoder'] == ['libopus', 'xma2']
    (ffmpeg / 'config_components.h').write_text(expected.replace('CONFIG_XMA2_DECODER 1', 'CONFIG_XMA2_DECODER 0'))
    with pytest.raises(ValueError, match='XMA2'):
        build.verify_ffmpeg_features(tmp_path / 'vgm', ffmpeg)
    (ffmpeg / 'config_components.h').write_text(expected)
    (ffmpeg / 'config.h').write_text('#define CONFIG_GPL 1\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 0\n')
    with pytest.raises(ValueError, match='licensing'):
        build.verify_ffmpeg_features(tmp_path / 'vgm', ffmpeg)


def test_dependency_rewrite_rejects_unreviewed_upstream_structure(tmp_path):
    (tmp_path / 'CMakeLists.txt').write_text('include(FetchDependency)\ninclude(dependencies/new-codec)\n')
    with pytest.raises(ValueError, match='structure changed'):
        build.adapt_vgmstream(tmp_path)


def test_dependency_source_change_requires_review_before_any_build(tmp_path):
    calls = []
    pins = {'vgmstream': {'dependency_sources': [{'directory': 'unexpected-new-codec'}]}}
    with pytest.raises(ValueError, match='changed vgmstream dependency closure'):
        build.prepare_dependencies(pins, tmp_path, tmp_path, tmp_path, tmp_path,
            {}, '/bin/sh', 1, lambda *args: calls.append(args), lambda *args: calls.append(args))
    assert not calls
