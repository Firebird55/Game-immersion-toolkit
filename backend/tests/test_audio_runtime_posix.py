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


def test_celt_adapter_preserves_upstream_namespaces_and_rejects_source_drift(tmp_path):
    path = tmp_path / 'celt.cmake'
    original = ('\t\tset(CELT_CFLAGS\n\t\t\tcelt_encoder_create\n\t\t\tcelt_decode\n\t\t)\n'
                'foreach(ver 0061 0110)\nforeach(source ${CELT_CFLAGS})\n'
                'list(APPEND CELT_${ver}_CFLAGS "-D${source}=${source}_${ver}")\nendforeach()\nendforeach()\n')
    path.write_text(original)
    build.adapt_celt_symbols(path)
    adapted = path.read_text()
    # Existing decode/encode namespaces and both historical ABIs remain intact.
    additions = '\t\t\tcelt_encoder_get_size\n\t\t\tcelt_encoder_init\n'
    assert adapted.replace(additions, '') == original
    with pytest.raises(ValueError, match='namespace structure changed'):
        build.adapt_celt_symbols(path)
    assert path.read_text() == adapted
    path.write_text(original.replace('set(CELT_CFLAGS', 'set(NEW_CELT_FLAGS'))
    with pytest.raises(ValueError, match='namespace structure changed'):
        build.adapt_celt_symbols(path)


@pytest.mark.parametrize('prefix', ['', '_'])
def test_actual_celt_defined_exports_must_not_collide_with_opus(prefix):
    text = ('\ncelt.o:\n000000001 T ' + prefix + 'celt_encoder_get_size_0110\n'
            '000000002 T ' + prefix + 'celt_encoder_init_0110\n')
    assert build.validate_celt_symbols(text) == ['celt_encoder_get_size_0110', 'celt_encoder_init_0110']
    for name in ('celt_encoder_get_size', 'celt_encoder_init'):
        with pytest.raises(ValueError, match='collide with Opus'):
            build.validate_celt_symbols(text + '000000003 T ' + prefix + name + '\n')
        with pytest.raises(ValueError, match='missing'):
            build.validate_celt_symbols(text.replace(name + '_0110', 'different_export'))
