"""Synthetic Source fixtures only; no game text or recordings are redistributed."""
from collections import defaultdict
import io
import lzma
from pathlib import Path
import struct
import wave
import zlib

import pytest

from backend import portal_assets as assets
from backend.preparation_errors import PreparationFailure
from backend.source_dialogue import (SourceFiles, caption_pages, captions, decode_performance,
    pack_performance, sound_path, steam_language, text_table, unpack_performance)
from backend.source_scene import binary_scene, caption_sequences, decompress_scene, scene_image


def pcm(sample=100):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as writer:
        writer.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        writer.writeframes(struct.pack('<h', sample) * 800)
    return stream.getvalue()


def write_vpk(path, files):
    grouped = defaultdict(lambda: defaultdict(list))
    for name, data in files.items():
        member = Path(name)
        grouped[member.suffix[1:]][member.parent.as_posix()].append((member.stem, data))
    tree, payload = bytearray(), bytearray()
    for extension, directories in sorted(grouped.items()):
        tree += extension.encode() + b'\0'
        for directory, entries in sorted(directories.items()):
            tree += directory.encode() + b'\0'
            for stem, data in sorted(entries):
                tree += stem.encode() + b'\0' + struct.pack('<IHHIIH', zlib.crc32(data), 0, 0x7FFF, len(payload), len(data), 0xFFFF)
                payload += data
            tree += b'\0'
        tree += b'\0'
    tree += b'\0'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<3I', 0x55AA1234, 1, len(tree)) + tree + payload)


def localization(native, rows):
    return ('"lang" { "Language" "' + native + '" "Tokens" { ' + ' '.join(
        f'"{token}" "{text}"' for token, text in rows.items()) + ' } }').encode('utf-16')


def compiled(rows):
    block, directory = bytearray(), bytearray()
    for token, text in rows.items():
        value = (text + '\0').encode('utf-16-le')
        directory += struct.pack('<IIHH', zlib.crc32(token.lower().encode()), 0, len(block), len(value))
        block += value
    return struct.pack('<4s5I', b'VCCD', 1, 1, 4096, len(rows), 24 + len(directory)) + directory + block.ljust(4096, b'\0')


def scene(events, *, inactive=False):
    strings = ['', 'actor', 'channel']
    def string(value):
        if value not in strings:
            strings.append(value)
        return struct.pack('<h', strings.index(value))
    output = bytearray(b'bvcd\x04' + b'\0' * 4 + b'\0\x01')
    output += string('actor') + b'\x01' + string('channel') + struct.pack('<B', len(events))
    for sound, token, start, end, caption_type in events:
        output += b'\x05' + string(sound) + struct.pack('<ff', start, end)
        output += string(sound) + string('') + string('')
        output += b'\0\x08' + struct.pack('<f', 0) + b'\0' * 6
        output += struct.pack('<B', caption_type) + string(token) + b'\0'
    output += (b'\0' if inactive else b'\x01') + b'\x01\0\0'
    return bytes(output), strings


def image_fixture(events):
    data, strings = scene(events)
    pool, offsets = bytearray(), bytearray()
    for value in strings:
        offsets += struct.pack('<I', 20 + 4 * len(strings) + len(pool))
        pool += value.encode() + b'\0'
    entry_offset = 20 + len(offsets) + len(pool)
    summary_offset = entry_offset + 16
    data_offset = summary_offset + 8
    return (struct.pack('<4s4I', b'VSIF', 2, 1, len(strings), entry_offset) + offsets + pool
            + struct.pack('<4I', 123, data_offset, len(data), summary_offset) + struct.pack('<II', 4000, 0) + data)


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / 'steamapps/common/SyntheticPortal'
    root.mkdir(parents=True)
    (root / 'hl2.exe').write_bytes(b'fixture')
    (root / 'portal').mkdir()
    (root / 'portal/gameinfo.txt').write_text('"GameInfo" { "game" "Portal" }')
    manifest(root, 'english')
    files = {
        'scripts/game_sounds_manifest.txt': b'"game_sounds_manifest" { "precache_file" "scripts/speech.txt" }',
        'scripts/speech.txt': b'''"Portal.One" { "channel" "CHAN_VOICE" "wave" "vo/aperture_ai/one.wav" }
            "Portal.Two" { "wave" "vo/aperture_ai/two.wav" }
            "NPC_FloorTurret.Random" { "rndwave" { "wave" "vo/aperture_ai/one.wav" "wave" "vo/aperture_ai/two.wav" } }
            "Portal.song_credits" { "wave" "*#music/synthetic.mp3" }''',
        'scenes/scenes.image': image_fixture([('Portal.One', 'Dialogue.Combined', 2, 3, 0), ('Portal.Two', 'Dialogue.Combined', 3.5, 4, 1)]),
        'scripts/credits.txt': b'''"credits.txt" { "OutroSongLyrics" {
            "[1.0]Synthetic report header" "CreditsOutroText"
            "[2.0]#portal_lyrics_01" "CreditsOutroText"
            "[3.0]#portal_lyrics_02" "CreditsOutroText" } }''',
        'sound/vo/aperture_ai/one.wav': pcm(11),
        'sound/vo/aperture_ai/two.wav': pcm(22),
        'sound/commentary/synthetic.wav': pcm(33),
        'sound/music/synthetic.mp3': b'ID3synthetic',
    }
    rows = {'portal.one': 'Synthetic opening line.', 'dialogue.combined': 'Two synthetic lines.',
            'npc_floorturret.random': 'A generic turret caption.', 'missing.voice': 'An unavailable recording.',
            '#commentary/synthetic.wav': 'A synthetic commentary.', 'fx.noise': '<sfx>[Synthetic noise]',
            'fx.growl': '<I>*GROWL*'}
    for locale, native in assets.TEXT_LOCALES.items():
        files[f'resource/closecaption_{native}.txt'] = localization(native, rows)
        files[f'resource/closecaption_{native}.dat'] = compiled(rows)
        files[f'resource/portal_{native}.txt'] = localization(native, {'portal_lyrics_01': 'Synthetic credit words.', 'portal_lyrics_02': 'Later distinct credit words.'})
    write_vpk(root / 'portal/portal_pak_dir.vpk', files)
    return root


def manifest(root, language, *, state=4, selected=None):
    (root.parent.parent / 'appmanifest_400.acf').write_text(
        f'"AppState" {{ "appid" "400" "installdir" "{root.name}" "StateFlags" "{state}" '
        f'"MountedConfig" {{ "language" "{language}" }} "UserConfig" {{ "language" "{selected or language}" }} }}')


def test_native_pipeline_keeps_caption_bindings_and_text_only_report(installed, tmp_path):
    result = assets.index_language(installed, tmp_path, 'en', ['zh-Hant', 'ja'])
    assert result['format'] == 2
    assert len(result['records']) == 8
    states = {row['text_id'].split(':', 2)[-1]: row for row in result['records']}
    composite = states['dialogue.combined']
    assert [part['at_ms'] for part in composite['audio']['parts']] == [0, 1500]
    payload = assets.extract_voice(installed, composite['audio'], None, tmp_path)
    assert unpack_performance(payload) == [pcm(11), pcm(22)]
    assert states['npc_floorturret.random']['voice_status'] == 'unavailable'
    assert states['missing.voice']['voice_status'] == 'unavailable'
    assert states['#commentary/synthetic.wav']['dialogue_kind'] == 'commentary'
    assert states['report:0']['voice_status'] == 'unvoiced'
    songs = [row for row in result['records'] if row['dialogue_kind'] == 'song_full_track']
    assert len(songs) == 2 and songs[0]['audio'] == songs[1]['audio']
    assert songs[1]['source_text'] not in songs[0]['source_text']
    assert songs[0]['audio']['playback_scope'] == 'full_track'
    assert unpack_performance(assets.extract_voice(installed, songs[0]['audio'], None, tmp_path)) == [b'ID3synthetic']
    assert all('ja' in row['texts'] for row in result['records'] if row['dialogue_kind'] != 'readable')
    assert result['diagnostics']['excluded_sound_effect_captions'] == 2
    assert result['diagnostics']['timed_composite_captions'] == 1
    assert assets.discover_install([installed]) == installed
    assert assets.probe_voice_pack(installed, 'en') == 'present'


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_all_six_voice_locales_use_own_pack_without_english_fallback(installed, tmp_path, locale):
    native = assets.TEXT_LOCALES[locale]
    if locale != 'en':
        assert assets.probe_voice_pack(installed, locale) == 'missing'
        result = assets.index_language(installed, tmp_path, locale, [])
        assert not any(row['audio'] or row['voice_status'] == 'unvoiced' for row in result['records'])
    write_vpk(installed / f'portal/portal_sound_vo_{native}_dir.vpk', {'sound/vo/aperture_ai/one.wav': pcm(77)})
    result = assets.index_language(installed, tmp_path, locale, [])
    row = next(row for row in result['records'] if row['text_id'] == 'portal:caption:portal.one')
    assert row['audio']['locale'] == locale
    assert unpack_performance(assets.extract_voice(installed, row['audio'], None, tmp_path)) == [pcm(77)]
    if locale != 'en':
        assert next(row for row in result['records'] if row['dialogue_kind'] == 'song_full_track')['audio'] is None


def test_mounted_language_and_completed_manifest_required_for_shared_english(installed):
    assert steam_language(installed, 400) == 'english'
    manifest(installed, 'english', selected='french')
    assert steam_language(installed, 400) is None
    assert assets.probe_voice_pack(installed, 'en') == 'missing'
    manifest(installed, 'french')
    assert assets.probe_voice_pack(installed, 'en') == 'missing'
    assert assets.probe_voice_pack(installed, 'fr') == 'missing'
    manifest(installed, 'english', state=6)
    assert steam_language(installed, 400) is None


def test_extraction_revalidates_authored_binding_and_locale(installed, tmp_path):
    row = next(row for row in assets.index_install(installed, tmp_path)['records'] if row['audio'])
    changed = dict(row['audio'], token='missing.voice')
    with pytest.raises(PreparationFailure, match='binding changed'):
        assets.extract_voice(installed, changed, None, tmp_path)
    changed = dict(row['audio'], locale='fr')
    with pytest.raises(PreparationFailure, match='binding changed'):
        assets.extract_voice(installed, changed, None, tmp_path)
    changed = dict(row['audio'], parts=[{'archive': '../escape', 'member': 'sound/vo/line.wav', 'at_ms': 0}])
    with pytest.raises(PreparationFailure):
        assets.extract_voice(installed, changed, None, tmp_path)


def test_compiled_text_is_authoritative_and_english_reference_not_fallback(tmp_path):
    named = {'dialogue.line': 'Stale text.', '[english]dialogue.reference': 'English reference.'}
    write_vpk(tmp_path / 'test_dir.vpk', {'resource/closecaption_french.txt': localization('french', named),
        'resource/closecaption_french.dat': compiled({'dialogue.line': 'Compiled French fixture.'})})
    assert captions(SourceFiles(tmp_path, ['test_dir.vpk']), 'french') == {'dialogue.line': 'Compiled French fixture.'}
    with pytest.raises(PreparationFailure, match='language'):
        text_table(localization('english', named), 'french')
    assert text_table(localization('korean', {'line': 'Synthetic Korean.'}), 'koreana') == {'line': 'Synthetic Korean.'}


def test_scene_bounds_compression_and_disabled_or_conflicting_timelines():
    events = [('Portal.One', 'group', 0, 1, 0), ('Portal.Two', 'group', 1.5, 2, 1)]
    data, strings = scene(events)
    assert caption_sequences({1: binary_scene(data, strings)})['group'] == (('portal.one', 0), ('portal.two', 1500))
    packed = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 4096, 'lc': 3, 'lp': 0, 'pb': 2}])
    envelope = b'LZMA' + struct.pack('<IIBI', len(data), len(packed), 93, 4096) + packed
    assert decompress_scene(envelope) == data
    assert len(scene_image(image_fixture(events))) == 1
    assert caption_sequences({1: binary_scene(*scene(events, inactive=True))}) == {}
    assert caption_sequences({1: binary_scene(*scene([('Portal.One', '', 0, 1, 2)]))}) == {}
    conflict = {1: binary_scene(data, strings), 2: binary_scene(*scene([('Portal.Two', 'group', 0, 1, 0)]))}
    assert caption_sequences(conflict)['group'] == ()
    for broken in (data[:-1], b'bvcd\x05' + data[5:]):
        with pytest.raises(PreparationFailure):
            binary_scene(broken, strings)
    for broken in (image_fixture(events)[:-1], b'BAD!' + image_fixture(events)[4:]):
        with pytest.raises(PreparationFailure):
            scene_image(broken)


def test_original_pcm_decode_and_capsule_bounds(tmp_path):
    packed = pack_performance([pcm()])
    output = tmp_path / 'decoded.wav'
    decode_performance(packed, {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert output.read_bytes() == pcm()
    for data in (packed[:-1], packed + b'junk', b'SRCVOIC1' + struct.pack('<I', 65)):
        with pytest.raises(PreparationFailure):
            unpack_performance(data)
    assert caption_pages('<I>First<delay:2>Second') == ['First', 'Second']
    assert sound_path('*#vo/line.wav') == 'sound/vo/line.wav'
    assert sound_path('!sentence') is None
    with pytest.raises(PreparationFailure):
        sound_path('../escape.wav')


@pytest.mark.parametrize('fault', ['truncated', 'truncated-data', 'partial-frame', 'riff-length',
                                  'chunk-header', 'duplicate-data', 'truncated-format'])
def test_damaged_pcm_is_rejected_without_decoder_or_previous_output_loss(tmp_path, monkeypatch, fault):
    data = pcm()
    if fault in {'truncated', 'truncated-data'}:
        data = data[:-10]
        if fault == 'truncated-data':
            data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    elif fault == 'partial-frame':
        data = data[:-1]
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:40] + struct.pack('<I', len(data) - 44) + data[44:]
    elif fault == 'riff-length':
        data = data[:4] + struct.pack('<I', len(data) + 2) + data[8:]
    elif fault == 'chunk-header':
        data += b'JUNK'
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    elif fault == 'duplicate-data':
        data += b'data' + bytes(4)
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    else:
        data = data[:16] + struct.pack('<I', 14) + data[20:34] + data[36:]
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    def forbidden():
        pytest.fail('Damaged PCM must not fall back to a media decoder')
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', forbidden)
    output = tmp_path / 'decoded.wav'
    output.write_bytes(b'previous completed original audio')
    with pytest.raises(PreparationFailure):
        decode_performance(pack_performance([data]), {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert output.read_bytes() == b'previous completed original audio'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['decoded.wav']


@pytest.mark.parametrize('channels,width,frames', [(1, 1, 3), (1, 2, 160), (2, 2, 160), (2, 3, 160)])
def test_complete_pcm_with_metadata_retains_original_bytes_without_a_decoder(tmp_path, monkeypatch, channels, width, frames):
    data = io.BytesIO()
    with wave.open(data, 'wb') as stream:
        stream.setparams((channels, width, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(bytes([11]) * channels * width * frames)
    original = data.getvalue()
    # Preserve an authored unknown metadata chunk and its odd-byte padding.
    original = original[:12] + b'JUNK' + struct.pack('<I', 3) + b'own\0' + original[12:]
    original = original[:4] + struct.pack('<I', len(original) - 8) + original[8:]
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: pytest.fail('Complete PCM needs no decoder'))
    output = tmp_path / 'decoded.wav'
    output.write_bytes(b'previous complete output')
    decode_performance(pack_performance([original]), {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert output.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ['decoded.wav']


def test_source_codec_failure_preserves_previous_output_and_cleans_pending_file(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: Path('existing-source-codec'))
    def failed(command, **_options):
        Path(command[-1]).write_bytes(b'incomplete codec output')
        raise RuntimeError('owned synthetic codec failure')
    monkeypatch.setattr('backend.source_dialogue.subprocess.run', failed)
    output = tmp_path / 'decoded.wav'
    output.write_bytes(b'previous complete output')
    with pytest.raises(RuntimeError, match='synthetic codec failure'):
        decode_performance(pack_performance([b'ID3owned']), {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert output.read_bytes() == b'previous complete output'
    assert not list(tmp_path.glob('source-pcm-*'))


@pytest.mark.parametrize('offset,value,kind', [(22, 0, 'H'), (24, 0, 'I'), (34, 0, 'H'),
    (34, 40, 'H'), (32, 1, 'H'), (28, 1, 'I')])
def test_malformed_declared_pcm_never_reaches_an_available_source_codec(tmp_path, monkeypatch, offset, value, kind):
    data = bytearray(pcm())
    struct.pack_into('<' + kind, data, offset, value)
    calls = []
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: Path('existing-source-codec'))
    def available(command, **_options):
        calls.append(command)
        Path(command[-1]).write_bytes(pcm())
    monkeypatch.setattr('backend.source_dialogue.subprocess.run', available)
    output = tmp_path / 'decoded.wav'
    output.write_bytes(b'previous complete output')
    with pytest.raises(PreparationFailure):
        decode_performance(pack_performance([bytes(data)]), {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert calls == [] and output.read_bytes() == b'previous complete output'
    assert not list(tmp_path.glob('source-pcm-*'))


def test_structurally_valid_non_pcm_retains_existing_source_codec_path(tmp_path, monkeypatch):
    body = (b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 6, 1, 8000, 8000, 1, 8)
            + b'data' + struct.pack('<I', 80) + bytes([0xd5]) * 80)
    alaw = b'RIFF' + struct.pack('<I', len(body)) + body
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: Path('existing-source-codec'))
    calls = []
    def available(command, **_options):
        calls.append(command)
        Path(command[-1]).write_bytes(pcm())
    monkeypatch.setattr('backend.source_dialogue.subprocess.run', available)
    output = tmp_path / 'decoded.wav'
    decode_performance(pack_performance([alaw]), {'parts': [{'at_ms': 0}]}, output, None, tmp_path)
    assert len(calls) == 1 and output.read_bytes() == pcm()
    assert not list(tmp_path.glob('source-pcm-*'))


def test_composite_decode_uses_authored_offsets_and_rejects_invalid_delays(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: Path('existing-ffmpeg'))
    def decode(command, **options):
        calls.append((command, options))
        Path(command[-1]).write_bytes(pcm())
    monkeypatch.setattr('backend.source_dialogue.subprocess.run', decode)
    packed = pack_performance([pcm(1), pcm(2)])
    decode_performance(packed, {'parts': [{'at_ms': 0}, {'at_ms': 1500}]}, tmp_path / 'out.wav', None, tmp_path)
    command, options = calls[0]
    graph = command[command.index('-filter_complex') + 1]
    assert '[1:a]adelay=1500:all=1[a1]' in graph
    assert 'amix=inputs=2:normalize=0[out]' in graph
    assert options['timeout'] == 90
    for delay in (-1, float('nan'), 1800001):
        with pytest.raises(PreparationFailure, match='offset'):
            decode_performance(packed, {'parts': [{'at_ms': 0}, {'at_ms': delay}]}, tmp_path / 'out.wav', None, tmp_path)
